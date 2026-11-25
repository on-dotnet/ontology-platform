"""Extraction quality on a case pack: `python -m ontology_platform.modules.ai.eval`.

Reads a JSON bundle on stdin:
  {"files": {"docs/<name>": "<base64>", "eval/expected.toml": "<base64>"},
   "recordings": ["<text of a recording file>", ...], "manifest": "<models.json text>" | null,
   "mode": "record" | "replay"}
Runs the model over every document in order, accepting every proposal so that later documents
align with what earlier ones produced, then scores entity types, relations and, when
eval/expected.toml has them, properties and hierarchy (format in docs/development.md). A case
without eval/expected.toml (private documents whose answers come later) is run and not scored.

Model calls go through `ReplayGateway`: a call whose input was recorded is answered from the
recording. "record" calls the model for the others and returns their recordings; "replay"
fails on the first call that was not recorded and needs no model key. "replay" uses the models
of the last recorded run (models.json), so that a workspace without the model settings asks
for the same keys. Ids of documents, chunks and accepted elements follow from names, since the
ids of existing types are part of later prompts.

Progress goes to stderr. Stdout is one JSON object: {"result": "<result JSON text>",
"files": [{"name": ..., "content": ...}]} with the new recording files, or {"error": ...,
"files": [...]} when the run failed, so that calls already paid for are kept.

The result keeps the accepted elements and parents, so that a changed expected.toml can be
scored against the same run: `--rescore` reads {"expected": "<toml text>", "elements": [...],
"parents": {...}} on stdin and prints the score.
"""

import asyncio
import base64
import json
import sys
import time
import tomllib
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from typing import Any
from uuid import UUID, uuid5

from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    Proposal,
    normalize,
)
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.replay import (
    MeteredGateway,
    ReplayGateway,
    ReplayMissError,
    load_recordings,
)
from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import detect_type, parse_document
from ontology_platform.settings import Settings

_NAMESPACE = UUID("6f1d3c52-8a4e-4d0b-9f57-2c1e0b7a9d43")
MANIFEST = "models.json"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def stable_id(*parts: str) -> UUID:
    return uuid5(_NAMESPACE, "/".join(parts))


def accept(
    known: list[KnownElement],
    proposals: Sequence[Proposal],
    parents: dict[UUID, UUID] | None = None,
) -> list[KnownElement]:
    """Apply proposals as if a reviewer accepted all of them; `parents` gets new types' parents.

    New elements get ids derived from their local names (unique within a run), so that a rerun
    shows the model the same ids.
    """
    result = list(known)
    used = {element.id for element in known}

    def new_id(kind: str, local_name: str) -> UUID:
        element_id, counter = stable_id(kind, local_name), 2
        while element_id in used:
            element_id, counter = stable_id(kind, local_name, str(counter)), counter + 1
        used.add(element_id)
        return element_id

    temp: dict[str, UUID] = {}
    for proposal in proposals:
        if proposal.op == "create" and proposal.temp_ref:
            temp[proposal.temp_ref] = new_id(proposal.kind, proposal.fields["localName"])

    def resolve(ref: Any) -> UUID | None:
        if not ref:
            return None
        if ref in temp:
            return temp[ref]
        try:
            return UUID(str(ref))
        except ValueError:
            return None

    for proposal in proposals:
        fields = proposal.fields
        synonyms = tuple(item["text"] for item in fields.get("synonyms", []))
        if proposal.op == "update" and proposal.target_element_id:
            result = [
                replace(e, synonyms=e.synonyms + synonyms)
                if e.id == proposal.target_element_id
                else e
                for e in result
            ]
            continue
        element_id = temp.get(proposal.temp_ref or "") or new_id(proposal.kind, fields["localName"])
        parent = resolve(fields.get("parentRef"))
        if parents is not None and parent is not None:
            parents[element_id] = parent
        result.append(
            KnownElement(
                id=element_id,
                kind=proposal.kind,
                local_name=fields["localName"],
                label_zh=fields["labelZh"],
                label_en=fields.get("labelEn"),
                synonyms=synonyms,
                definition_zh=fields.get("definitionZh"),
                domain_id=resolve(fields.get("domainRef")),
                range_id=resolve(fields.get("rangeRef")),
            )
        )
    return result


def dump_elements(known: Sequence[KnownElement]) -> list[dict[str, Any]]:
    return [
        {
            key: (str(value) if isinstance(value, UUID) else value)
            for key, value in asdict(element).items()
        }
        for element in known
    ]


def load_elements(saved: Sequence[dict[str, Any]]) -> list[KnownElement]:
    def uuid_or_none(value: Any) -> UUID | None:
        return UUID(value) if value else None

    return [
        KnownElement(
            **{
                **item,
                "id": UUID(item["id"]),
                "synonyms": tuple(item["synonyms"]),
                "domain_id": uuid_or_none(item["domain_id"]),
                "range_id": uuid_or_none(item["range_id"]),
            }
        )
        for item in saved
    ]


def _names(element: KnownElement) -> set[str]:
    values = {element.label_zh, element.local_name, *element.synonyms}
    if element.label_en:
        values.add(element.label_en)
    return {normalize(value) for value in values if value}


def _ratio(hits: int, total: int) -> float | None:
    """None when there is nothing to divide by (no predictions, or no core entries)."""
    return round(hits / total, 3) if total else None


class ExpectedError(ValueError):
    """eval/expected.toml is malformed; the message names the entry."""


def check_expected(expected: Mapping[str, Any]) -> None:
    """Fails on the first malformed entry: a missing field, or an end that names no type."""
    types = expected.get("entity_types")
    if not types or not isinstance(types, list):
        raise ExpectedError("entity_types is missing or empty")
    first_names: set[str] = set()
    for index, entry in enumerate(types):
        if not entry.get("names") or not isinstance(entry.get("core"), bool):
            raise ExpectedError(f"entity_types[{index}] needs names and core")
        first_names.add(normalize(entry["names"][0]))
    ends = {
        "relations": ("domain", "range"),
        "properties": ("domain",),
        "hierarchy": ("child", "parent"),
    }
    for section, fields in ends.items():
        for index, entry in enumerate(expected.get(section, [])):
            if not isinstance(entry.get("core"), bool):
                raise ExpectedError(f"{section}[{index}] needs core")
            if section == "properties" and not entry.get("names"):
                raise ExpectedError(f"{section}[{index}] needs names")
            for field in fields:
                if normalize(str(entry.get(field, ""))) not in first_names:
                    raise ExpectedError(
                        f"{section}[{index}].{field} = {entry.get(field)!r} is not the first "
                        "name of an entity type"
                    )
    if "relations" not in expected:
        raise ExpectedError("relations is missing")


def score(
    known: Sequence[KnownElement],
    expected: dict[str, Any],
    parents: Mapping[UUID, UUID] | None = None,
) -> dict[str, Any]:
    groups = [{normalize(n) for n in group["names"]} for group in expected["entity_types"]]
    first_name = {normalize(g["names"][0]): i for i, g in enumerate(expected["entity_types"])}
    types = [e for e in known if e.kind == "entity_type"]
    group_of: dict[UUID, int | None] = {}
    for element in types:
        names = _names(element)
        group_of[element.id] = next((i for i, g in enumerate(groups) if names & g), None)

    core_types = [i for i, g in enumerate(expected["entity_types"]) if g["core"]]
    found_groups = {g for g in group_of.values() if g is not None}
    type_precision = sum(g is not None for g in group_of.values()) / len(types) if types else 0.0
    type_recall = sum(i in found_groups for i in core_types) / len(core_types)

    expected_pairs = [
        (
            frozenset({first_name[normalize(r["domain"])], first_name[normalize(r["range"])]}),
            r["core"],
        )
        for r in expected["relations"]
    ]
    relations = [e for e in known if e.kind == "relation_type"]
    predicted_pairs = [
        frozenset(
            {
                group_of.get(r.domain_id) if r.domain_id else None,
                group_of.get(r.range_id) if r.range_id else None,
            }
        )
        for r in relations
    ]
    valid_pairs = {pair for pair, _ in expected_pairs}
    relation_precision = (
        sum(pair in valid_pairs for pair in predicted_pairs) / len(relations) if relations else 0.0
    )
    core_pairs = [pair for pair, core in expected_pairs if core]
    relation_recall = sum(pair in set(predicted_pairs) for pair in core_pairs) / len(core_pairs)
    label = {element.id: element.label_zh for element in types}
    unmatched_relations = sorted(
        f"{label.get(r.domain_id, '?') if r.domain_id else '?'} → "
        f"{label.get(r.range_id, '?') if r.range_id else '?'}（{r.label_zh}）"
        for r, pair in zip(relations, predicted_pairs, strict=True)
        if pair not in valid_pairs
    )

    properties = [e for e in known if e.kind == "property"]
    hierarchy = [(child, parent) for child, parent in (parents or {}).items() if child in label]
    result: dict[str, Any] = {
        "entityTypes": {
            "predicted": len(types),
            "precision": round(type_precision, 3),
            "recall": round(type_recall, 3),
            "unmatched": sorted(e.label_zh for e in types if group_of[e.id] is None),
            "missedCore": [
                expected["entity_types"][i]["names"][0] for i in core_types if i not in found_groups
            ],
        },
        "relations": {
            "predicted": len(relations),
            "precision": round(relation_precision, 3),
            "recall": round(relation_recall, 3),
            "unmatched": unmatched_relations,
        },
        "properties": {"predicted": len(properties)},
        "hierarchy": {"predicted": len(hierarchy)},
    }
    if "properties" in expected:
        result["properties"] = _score_properties(
            properties, expected["properties"], first_name, group_of, label
        )
    if "hierarchy" in expected:
        result["hierarchy"] = _score_hierarchy(
            hierarchy, expected["hierarchy"], first_name, group_of, label
        )
    return result


def _score_properties(
    properties: Sequence[KnownElement],
    entries: Sequence[dict[str, Any]],
    first_name: Mapping[str, int],
    group_of: Mapping[UUID, int | None],
    label: Mapping[UUID, str],
) -> dict[str, Any]:
    """A property matches an entry when it belongs to the entry's type and shares a name."""
    wanted = [
        (first_name[normalize(e["domain"])], {normalize(n) for n in e["names"]}) for e in entries
    ]
    found: set[int] = set()
    matched = 0
    unmatched: list[str] = []
    for prop in properties:
        group = group_of.get(prop.domain_id) if prop.domain_id else None
        names = _names(prop)
        hits = [
            i
            for i, (owner, wanted_names) in enumerate(wanted)
            if group is not None and owner == group and names & wanted_names
        ]
        if hits:
            matched += 1
            found.update(hits)
        else:
            owner_label = label.get(prop.domain_id, "?") if prop.domain_id else "?"
            unmatched.append(f"{owner_label}.{prop.label_zh}")
    core = [i for i, entry in enumerate(entries) if entry["core"]]
    return {
        "predicted": len(properties),
        "precision": _ratio(matched, len(properties)),
        "recall": _ratio(sum(i in found for i in core), len(core)),
        "unmatched": sorted(unmatched),
        "missedCore": [
            f"{entries[i]['domain']}.{entries[i]['names'][0]}" for i in core if i not in found
        ],
    }


def _score_hierarchy(
    pairs: Sequence[tuple[UUID, UUID]],
    entries: Sequence[dict[str, Any]],
    first_name: Mapping[str, int],
    group_of: Mapping[UUID, int | None],
    label: Mapping[UUID, str],
) -> dict[str, Any]:
    """Child → parent pairs of expected types; unlike relations, direction counts."""
    wanted = [
        (first_name[normalize(e["child"])], first_name[normalize(e["parent"])]) for e in entries
    ]
    predicted = [(group_of.get(child), group_of.get(parent)) for child, parent in pairs]
    valid = set(wanted)
    core = [i for i, entry in enumerate(entries) if entry["core"]]
    return {
        "predicted": len(pairs),
        "precision": _ratio(sum(pair in valid for pair in predicted), len(pairs)),
        "recall": _ratio(sum(wanted[i] in set(predicted) for i in core), len(core)),
        "unmatched": sorted(
            f"{label.get(child, '?')} → {label.get(parent, '?')}"
            for (child, parent), pair in zip(pairs, predicted, strict=True)
            if pair not in valid
        ),
        "missedCore": [
            f"{entries[i]['child']} → {entries[i]['parent']}"
            for i in core
            if wanted[i] not in set(predicted)
        ],
    }


_COUNTS = ("calls", "replayed", "seconds", "inputTokens", "outputTokens")


def _usage(gateway: ReplayGateway) -> dict[str, Any]:
    """Model calls per document and stage, per stage, and in total."""
    documents = gateway.stats()
    stages: dict[str, dict[str, float]] = {}
    total = dict.fromkeys(_COUNTS, 0.0)
    for per_stage in documents.values():
        for purpose, numbers in per_stage.items():
            stage = stages.setdefault(purpose, dict.fromkeys(_COUNTS, 0.0))
            for key in _COUNTS:
                stage[key] += numbers[key]
                total[key] += numbers[key]

    def tidy(numbers: dict[str, float]) -> dict[str, Any]:
        return {
            key: round(value, 1) if key == "seconds" else int(value)
            for key, value in numbers.items()
        }

    return {
        "documents": documents,
        "stages": {purpose: tidy(numbers) for purpose, numbers in stages.items()},
        "total": tidy(total),
    }


async def run_case(
    files: Mapping[str, bytes], gateway: ReplayGateway, models: ExtractionModels
) -> dict[str, Any]:
    """Runs a case; without eval/expected.toml it only counts what was found (`scored` false)."""
    answers = files.get("eval/expected.toml")
    expected = tomllib.loads(answers.decode("utf-8")) if answers is not None else None
    if expected is not None:
        check_expected(expected)  # before paying for any call
    extractor = Extractor(gateway, models)
    known: list[KnownElement] = []
    parents: dict[UUID, UUID] = {}
    proposals_total = 0
    ungrounded = 0

    async def progress(step: str, done: int, total: int) -> None:
        log(f"    {step} {done}/{total}")

    for name in sorted(path for path in files if path.startswith("docs/")):
        data = files[name]
        parsed = parse_document(detect_type(name, data), data)
        if parsed.needs_vision:
            log(f"skip {name}: scanned PDF")
            continue
        document_id = stable_id("document", name)
        gateway.label(document_id, name)
        chunks = [
            ChunkText(
                id=stable_id("chunk", name, str(seq)),
                seq=seq,
                text=chunk.text,
                page=chunk.page,
                heading=chunk.heading,
            )
            for seq, chunk in enumerate(chunk_pages(parsed.pages))
        ]
        log(f"{name}: {len(chunks)} chunks, {sum(len(c.text) for c in chunks)} characters")
        started = time.monotonic()
        proposals = await extractor.run(
            document_id=document_id, title=name, chunks=chunks, known=known, progress=progress
        )
        log(f"    {time.monotonic() - started:.1f} s")
        proposals_total += len(proposals)
        ungrounded += sum("evidence_not_found" in p.flags for p in proposals)
        known = accept(known, proposals, parents)

    if expected is not None:
        result = {"scored": True, **score(known, expected, parents)}
    else:
        types = {e.id for e in known if e.kind == "entity_type"}
        result = {
            "scored": False,
            "entityTypes": {"predicted": len(types)},
            "relations": {"predicted": sum(e.kind == "relation_type" for e in known)},
            "properties": {"predicted": sum(e.kind == "property" for e in known)},
            "hierarchy": {"predicted": sum(child in types for child in parents)},
        }
    result["models"] = asdict(models)
    result["proposals"] = proposals_total
    result["groundedShare"] = (
        round(1 - ungrounded / proposals_total, 3) if proposals_total else None
    )
    result["usage"] = _usage(gateway)
    result["elements"] = dump_elements(known)
    result["parents"] = {str(child): str(parent) for child, parent in parents.items()}
    return result


def _models(settings: Settings, mode: str, manifest: str | None) -> ExtractionModels:
    if mode == "replay" and manifest:
        return ExtractionModels(**json.loads(manifest)["models"])
    return ExtractionModels(standard=settings.ai_model, reasoning=settings.ai_reasoning_model)


def _files(gateway: ReplayGateway, models: ExtractionModels) -> list[dict[str, str]]:
    files = [{"name": name, "content": text} for name, text in gateway.recording_files()]
    # Only a run that recorded something says which models the recordings are for: a run that
    # failed before its first answer (no key, wrong model) must not redirect later replays.
    if files:
        manifest = json.dumps({"models": asdict(models)}, indent=1)
        files.append({"name": MANIFEST, "content": manifest})
    return files


def evaluate(
    bundle: dict[str, Any], inner: ModelGateway | None = None
) -> tuple[dict[str, Any], int]:
    """Runs a bundle; returns the object for stdout and the exit code.

    `inner` is the gateway for calls that were not recorded ("record" only); by default the
    real one.
    """
    mode = bundle.get("mode", "record")
    if mode not in {"record", "replay"}:
        raise ValueError(f"Unknown mode: {mode}")
    settings = Settings()
    models = _models(settings, mode, bundle.get("manifest"))
    files = {path: base64.b64decode(value) for path, value in bundle["files"].items()}
    if mode == "replay":
        inner = None
    elif inner is None:
        inner = MeteredGateway(settings)
    recordings = load_recordings(
        bundle.get("recordings", []),
        on_invalid=lambda index: log(f"recording {index} is not readable, skipped"),
    )
    gateway = ReplayGateway(recordings, inner)
    try:
        result = asyncio.run(run_case(files, gateway, models))
    except (AiError, ReplayMissError, ExpectedError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        return {"error": error, "files": _files(gateway, models)}, 1
    except Exception as exc:
        traceback.print_exc()
        return {"error": type(exc).__name__, "files": _files(gateway, models)}, 1
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return {"result": text, "files": _files(gateway, models)}, 0


def main() -> int:
    bundle = json.loads(sys.stdin.read())
    if "--rescore" in sys.argv[1:]:
        known = load_elements(bundle["elements"])
        parents = {UUID(c): UUID(p) for c, p in bundle.get("parents", {}).items()}
        expected = tomllib.loads(bundle["expected"])
        print(json.dumps(score(known, expected, parents), ensure_ascii=False))
        return 0
    output, code = evaluate(bundle)
    print(json.dumps(output, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
