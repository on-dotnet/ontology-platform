"""Frozen review memory shared with extraction and evaluation."""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

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
    raise NotImplementedError


def apply_delta(
    memory: ReviewMemory, delta: MemoryDelta, *, now: datetime, max_entries: int
) -> ReviewMemory:
    raise NotImplementedError
