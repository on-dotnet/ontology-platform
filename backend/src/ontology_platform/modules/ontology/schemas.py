"""API models of the ontology module.

Names and fields follow docs/specs/001-m1-api-shapes.md. `ProposedItem`, `ElementFields` and
`EvidenceIn` are also the Python interface through which other modules propose changes.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from ontology_platform.errors import Problem
from ontology_platform.modules.ontology.models import (
    ChangeOp,
    ChangeSetSource,
    ChangeSetStatus,
    Datatype,
    Decision,
    ElementStatus,
    ItemFlag,
    Kind,
    Origin,
)
from ontology_platform.schemas import CamelModel

KEY_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"

SkipCode = Literal[
    "changeset.stale_target",
    "changeset.dependency_skipped",
    "changeset.invalid_item",
]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class Synonym(CamelModel):
    lang: Literal["zh", "en"]
    text: str = Field(min_length=1, max_length=200)


class ElementFields(CamelModel):
    """Proposed or edited fields of an element; every field is optional.

    Which keys were given matters: only those are stored, returned and applied, and an explicit
    null clears a value. References (`parentRef`, `domainRef`, `rangeRef`) hold an element id or
    the `temp_ref` of a create item in the same change set. Rules that depend on the kind
    (required fields, naming, references) are checked by the service.
    """

    local_name: str | None = Field(default=None, max_length=128)
    label_zh: str | None = Field(default=None, max_length=200)
    label_en: str | None = Field(default=None, max_length=200)
    definition_zh: str | None = Field(default=None, max_length=4000)
    definition_en: str | None = Field(default=None, max_length=4000)
    synonyms: list[Synonym] | None = Field(default=None, max_length=100)
    parent_ref: Ref | None = None
    domain_ref: Ref | None = None
    range_ref: Ref | None = None
    datatype: Datatype | None = None
    unit: str | None = Field(default=None, max_length=32)
    required: bool | None = None
    multiple: bool | None = None


class EvidenceIn(CamelModel):
    document_id: UUID
    chunk_id: UUID
    quote: str = Field(min_length=1, max_length=500)
    # Position in the chunk text; both null when the quote was not found.
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)


class ProposedItem(CamelModel):
    """One proposed change, as passed to `service.create_change_set`."""

    op: ChangeOp
    kind: Kind
    target_element_id: UUID | None = None
    # Revision of the target the proposer read; defaults to the current one. A later merge
    # skips the item as stale when the element changed since.
    target_revision: int | None = Field(default=None, ge=1)
    temp_ref: Ref | None = None
    proposed: ElementFields
    confidence: float | None = Field(default=None, ge=0, le=1)
    rationale: str | None = None
    flags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceIn] = Field(default_factory=list)


# ---------- ontology ----------


class OntologySummary(CamelModel):
    id: UUID
    key: str
    name: str
    description: str | None
    base_iri: str
    entity_type_count: int
    relation_type_count: int
    property_count: int
    open_change_set_count: int
    active_release_id: UUID | None
    active_release_version: int | None
    created_at: datetime
    updated_at: datetime


class OntologyCreate(CamelModel):
    name: Name
    key: str | None = Field(default=None, pattern=KEY_PATTERN)
    description: str | None = Field(default=None, max_length=2000)


class Element(CamelModel):
    id: UUID
    ontology_id: UUID
    kind: Kind
    local_name: str
    iri: str
    label_zh: str
    label_en: str | None
    definition_zh: str | None
    definition_en: str | None
    synonyms: list[Synonym]
    parent_id: UUID | None
    domain_id: UUID | None
    range_id: UUID | None
    datatype: Datatype | None
    unit: str | None
    required: bool
    multiple: bool
    status: ElementStatus
    origin: Origin
    revision: int
    created_at: datetime
    updated_at: datetime


class Evidence(CamelModel):
    id: UUID
    document_id: UUID
    chunk_id: UUID
    quote: str
    char_start: int | None
    char_end: int | None


class Provenance(CamelModel):
    """A merged change item that created or modified an element."""

    change_set_id: UUID
    change_set_title: str
    item_id: UUID
    op: ChangeOp
    merged_at: datetime
    evidence: list[Evidence]


class ElementDetail(Element):
    provenance: list[Provenance]


class GraphNode(CamelModel):
    id: UUID
    label: str
    local_name: str
    parent_id: UUID | None
    property_count: int


class GraphEdge(CamelModel):
    id: str
    source: UUID
    target: UUID
    kind: Literal["relation", "subclass"]
    label: str | None


class Graph(CamelModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ---------- change sets ----------


class ChangeItem(CamelModel):
    # No defaults on purpose: change set routes drop unset fields so that `proposed`, `edited`
    # and `before` only carry the keys that were given, and every other field must be set.
    id: UUID
    seq: int
    op: ChangeOp
    kind: Kind
    target_element_id: UUID | None
    temp_ref: str | None
    proposed: ElementFields
    edited: ElementFields | None
    # For updates: the target element's current values, for comparison.
    before: ElementFields | None
    decision: Decision
    confidence: float | None
    rationale: str | None
    flags: list[ItemFlag]
    note: str | None
    decided_by: UUID | None
    decided_at: datetime | None
    applied_element_id: UUID | None
    evidence: list[Evidence]


class DecisionCounts(CamelModel):
    total: int
    pending: int
    accepted: int
    rejected: int


class ChangeSetSummary(CamelModel):
    id: UUID
    ontology_id: UUID
    title: str
    source: ChangeSetSource
    document_id: UUID | None
    status: ChangeSetStatus
    counts: DecisionCounts
    created_at: datetime
    merged_at: datetime | None


class ChangeSetDetail(ChangeSetSummary):
    items: list[ChangeItem]


class ItemDecisionPatch(CamelModel):
    """Only the given keys change; `edited: null` drops the reviewer's edit."""

    decision: Decision | None = None
    edited: ElementFields | None = None
    note: str | None = Field(default=None, max_length=2000)


class BulkDecision(CamelModel):
    item_ids: list[UUID] = Field(max_length=5000)
    decision: Decision


class MergeSkip(CamelModel):
    item_id: UUID
    code: SkipCode


class MergeResult(CamelModel):
    applied: int
    skipped: list[MergeSkip]


# ---------- releases ----------


class ReleaseSummary(CamelModel):
    id: UUID
    ontology_id: UUID
    version: int
    title: str
    notes: str | None
    element_count: int
    is_active: bool
    created_by: UUID | None
    created_at: datetime


class ReleaseCreate(CamelModel):
    title: Name
    notes: str | None = Field(default=None, max_length=4000)


class ReleaseProblem(CamelModel):
    code: str
    element_id: UUID | None
    message: str


class ReleaseInvalidProblem(Problem):
    """422 `release.invalid`: the working version failed the publish checks."""

    problems: list[ReleaseProblem]
