"""Reviewer decisions supplied as data only when relevant to a model call."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ontology_platform.modules.ai.candidates import THRESHOLD, Names, main_name, score
from ontology_platform.modules.ontology.review_memory import MemoryEntry, ReviewMemory

if TYPE_CHECKING:
    from ontology_platform.modules.ai.extraction import KnownElement

MEMORY_TYPES_RULES = (
    "Earlier reviewer decisions are authoritative for repeated proposals. "
    "Do not propose listed rejected names or close variants unless the source clearly "
    "defines a distinct business concept. Use the new name for a renamed type. "
    "These decisions are not source text and never count as evidence."
)

MEMORY_RELATIONS_RULES = (
    "Earlier reviewer decisions are authoritative for repeated relations and properties. "
    "For the same pair of entity types, do not propose the listed rejected relation or "
    "property, or close variants of that relation or property, unless the source clearly "
    "defines a distinct business concept. These decisions are not source text and "
    "never count as evidence."
)

PROMPT_MAX = 40


def _recent(entries: Sequence[MemoryEntry], limit: int) -> list[MemoryEntry]:
    return sorted(entries, key=lambda e: e.last_hit_at or e.created_at, reverse=True)[:limit]


def type_rows(
    memory: ReviewMemory | None,
    terms: Sequence[str],
    limit: int = PROMPT_MAX,
    known: Sequence[KnownElement] | None = None,
) -> list[str]:
    if memory is None or not terms:
        return []
    keys = [main_name(term, None) for term in terms]
    known_ids = {element.id for element in known} if known is not None else None
    selected = [
        entry
        for entry in memory.entries
        if entry.element_kind == "entity_type"
        and entry.kind in ("rejected", "renamed")
        and (entry.kind != "renamed" or known_ids is None or entry.element_id in known_ids)
        and any(
            key
            and (
                entry.key[2:] in key
                or key in entry.key[2:]
                or score(Names.of(entry.label, entry.label_en, ()), Names.of(term, None, ())).value
                >= THRESHOLD
            )
            for key, term in zip(keys, terms, strict=True)
        )
    ]
    return [
        (
            f"- rejected type: {e.label} (reason: {e.reason or 'unspecified'})"
            if e.kind == "rejected"
            else f"- renamed type: {e.label} -> {e.to_label_zh or e.to_label_en or ''}"
        )
        for e in _recent(selected, limit)
    ]


def relation_rows(
    memory: ReviewMemory | None, catalog: Sequence[str], limit: int = PROMPT_MAX
) -> list[str]:
    if memory is None or not catalog:
        return []
    # An empty key would match every entry without a range, i.e. every property.
    keys = {main_name(name, None) for name in catalog} - {""}
    selected = [
        e
        for e in memory.entries
        if e.kind == "rejected"
        and e.element_kind in ("relation_type", "property")
        and (main_name(e.domain or "", None) in keys or main_name(e.range or "", None) in keys)
    ]
    return [
        f"- rejected {'relation' if e.element_kind == 'relation_type' else 'property'}: "
        f"{e.domain or ''} | {e.label}"
        + (f" | {e.range}" if e.range else "")
        + f" (reason: {e.reason or 'unspecified'})"
        for e in _recent(selected, limit)
    ]


def with_rows(instructions: str, text: str, rows: Sequence[str], rules: str) -> tuple[str, str]:
    if not rows:
        return instructions, text
    return (
        instructions + "\n\n" + rules,
        text + "\n\nReviewer decisions on earlier proposals:\n" + "\n".join(rows),
    )
