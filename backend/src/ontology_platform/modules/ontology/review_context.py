"""Immutable input for review assistance."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ontology.models import (
    ChangeSetSource,
    Decision,
    ItemFlag,
    MatchDecision,
    MatchKind,
)
from ontology_platform.modules.ontology.review_memory import MemoryEntry


@dataclass(frozen=True)
class ReviewItem:
    id: UUID
    seq: int
    fingerprint: str
    kind: str
    op: str
    decision: Decision
    label_zh: str | None
    label_en: str | None
    local_name: str | None
    definition: str | None
    parent: str | None
    domain: str | None
    range: str | None
    flags: tuple[ItemFlag, ...]
    confidence: float | None
    has_evidence: bool
    quotes: tuple[str, ...]
    match_kind: MatchKind | None
    match_decision: MatchDecision | None
    match_other_label: str | None
    kept_fields: tuple[str, ...]
    target_stale: bool


@dataclass(frozen=True)
class ElementBrief:
    id: UUID
    kind: str
    label_zh: str | None
    label_en: str | None
    local_name: str
    parent: str | None
    domain: str | None
    range: str | None
    disjoint: tuple[str, ...]


@dataclass(frozen=True)
class ReviewContext:
    change_set_id: UUID
    ontology_id: UUID
    status: str
    source: ChangeSetSource
    items: tuple[ReviewItem, ...]
    elements: tuple[ElementBrief, ...]
    rejected: tuple[MemoryEntry, ...]


def item_fingerprint(
    kind: str,
    op: str,
    target_element_id: UUID | None,
    proposed: Mapping[str, object],
    edited: Mapping[str, object] | None,
) -> str:
    raise NotImplementedError


async def review_context(
    db: AsyncSession, change_set_id: UUID, *, elements_max: int = 400, memory_max: int = 60
) -> ReviewContext:
    raise NotImplementedError


async def item_fingerprints(db: AsyncSession, change_set_id: UUID) -> dict[UUID, str]:
    raise NotImplementedError
