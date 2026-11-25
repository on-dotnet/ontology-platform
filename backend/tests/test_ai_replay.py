"""Recording and replay of model calls: same input, no second call; a miss names its place."""

import json
from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.replay import (
    MeteredGateway,
    ReplayGateway,
    ReplayMissError,
    call_key,
    load_recordings,
)
from ontology_platform.settings import Settings


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
    ) -> T:
        self.calls += 1
        return schema.model_validate({"items": [f"call {self.calls}", text]})

    async def ping(self) -> bool:
        return True

    def take_usage(self) -> tuple[int, int, int]:
        return 2, 100, 10  # attempts (one retry), input tokens, output tokens


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
    recorder = ReplayGateway({}, CountingGateway(), labels={"doc-a": "docs/a.md"})
    original = await recorder.structured(**ask())
    files = recorder.recording_files()

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
    assert replayer.new_recordings == {}


async def test_metered_gateway_sums_the_usage_of_every_attempt() -> None:
    gateway = MeteredGateway(Settings(openai_api_key=None))
    call = SimpleNamespace(purpose="extract.terms", model="m", document_id=None)
    await gateway._record(call, 0.0, SimpleNamespace(input_tokens=7, output_tokens=3), "x")  # type: ignore[arg-type]
    await gateway._record(call, 0.0, SimpleNamespace(input_tokens=5, output_tokens=2), None)  # type: ignore[arg-type]
    await gateway._record(call, 0.0, None, "ai.unavailable")  # type: ignore[arg-type]

    assert gateway.take_usage() == (3, 12, 5)
    assert gateway.take_usage() == (0, 0, 0)


def _key_fields(call: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in call.items() if k != "document_id"}
