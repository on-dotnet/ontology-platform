"""Recording and replay of model calls: same input, no second call; a miss names its place."""

import asyncio
import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, SecretStr

from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.replay import (
    MeteredGateway,
    ReplayGateway,
    ReplayMissError,
    call_key,
    load_recordings,
)
from ontology_platform.settings import Settings
from test_ai_gateway import Answer as GatewayAnswer
from test_ai_gateway import client_with, stream


class Answer(BaseModel):
    items: list[str]


class Other(BaseModel):
    items: list[str]
    extra: int


class CountingGateway:
    """Answers with the call number, and reports made-up token usage for each call."""

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        return schema.model_validate({"items": [f"call {self.calls}", text]})

    async def ping(self) -> bool:
        return True

    def take_usage(self) -> tuple[int, int, int, int]:
        return 2, 100, 10, 4  # attempts (one retry), input, output and reasoning tokens


def ask(**overrides: Any) -> dict[str, Any]:
    call: dict[str, Any] = {
        "purpose": "extract.terms",
        "model": "m1",
        "instructions": "List terms.",
        "text": "Document: a.md\n\nhello",
        "schema": Answer,
        "document_id": "doc-a",
    }
    return {**call, **overrides}


async def test_a_recorded_call_is_not_made_again() -> None:
    inner = CountingGateway()
    gateway = ReplayGateway({}, inner, labels={"doc-a": "docs/a.md"})
    first = await gateway.structured(**ask())
    second = await gateway.structured(**ask())

    assert inner.calls == 1
    assert first == second
    assert first is not second  # extraction extends lists in place: never hand out one object
    assert len(gateway.new_recordings) == 1


async def test_replay_returns_the_output_as_it_was_before_the_caller_changed_it() -> None:
    gateway = ReplayGateway({}, CountingGateway())
    first = await gateway.structured(**ask())
    first.items.append("changed by the caller")
    assert (await gateway.structured(**ask())).items == ["call 1", "Document: a.md\n\nhello"]


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "extract.types"},
        {"model": "m2"},
        {"instructions": "List terms!"},
        {"text": "Document: a.md\n\nhello."},
        {"schema": Other},
        {"files": [InputFile("a.pdf", "application/pdf", "AAAA")]},
    ],
)
def test_every_input_of_a_call_is_part_of_its_key(change: dict[str, Any]) -> None:
    def key(call: dict[str, Any]) -> str:
        call = {k: v for k, v in call.items() if k != "document_id"}
        return call_key(**call)

    assert key(ask(**change)) != key(ask())
    # the document id is not an input of the model: fresh ids must not defeat the recording
    assert key(ask(document_id="other")) == key(ask())


async def test_recordings_survive_a_round_trip_through_files() -> None:
    emitted: list[tuple[str, str]] = []
    recorder = ReplayGateway(
        {},
        CountingGateway(),
        labels={"doc-a": "docs/a.md"},
        on_record=lambda name, content: emitted.append((name, content)),
    )
    original = await recorder.structured(**ask())
    files = recorder.recording_files()
    assert emitted == files

    assert [name for name, _ in files] == [f"{call_key(**_key_fields(ask()))}.json"]
    record = json.loads(files[0][1])
    assert set(record) == {
        "format",
        "key",
        "purpose",
        "model",
        "document",
        "output",
        "attempts",
        "inputTokens",
        "outputTokens",
        "reasoningTokens",
        "seconds",
    }
    assert record["document"] == "docs/a.md"

    replayer = ReplayGateway(load_recordings([text for _, text in files]), None)
    assert await replayer.structured(**ask()) == original


async def test_replay_only_names_the_document_and_stage_of_a_miss() -> None:
    gateway = ReplayGateway({}, None, labels={"doc-a": "docs/a.md"})
    with pytest.raises(ReplayMissError) as caught:
        await gateway.structured(**ask(purpose="extract.relations"))
    assert "docs/a.md" in str(caught.value)
    assert "extract.relations" in str(caught.value)


async def test_stats_count_paid_calls_and_their_tokens_but_not_replays() -> None:
    gateway = ReplayGateway({}, CountingGateway(), labels={"doc-a": "docs/a.md"})
    await gateway.structured(**ask())
    await gateway.structured(**ask())

    stats = gateway.stats()
    assert stats["docs/a.md"]["extract.terms"]["calls"] == 2  # the retry counts
    assert stats["docs/a.md"]["extract.terms"]["replayed"] == 1
    assert stats["docs/a.md"]["extract.terms"]["inputTokens"] == 100
    assert stats["docs/a.md"]["extract.terms"]["outputTokens"] == 10
    assert stats["docs/a.md"]["extract.terms"]["reasoningTokens"] == 4
    # The replayed call adds what its recording says it cost.
    assert stats["docs/a.md"]["extract.terms"]["recordedOutputTokens"] == 20
    assert stats["docs/a.md"]["extract.terms"]["recordedReasoningTokens"] == 8
    assert stats["docs/a.md"]["extract.terms"]["seconds"] >= 0


async def test_a_replayed_run_reports_no_calls_at_all() -> None:
    recorder = ReplayGateway({}, CountingGateway(), labels={"doc-a": "docs/a.md"})
    await recorder.structured(**ask())
    recordings = load_recordings([text for _, text in recorder.recording_files()])

    replayer = ReplayGateway(recordings, None, labels={"doc-a": "docs/a.md"})
    await replayer.structured(**ask())
    stage = replayer.stats()["docs/a.md"]["extract.terms"]
    assert (stage["calls"], stage["replayed"], stage["inputTokens"], stage["outputTokens"]) == (
        0,
        1,
        0,
        0,
    )
    assert (stage["recordedInputTokens"], stage["recordedOutputTokens"]) == (100, 10)
    assert replayer.new_recordings == {}


async def test_metered_gateway_counts_a_retried_call_end_to_end() -> None:
    responses = [httpx2.Response(500, json={"error": {"message": "x"}}), stream('{"value": 7}')]

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses.pop(0)

    settings = Settings(openai_api_key=SecretStr("sk-test"), ai_model="m")
    gateway = MeteredGateway(settings, http_client=client_with(handler), retry_delays=(0,))
    answer = await gateway.structured(
        purpose="test", model="m", instructions="i", text="t", schema=GatewayAnswer
    )
    assert answer == GatewayAnswer(value=7)
    assert gateway.take_usage() == (2, 11, 3, 0)  # the failed attempt reports no usage


async def test_metered_gateway_sums_the_usage_of_every_attempt() -> None:
    gateway = MeteredGateway(Settings(openai_api_key=None))
    call = SimpleNamespace(purpose="extract.terms", model="m", document_id=None)
    await gateway._record(call, 0.0, SimpleNamespace(input_tokens=7, output_tokens=3), "x")  # type: ignore[arg-type]
    details = SimpleNamespace(reasoning_tokens=1)
    usage = SimpleNamespace(input_tokens=5, output_tokens=2, output_tokens_details=details)
    await gateway._record(call, 0.0, usage, None)  # type: ignore[arg-type]
    await gateway._record(call, 0.0, None, "ai.unavailable")  # type: ignore[arg-type]

    assert gateway.take_usage() == (3, 12, 5, 1)
    assert gateway.take_usage() == (0, 0, 0, 0)


def _key_fields(call: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in call.items() if k != "document_id"}


def test_the_effort_is_part_of_the_key_only_when_given() -> None:
    fields = _key_fields(ask())
    assert call_key(**fields, effort=None) == call_key(**fields)
    assert call_key(**fields, effort="low") != call_key(**fields)
    assert call_key(**fields, effort="low") != call_key(**fields, effort="high")


async def test_the_effort_reaches_the_model_and_keys_the_recording() -> None:
    seen: list[str | None] = []

    class Inner(CountingGateway):
        async def structured[T: BaseModel](self, **call: Any) -> T:
            seen.append(call.get("effort"))
            return await super().structured(**call)

    gateway = ReplayGateway({}, Inner())
    await gateway.structured(**ask(), effort="low")
    await gateway.structured(**ask(), effort="low")
    await gateway.structured(**ask())
    assert seen == ["low", None]


async def test_concurrent_calls_each_count_their_own_attempts_and_tokens() -> None:
    class Interleaved(MeteredGateway):
        """Call "tN" makes N attempts of 10*N input and N output tokens, interleaved."""

        async def structured[T: BaseModel](self, **call: Any) -> T:
            n = int(call["text"][-1])
            record = SimpleNamespace(purpose=call["purpose"], model="m", document_id=None)
            for _ in range(n):
                await asyncio.sleep(0.01)
                usage = SimpleNamespace(input_tokens=10 * n, output_tokens=n)
                await self._record(record, 0.0, usage, None)  # type: ignore[arg-type]
            answer: T = call["schema"].model_validate({"items": [call["text"]]})
            return answer

    gateway = ReplayGateway({}, Interleaved(Settings(openai_api_key=None)))
    await asyncio.gather(*(gateway.structured(**ask(text=f"t{n}")) for n in (3, 1, 2)))

    records = {r["output"]["items"][0]: r for r in gateway.new_recordings.values()}
    for n in (1, 2, 3):
        record = records[f"t{n}"]
        assert (record["attempts"], record["inputTokens"], record["outputTokens"]) == (
            n,
            10 * n * n,
            n * n,
        )
