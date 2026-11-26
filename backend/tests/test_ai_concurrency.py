"""Concurrent model calls (spec 004, 7.3): batches of one document at the same time, the same
result as one at a time, a process-wide limit, and failures that behave as before."""

import asyncio
import re
from collections import Counter
from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, SecretStr

from ontology_platform.modules.ai.extraction import (
    BATCH_CHARS,
    ChunkText,
    ExtractionModels,
    Extractor,
    Proposal,
    RunStats,
)
from ontology_platform.modules.ai.gateway import (
    AiUnavailableError,
    InputFile,
    OpenAIGateway,
    _Call,
)
from ontology_platform.modules.ai.prompts import (
    EntityTypeOut,
    Quote,
    RelationOut,
    RelationsOut,
    ResolveOut,
    TermOut,
    TermsOut,
    TypesOut,
)
from ontology_platform.modules.jobs.runner import JobLeaseLostError
from ontology_platform.settings import Settings

DOC = uuid4()
BATCHES = 3
MODELS = ExtractionModels(standard="std", reasoning="deep")


def _chunks() -> list[ChunkText]:
    """Three chunks too long to share a batch: three batches of terms and of relations."""
    out: list[ChunkText] = []
    for n in range(BATCHES):
        sentence = f"炉次{n}由钢包运送。"
        text = sentence * (BATCH_CHARS // len(sentence) // 2 + 1)
        out.append(ChunkText(id=uuid4(), seq=n, text=text))
    return out


def _batch(text: str) -> int:
    """Which chunk a terms or relations call shows: its "[chunk n]" or its "[n.1]" numbers."""
    found = re.search(r"\[chunk (\d+)\]|\[(\d+)\.\d+\]", text)
    assert found is not None
    return int(found[1] or found[2])


class Gateway:
    """Answers by the batch it is shown; later batches answer first, and every call can be
    held back by `limit` (1: one call at a time, as before) or fail (`fail`)."""

    def __init__(self, limit: int | None = None, fail: tuple[str, int] | None = None) -> None:
        self.limit = asyncio.Semaphore(limit) if limit else None
        self.fail = fail
        self.active: Counter[str] = Counter()
        self.peak: Counter[str] = Counter()
        self.texts: list[tuple[str, str]] = []
        self.finished = 0

    def _held(self) -> AbstractAsyncContextManager[Any]:
        return self.limit if self.limit is not None else nullcontext()

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
        effort: str | None = None,
    ) -> T:
        async with self._held():
            self.texts.append((purpose, text))
            self.active[purpose] += 1
            self.peak[purpose] = max(self.peak[purpose], self.active[purpose])
            try:
                return schema.model_validate(await self._answer(purpose, text))
            finally:
                self.active[purpose] -= 1

    async def _answer(self, purpose: str, text: str) -> BaseModel:
        if purpose == "extract.types":
            names = sorted(set(re.findall(r"炉次\d", text)))
            return TypesOut(entity_types=[_type(name) for name in [*names, "钢包"]])
        if purpose == "extract.resolve":
            return ResolveOut(decisions=[])  # 炉次0, 炉次1 and 炉次2 look alike; no answer
        n = _batch(text)
        if self.fail == (purpose, n):
            await asyncio.sleep(0.01)
            raise AiUnavailableError("offline", retryable=True)
        await asyncio.sleep(0.02 * (BATCHES - n))
        self.finished += 1
        if purpose == "extract.terms":
            quote = f"炉次{n}由钢包运送。"
            return TermsOut(terms=[_term(f"炉次{n}", n, quote), _term("钢包", n, quote)])
        ref = re.search(rf"\[({n}\.\d+)\]", text)
        domain = re.search(rf"(new:Heat{n}) \|", text)
        assert ref is not None
        assert domain is not None
        return RelationsOut(
            relations=[_relation(domain[1], "new:Ladle", f"运送{n}", ref[1])], properties=[]
        )

    async def ping(self) -> bool:
        return True


def _term(name: str, chunk: int, quote: str) -> TermOut:
    return TermOut(
        name=name,
        english=None,
        definition=None,
        category="entity",
        quotes=[Quote(chunk=chunk, text=quote)],
    )


def _type(name: str) -> EntityTypeOut:
    ref = "new:Ladle" if name == "钢包" else f"new:Heat{name[-1]}"
    return EntityTypeOut(
        ref=ref,
        label_zh=name,
        label_en=None,
        definition_zh=None,
        synonyms=[],
        parent=None,
        confidence=0.9,
        sentence=None,
    )


def _relation(domain: str, range_: str, label: str, sentence: str) -> RelationOut:
    return RelationOut(
        label_zh=label,
        local_name="carries",
        domain=domain,
        range=range_,
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=0.8,
        sentence=sentence,
    )


async def _run(
    gateway: Gateway,
    steps: list[tuple[str, int, int]] | None = None,
    stats: RunStats | None = None,
    extractor: Extractor | None = None,
) -> list[Proposal]:
    async def progress(step: str, done: int, total: int) -> None:
        if steps is not None:
            steps.append((step, done, total))

    return await (extractor or Extractor(gateway, MODELS)).run(
        document_id=DOC,
        title="t",
        chunks=CHUNKS,
        known=[],
        progress=progress,
        stats=stats,
    )


CHUNKS = _chunks()


def _dump(proposals: Sequence[Proposal]) -> list[Any]:
    return [
        (p.op, p.kind, p.temp_ref, p.fields, p.confidence, p.flags, p.evidence) for p in proposals
    ]


async def test_the_batches_of_terms_and_of_relations_are_called_at_the_same_time() -> None:
    gateway = Gateway()
    await _run(gateway)

    assert gateway.peak["extract.terms"] == BATCHES
    assert gateway.peak["extract.relations"] == BATCHES
    assert gateway.peak["extract.types"] == 1


async def test_concurrent_batches_give_what_one_call_at_a_time_gives() -> None:
    one_at_a_time, concurrent = Gateway(limit=1), Gateway()
    stats_one, stats_many = RunStats(), RunStats()
    expected = await _run(one_at_a_time, stats=stats_one)
    found = await _run(concurrent, stats=stats_many)

    assert one_at_a_time.peak["extract.terms"] == 1
    assert _dump(found) == _dump(expected)
    # The model is asked exactly the same: recordings replay, whatever order calls finish in.
    assert Counter(concurrent.texts) == Counter(one_at_a_time.texts)
    assert stats_many.literal == stats_one.literal
    assert stats_many.trimmed == stats_one.trimmed
    # Results are merged in batch order, not in the order the calls finish.
    relations = [p for p in found if p.kind == "relation_type"]
    assert [p.fields["labelZh"] for p in relations] == [f"运送{n}" for n in range(BATCHES)]


async def test_progress_counts_finished_batches_in_order() -> None:
    steps: list[tuple[str, int, int]] = []
    await _run(Gateway(), steps)

    for step in ("terms", "relations"):
        assert [s for s in steps if s[0] == step] == [
            (step, done, BATCHES) for done in range(BATCHES + 1)
        ]


@pytest.mark.parametrize("purpose", ["extract.terms", "extract.relations"])
async def test_a_failed_batch_fails_the_run_with_its_error_and_stops_the_others(
    purpose: str,
) -> None:
    gateway = Gateway(fail=(purpose, 1))
    with pytest.raises(AiUnavailableError) as caught:
        await _run(gateway)
    assert caught.value.retryable  # the job goes back to the queue, as before

    finished = gateway.finished
    await asyncio.sleep(0.1)
    # The calls still running were cancelled: nothing finishes after the run has failed.
    assert gateway.finished == finished
    assert sum(gateway.active.values()) == 0


async def test_a_lost_lease_stops_the_run_as_itself() -> None:
    async def progress(step: str, done: int, total: int) -> None:
        if (step, done) == ("terms", 2):
            raise JobLeaseLostError

    with pytest.raises(JobLeaseLostError):
        await Extractor(Gateway(), MODELS).run(
            document_id=DOC, title="t", chunks=CHUNKS, known=[], progress=progress
        )


async def test_runs_at_the_same_time_keep_their_own_statistics() -> None:
    alone = RunStats()
    await _run(Gateway(), stats=alone)

    extractor = Extractor(Gateway(), MODELS)
    first, second = RunStats(), RunStats()
    await asyncio.gather(
        _run(Gateway(), stats=first, extractor=extractor),
        _run(Gateway(), stats=second, extractor=extractor),
    )
    assert alone.literal
    assert first.literal == alone.literal
    assert second.literal == alone.literal
    assert not hasattr(extractor, "last")


class _Answer(BaseModel):
    value: int


class _CountingGateway(OpenAIGateway):
    """The real gateway with the provider call replaced: counts the attempts in flight."""

    def __init__(self, settings: Settings, failures: int = 0) -> None:
        super().__init__(settings, retry_delays=(0.3,))
        self.active = 0
        self.peak = 0
        self.failures = failures

    async def _attempt[T: BaseModel](self, client: Any, call: "_Call[T]") -> T:
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(0.01)
            if self.failures:
                self.failures -= 1
                raise AiUnavailableError("busy", retryable=True)
            return call.schema.model_validate({"value": 1})
        finally:
            self.active -= 1


def _settings(**values: Any) -> Settings:
    return Settings(openai_api_key=SecretStr("sk-test"), **values)


async def _ask(gateway: OpenAIGateway) -> _Answer:
    return await gateway.structured(
        purpose="test", model="m", instructions="i", text="t", schema=_Answer
    )


async def test_the_gateway_makes_at_most_the_configured_calls_at_once() -> None:
    gateway = _CountingGateway(_settings(ai_max_concurrent_calls=2))
    answers = await asyncio.gather(*(_ask(gateway) for _ in range(6)))

    assert answers == [_Answer(value=1)] * 6
    assert gateway.peak == 2


async def test_a_call_waiting_to_retry_leaves_its_place_to_another() -> None:
    gateway = _CountingGateway(_settings(ai_max_concurrent_calls=1), failures=1)
    retried = asyncio.create_task(_ask(gateway))
    await asyncio.sleep(0.05)  # the first attempt failed; the retry waits 0.3 s
    started = asyncio.get_running_loop().time()
    await _ask(gateway)
    assert asyncio.get_running_loop().time() - started < 0.15
    assert await retried == _Answer(value=1)


def test_the_concurrency_settings_have_their_defaults_and_bounds() -> None:
    settings = Settings()
    assert (settings.worker_concurrency, settings.ai_max_concurrent_calls) == (3, 4)
    with pytest.raises(ValueError, match="worker_concurrency"):
        Settings(worker_concurrency=9)
    with pytest.raises(ValueError, match="worker_concurrency"):
        Settings(worker_concurrency=0)
    with pytest.raises(ValueError, match="ai_max_concurrent_calls"):
        Settings(ai_max_concurrent_calls=0)
    with pytest.raises(ValueError, match="ai_max_concurrent_calls"):
        Settings(ai_max_concurrent_calls=33)
