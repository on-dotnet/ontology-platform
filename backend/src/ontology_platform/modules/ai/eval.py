"""Extraction quality on a case pack: `python -m ontology_platform.modules.ai.eval`.

Reads a JSON bundle on stdin: {"files": {"docs/<name>": "<base64>", "eval/expected.toml": ...}}.
Runs the real model over every document in order, accepting every proposal so that later
documents align with what earlier ones produced, then scores entity types and relations
against eval/expected.toml (format documented in that file). Progress goes to stderr, the
result as JSON to stdout. This spends model tokens, so it is not part of CI.
"""

import asyncio
import base64
import json
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    Proposal,
    normalize,
)
from ontology_platform.modules.ai.gateway import OpenAIGateway
from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import detect_type, parse_document
from ontology_platform.settings import Settings


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def accept(known: list[KnownElement], proposals: Sequence[Proposal]) -> list[KnownElement]:
    """Apply proposals as if a reviewer accepted all of them."""
    result = list(known)
    temp: dict[str, UUID] = {}
    for proposal in proposals:
        if proposal.op == "create" and proposal.temp_ref:
            temp[proposal.temp_ref] = uuid4()

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
        element_id = temp.get(proposal.temp_ref or "") or uuid4()
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


def _names(element: KnownElement) -> set[str]:
    values = {element.label_zh, element.local_name, *element.synonyms}
    if element.label_en:
        values.add(element.label_en)
    return {normalize(value) for value in values if value}


def score(known: Sequence[KnownElement], expected: dict[str, Any]) -> dict[str, Any]:
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

    return {
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
        },
        "properties": sum(e.kind == "property" for e in known),
    }


async def evaluate(files: dict[str, bytes]) -> dict[str, Any]:
    settings = Settings()
    expected = tomllib.loads(files["eval/expected.toml"].decode("utf-8"))
    extractor = Extractor(
        OpenAIGateway(settings),
        ExtractionModels(standard=settings.ai_model, reasoning=settings.ai_reasoning_model),
    )
    known: list[KnownElement] = []
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
        chunks = [
            ChunkText(id=uuid4(), seq=seq, text=chunk.text, page=chunk.page, heading=chunk.heading)
            for seq, chunk in enumerate(chunk_pages(parsed.pages))
        ]
        log(f"{name}: {len(chunks)} chunks")
        proposals = await extractor.run(
            document_id=uuid4(), title=name, chunks=chunks, known=known, progress=progress
        )
        proposals_total += len(proposals)
        ungrounded += sum("evidence_not_found" in p.flags for p in proposals)
        known = accept(known, proposals)

    result = score(known, expected)
    result["models"] = {"standard": settings.ai_model, "reasoning": settings.ai_reasoning_model}
    result["proposals"] = proposals_total
    result["groundedShare"] = (
        round(1 - ungrounded / proposals_total, 3) if proposals_total else None
    )
    return result


def main() -> int:
    bundle = json.loads(sys.stdin.read())
    files = {path: base64.b64decode(value) for path, value in bundle["files"].items()}
    result = asyncio.run(evaluate(files))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
