"""Frozen review memory shared with extraction and evaluation."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from ontology_platform.modules.ontology.models import (
    ChangeSetSource,
    Decision,
    MatchDecision,
    MatchKind,
)

MemoryKind = Literal["rejected", "renamed", "kept_apart"]
MemoryElementKind = Literal["entity_type", "relation_type", "property"]
RejectReason = Literal["out_of_scope", "incorrect", "duplicate", "keep_open"]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).lower()


def _main_name(label_zh: str | None, label_en: str | None) -> str:
    return _normalize(label_zh or "") or _normalize(label_en or "")


def type_key(label_zh: str | None, label_en: str | None) -> str:
    return "t:" + _main_name(label_zh, label_en)


# The parts of the keys below must already be main names (`_main_name`): raw labels never match.
def relation_key(domain: str, name: str, range_: str) -> str:
    return f"r:{domain}|{name}|{range_}"


def property_key(domain: str, name: str) -> str:
    return f"p:{domain}|{name}"


def pair_key(a: str, b: str) -> str:
    first, second = sorted((a, b))
    return f"k:{first}||{second}"


@dataclass(frozen=True)
class MemoryEntry:
    id: UUID
    kind: MemoryKind
    element_kind: MemoryElementKind
    key: str
    label: str
    reason: RejectReason | None
    label_en: str | None
    domain: str | None
    range: str | None
    to_label_zh: str | None
    to_label_en: str | None
    element_id: UUID | None
    other_label: str | None
    created_at: datetime
    last_hit_at: datetime | None


@dataclass(frozen=True)
class ReviewMemory:
    ontology_id: UUID
    entries: tuple[MemoryEntry, ...]

    def find(self, kind: MemoryKind, key: str) -> MemoryEntry | None:
        return next(
            (entry for entry in self.entries if entry.kind == kind and entry.key == key), None
        )


@dataclass(frozen=True)
class DecidedItem:
    item_id: UUID
    kind: str
    op: str
    decision: Decision
    reject_reason: RejectReason | None
    proposed_label_zh: str | None
    proposed_label_en: str | None
    final_label_zh: str | None
    final_label_en: str | None
    domain_label: str | None
    range_label: str | None
    created_element_id: UUID | None
    renamed_element_id: UUID | None
    match_kind: MatchKind | None
    match_decision: MatchDecision | None
    match_other_label: str | None
    match_other_element_id: UUID | None


@dataclass(frozen=True)
class NewEntry:
    kind: MemoryKind
    element_kind: MemoryElementKind
    key: str
    label: str
    detail: Mapping[str, object]
    source_item_id: UUID | None
    decided_by: UUID | None


@dataclass(frozen=True)
class MemoryDelta:
    upserts: tuple[NewEntry, ...]
    superseded_keys: tuple[tuple[MemoryElementKind, str], ...]


def collect(source: ChangeSetSource, items: Sequence[DecidedItem]) -> MemoryDelta:
    superseded: list[tuple[MemoryElementKind, str]] = []
    upserts: dict[tuple[MemoryKind, MemoryElementKind, str], NewEntry] = {}
    for item in items:
        if item.kind not in ("entity_type", "relation_type", "property"):
            continue
        kind: MemoryElementKind = item.kind  # type: ignore[assignment]
        name = _main_name(item.final_label_zh, item.final_label_en)
        domain = _main_name(item.domain_label, None)
        range_ = _main_name(item.range_label, None)
        if kind == "entity_type":
            key = type_key(item.final_label_zh, item.final_label_en)
        elif kind == "relation_type":
            key = relation_key(domain, name, range_)
        else:
            key = property_key(domain, name)
        if item.decision == "accepted" and (
            item.created_element_id is not None or item.renamed_element_id is not None
        ):
            superseded.append((kind, key))
        if source != "ai_extraction" or item.op != "create":
            continue
        label = item.proposed_label_zh or item.proposed_label_en or ""
        if (
            item.decision == "rejected"
            and item.reject_reason in (None, "out_of_scope", "incorrect")
            and item.match_kind is None
        ):
            proposed_name = _main_name(item.proposed_label_zh, item.proposed_label_en)
            rejected_key = (
                type_key(item.proposed_label_zh, item.proposed_label_en)
                if kind == "entity_type"
                else relation_key(domain, proposed_name, range_)
                if kind == "relation_type"
                else property_key(domain, proposed_name)
            )
            entry = NewEntry(
                "rejected",
                kind,
                rejected_key,
                label,
                {
                    "reason": item.reject_reason,
                    "labelEn": item.proposed_label_en,
                    "domain": item.domain_label,
                    "range": item.range_label,
                },
                item.item_id,
                None,
            )
            upserts[(entry.kind, kind, rejected_key)] = entry
        if item.decision != "accepted":
            continue
        if (
            kind == "entity_type"
            and item.created_element_id is not None
            and item.renamed_element_id is None
            and item.final_label_zh is not None
            and _main_name(item.final_label_zh, None) != _main_name(item.proposed_label_zh, None)
        ):
            entry = NewEntry(
                "renamed",
                kind,
                type_key(item.proposed_label_zh, item.proposed_label_en),
                label,
                {
                    "toLabelZh": item.final_label_zh,
                    "toLabelEn": item.final_label_en,
                    "elementId": str(item.created_element_id),
                },
                item.item_id,
                None,
            )
            upserts[(entry.kind, kind, entry.key)] = entry
        if (
            kind == "entity_type"
            and item.match_kind == "possible"
            and item.match_decision == "different"
            and item.match_other_label
        ):
            pair = pair_key(
                _main_name(item.final_label_zh, item.final_label_en),
                _main_name(item.match_other_label, None),
            )
            entry = NewEntry(
                "kept_apart",
                kind,
                pair,
                label,
                {
                    "otherLabel": item.match_other_label,
                    "otherElementId": str(item.match_other_element_id)
                    if item.match_other_element_id
                    else None,
                },
                item.item_id,
                None,
            )
            upserts[(entry.kind, kind, pair)] = entry
    return MemoryDelta(tuple(upserts.values()), tuple(dict.fromkeys(superseded)))


def apply_delta(
    memory: ReviewMemory, delta: MemoryDelta, *, now: datetime, max_entries: int
) -> ReviewMemory:
    entries = {
        (entry.kind, entry.element_kind, entry.key): entry
        for entry in memory.entries
        if not (
            entry.kind == "rejected" and (entry.element_kind, entry.key) in delta.superseded_keys
        )
    }
    for new in delta.upserts:
        key = (new.kind, new.element_kind, new.key)
        detail = new.detail
        entries[key] = MemoryEntry(
            id=entries[key].id if key in entries else uuid4(),
            kind=new.kind,
            element_kind=new.element_kind,
            key=new.key,
            label=new.label,
            reason=detail.get("reason") if new.kind == "rejected" else None,  # type: ignore[arg-type]
            label_en=detail.get("labelEn") if new.kind == "rejected" else None,  # type: ignore[arg-type]
            domain=detail.get("domain") if new.kind == "rejected" else None,  # type: ignore[arg-type]
            range=detail.get("range") if new.kind == "rejected" else None,  # type: ignore[arg-type]
            to_label_zh=detail.get("toLabelZh") if new.kind == "renamed" else None,  # type: ignore[arg-type]
            to_label_en=detail.get("toLabelEn") if new.kind == "renamed" else None,  # type: ignore[arg-type]
            element_id=UUID(str(detail["elementId"]))
            if new.kind == "renamed"
            else UUID(str(detail["otherElementId"]))
            if new.kind == "kept_apart" and detail.get("otherElementId")
            else None,
            other_label=detail.get("otherLabel") if new.kind == "kept_apart" else None,  # type: ignore[arg-type]
            created_at=now,
            last_hit_at=None,
        )
    newest = sorted(
        entries.values(),
        key=lambda entry: (entry.last_hit_at or entry.created_at, str(entry.id)),
        reverse=True,
    )
    return ReviewMemory(memory.ontology_id, tuple(newest[:max_entries]))
