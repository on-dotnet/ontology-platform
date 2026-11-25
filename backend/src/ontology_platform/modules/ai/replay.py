"""Recording and replay of model calls, so that an evaluation is rerun without paying for it.

A call is keyed by the hash of everything the model sees: purpose, model, instructions, text,
the JSON Schema of the output and the attached files. A key that was recorded returns the
recorded output; the model is called only for new keys. After a change to deterministic
post-processing nothing is called again, after a change to one stage's prompt only that stage's
calls (and the calls whose input depends on their output). Recordings hold the structured output,
the hash and the usage of the call, nothing about how the model was reached.
"""

import hashlib
import json
import time
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from ontology_platform.modules.ai.gateway import InputFile, ModelGateway, OpenAIGateway, _Call

# Changes when the key or the record format changes, so old recordings are not misread.
FORMAT = 1


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
) -> str:
    payload = {
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
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_recordings(texts: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Records by key, from the texts of recording files; other formats are skipped."""
    records: dict[str, dict[str, Any]] = {}
    for text in texts:
        record = json.loads(text)
        if isinstance(record, dict) and record.get("format") == FORMAT and "key" in record:
            records[record["key"]] = record
    return records


def _stage() -> dict[str, Any]:
    return {"calls": 0, "replayed": 0, "seconds": 0.0, "inputTokens": 0, "outputTokens": 0}


class ReplayGateway:
    """Answers recorded calls from `recordings`; others go to `inner`, or fail if it is None.

    `labels` names documents by their id, for statistics and for the message of a miss. When
    `inner` has `take_usage` (see `MeteredGateway`), paid calls are counted with their attempts
    and tokens; replayed calls count as no call.
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
    ) -> T:
        key = call_key(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            files=files,
        )
        document = self._labels.get(document_id)
        stage = self._stats.setdefault(document or "-", {}).setdefault(purpose, _stage())
        started = time.monotonic()
        record = self._recordings.get(key)
        if record is not None:
            stage["replayed"] += 1
            stage["seconds"] += time.monotonic() - started
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
        result = await self._inner.structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            files=files,
            document_id=document_id,
        )
        attempts, input_tokens, output_tokens = _take_usage(self._inner)
        stage["calls"] += attempts
        stage["inputTokens"] += input_tokens
        stage["outputTokens"] += output_tokens
        stage["seconds"] += time.monotonic() - started
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
        }
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
                purpose: {**stage, "seconds": round(stage["seconds"], 1)}
                for purpose, stage in stages.items()
            }
            for document, stages in self._stats.items()
        }


def _take_usage(gateway: ModelGateway) -> tuple[int, int, int]:
    take = getattr(gateway, "take_usage", None)
    if take is None:
        return 1, 0, 0
    attempts, input_tokens, output_tokens = take()
    return int(attempts), int(input_tokens), int(output_tokens)


class MeteredGateway(OpenAIGateway):
    """The real gateway, keeping the usage of its attempts in memory instead of the database."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._usage = [0, 0, 0]

    async def _record(
        self, call: "_Call[Any]", started: float, usage: Any, error_code: str | None
    ) -> None:
        self._usage[0] += 1
        self._usage[1] += getattr(usage, "input_tokens", None) or 0
        self._usage[2] += getattr(usage, "output_tokens", None) or 0

    def take_usage(self) -> tuple[int, int, int]:
        """Attempts and tokens since the last call of this method."""
        attempts, input_tokens, output_tokens = self._usage
        self._usage = [0, 0, 0]
        return attempts, input_tokens, output_tokens
