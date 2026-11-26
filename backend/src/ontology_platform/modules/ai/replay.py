"""Recording and replay of model calls, so that an evaluation is rerun without paying for it.

A call is keyed by the hash of everything the model sees: purpose, model, instructions, text,
the JSON Schema of the output and the attached files. A key that was recorded returns the
recorded output; the model is called only for new keys, that is for calls whose input changed:
after a change to one stage's prompt, that stage's calls and the later ones whose input depends
on their output; after a change to post-processing, the later documents' calls that show what
earlier documents produced. Recordings hold the structured output, the hash, the purpose, model
and document name and the usage of the call, nothing about how the model was reached. The base
URL is not part of the key: the same model name at another provider replays the same outputs.
"""

import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

from ontology_platform.modules.ai.gateway import InputFile, ModelGateway, OpenAIGateway, _Call

# Changes when the key or the record format changes, so old recordings are not misread.
FORMAT = 1

# Attempts, input, output and reasoning tokens of the call in progress. A context variable, so
# that calls made at the same time (the batches of a document) each count their own attempts.
_CALL_USAGE: ContextVar[list[int] | None] = ContextVar("call_usage", default=None)


class ReplayMissError(Exception):
    """Replay only, and a call was not recorded."""


def call_key(
    *,
    purpose: str,
    model: str,
    instructions: str,
    text: str,
    schema: type[BaseModel],
    files: Sequence[InputFile] = (),
    effort: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "format": FORMAT,
        "purpose": purpose,
        "model": model,
        "instructions": instructions,
        "text": text,
        "schema": schema.model_json_schema(),
        "files": [
            [item.filename, item.media_type, hashlib.sha256(item.data_base64.encode()).hexdigest()]
            for item in files
        ],
    }
    # Only when given, so that the keys of calls without an effort stay what they were.
    if effort is not None:
        payload["effort"] = effort
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_recordings(
    texts: Iterable[str], on_invalid: Callable[[int], None] | None = None
) -> dict[str, dict[str, Any]]:
    """Records by key, from the texts of recording files.

    Other formats are skipped silently; text that is not JSON is skipped and reported by its
    position, since one damaged file should cost one call, not the whole run.
    """
    records: dict[str, dict[str, Any]] = {}
    for index, text in enumerate(texts):
        try:
            record = json.loads(text)
        except json.JSONDecodeError:
            if on_invalid is not None:
                on_invalid(index)
            continue
        if isinstance(record, dict) and record.get("format") == FORMAT and "key" in record:
            records[record["key"]] = record
    return records


# Paid calls: attempts, seconds and tokens. "recorded…": the usage every call had when it was
# recorded, paid now or replayed, so that runs compare whatever they replayed.
STAGE_COUNTS = (
    "calls",
    "replayed",
    "seconds",
    "inputTokens",
    "outputTokens",
    "reasoningTokens",
    "recordedSeconds",
    "recordedInputTokens",
    "recordedOutputTokens",
    "recordedReasoningTokens",
)
_SECONDS = frozenset({"seconds", "recordedSeconds"})


def _stage() -> dict[str, Any]:
    return {key: 0.0 if key in _SECONDS else 0 for key in STAGE_COUNTS}


def _add_recorded(stage: dict[str, Any], record: Mapping[str, Any]) -> None:
    # Recordings made before these fields existed have no seconds or reasoning tokens.
    stage["recordedSeconds"] += record.get("seconds", 0.0)
    stage["recordedInputTokens"] += record.get("inputTokens", 0)
    stage["recordedOutputTokens"] += record.get("outputTokens", 0)
    stage["recordedReasoningTokens"] += record.get("reasoningTokens", 0)


class ReplayGateway:
    """Answers recorded calls from `recordings`; others go to `inner`, or fail if it is None.

    `labels` names documents by their id, for statistics and for the message of a miss. Paid
    calls are counted with their attempts and tokens: those of a `MeteredGateway` per call, also
    when calls run at the same time; a stand-in may report them with `take_usage`. Replayed
    calls count as no call. A call that fails counts nothing: the evaluation stops on it.
    """

    def __init__(
        self,
        recordings: Mapping[str, dict[str, Any]],
        inner: ModelGateway | None,
        *,
        labels: Mapping[Any, str] | None = None,
    ) -> None:
        self._recordings = dict(recordings)
        self._inner = inner
        self._labels = dict(labels or {})
        self.new_recordings: dict[str, dict[str, Any]] = {}
        self._stats: dict[str, dict[str, dict[str, Any]]] = {}

    def label(self, document_id: Any, name: str) -> None:
        self._labels[document_id] = name

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
        key = call_key(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            files=files,
            effort=effort,
        )
        document = self._labels.get(document_id)
        stage = self._stats.setdefault(document or "-", {}).setdefault(purpose, _stage())
        started = time.monotonic()
        record = self._recordings.get(key)
        if record is not None:
            stage["replayed"] += 1
            stage["seconds"] += time.monotonic() - started
            _add_recorded(stage, record)
            # A fresh object each time: callers extend the lists of what they get.
            return schema.model_validate(record["output"])
        if self._inner is None:
            done = sum(
                item["calls"] + item["replayed"] for item in self._stats[document or "-"].values()
            )
            raise ReplayMissError(
                f"No recording for {document or 'an unknown document'}, stage {purpose} "
                f"(call {done + 1} of the document, model {model})."
            )
        usage = [0, 0, 0, 0]
        token = _CALL_USAGE.set(usage)
        try:
            result = await self._inner.structured(
                purpose=purpose,
                model=model,
                instructions=instructions,
                text=text,
                schema=schema,
                files=files,
                document_id=document_id,
                effort=effort,
            )
        finally:
            _CALL_USAGE.reset(token)
        attempts, input_tokens, output_tokens, reasoning_tokens = _usage_of(self._inner, usage)
        seconds = time.monotonic() - started
        stage["calls"] += attempts
        stage["inputTokens"] += input_tokens
        stage["outputTokens"] += output_tokens
        stage["reasoningTokens"] += reasoning_tokens
        stage["seconds"] += seconds
        record = {
            "format": FORMAT,
            "key": key,
            "purpose": purpose,
            "model": model,
            "document": document,
            # Dumped before the caller can change the result.
            "output": result.model_dump(mode="json"),
            "attempts": attempts,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "reasoningTokens": reasoning_tokens,
            "seconds": round(seconds, 1),
        }
        _add_recorded(stage, record)
        self._recordings[key] = record
        self.new_recordings[key] = record
        return result

    async def ping(self) -> bool:
        return self._inner is not None and await self._inner.ping()

    def recording_files(self) -> list[tuple[str, str]]:
        """(file name, text) of each new recording."""
        return [
            (f"{key}.json", json.dumps(record, ensure_ascii=False, indent=1, sort_keys=True))
            for key, record in self.new_recordings.items()
        ]

    def stats(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Per document and stage: paid calls (attempts), replayed calls, seconds, tokens."""
        return {
            document: {
                purpose: {
                    **stage,
                    "seconds": round(stage["seconds"], 1),
                    "recordedSeconds": round(stage["recordedSeconds"], 1),
                }
                for purpose, stage in stages.items()
            }
            for document, stages in self._stats.items()
        }


def _usage_of(gateway: ModelGateway, usage: Sequence[int]) -> tuple[int, int, int, int]:
    """One call's usage: counted for it by a `MeteredGateway`; else what a stand-in's
    `take_usage` reports; else one attempt."""
    if isinstance(gateway, MeteredGateway):
        attempts, input_tokens, output_tokens, reasoning_tokens = usage
        return attempts, input_tokens, output_tokens, reasoning_tokens
    take = getattr(gateway, "take_usage", None)
    if take is None:
        return 1, 0, 0, 0
    attempts, input_tokens, output_tokens, reasoning_tokens = take()
    return int(attempts), int(input_tokens), int(output_tokens), int(reasoning_tokens)


class MeteredGateway(OpenAIGateway):
    """The real gateway, keeping the usage of its attempts in memory instead of the database.

    Through a `ReplayGateway` each call counts its own attempts; called directly, they add up
    until `take_usage`.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._usage = [0, 0, 0, 0]

    async def _record(
        self, call: "_Call[Any]", started: float, usage: Any, error_code: str | None
    ) -> None:
        counts = _CALL_USAGE.get()
        if counts is None:
            counts = self._usage
        counts[0] += 1
        counts[1] += getattr(usage, "input_tokens", None) or 0
        counts[2] += getattr(usage, "output_tokens", None) or 0
        details = getattr(usage, "output_tokens_details", None)
        counts[3] += getattr(details, "reasoning_tokens", None) or 0

    def take_usage(self) -> tuple[int, int, int, int]:
        """Attempts, input, output and reasoning tokens since the last call of this method."""
        attempts, input_tokens, output_tokens, reasoning_tokens = self._usage
        self._usage = [0, 0, 0, 0]
        return attempts, input_tokens, output_tokens, reasoning_tokens
