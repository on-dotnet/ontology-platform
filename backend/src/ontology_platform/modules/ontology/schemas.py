"""API models of the ontology module.

Names and fields follow docs/specs/001-m1-api-shapes.md and 002-m2-api-shapes.md.
`ProposedItem`, `ElementFields` and `EvidenceIn` are also the Python interface through which
other modules propose changes.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from ontology_platform.errors import Problem
from ontology_platform.modules.ontology.models import (
    ChangeOp,
    ChangeSetSource,
    ChangeSetStatus,
    Datatype,
    Decision,
    ElementFlag,
    ElementStatus,
    ItemFlag,
    Kind,
    Origin,
)
from ontology_platform.schemas import CamelModel

KEY_PATTERN = r"^[a-z][a-z0-9-]{1,62}$"
IRI_MAX_LENGTH = 2048
# One axiom; the file it comes from is at most 5 MB.
TURTLE_MAX_LENGTH = 2_000_000
SYNONYMS_MAX = 100
RULES_MAX = 200
ALLOWED_VALUES_MAX = 1000
PATTERN_MAX = 2000
FLAGS_MAX = 16
MESSAGES_MAX = 20
MESSAGE_MAX = 2000
LEXICAL_MAX = 4000
LANG_MAX = 35

SkipCode = Literal[
    "changeset.stale_target",
    "changeset.dependency_skipped",
    "changeset.invalid_item",
    "changeset.has_dependents",
]
NodeKind = Literal[
    "IRI",
    "Literal",
    "BlankNode",
    "BlankNodeOrIRI",
    "BlankNodeOrLiteral",
    "IRIOrLiteral",
]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Ref = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class Synonym(CamelModel):
    lang: Literal["zh", "en"]
    text: str = Field(min_length=1, max_length=200)


class RdfValue(CamelModel):
    """An RDF value as written: an IRI, or a literal with its exact spelling.

    `datatype` is an XSD local name (such as "integer") or a full IRI; null for plain text.
    """

    iri: str | None = Field(default=None, max_length=IRI_MAX_LENGTH)
    lexical: str | None = Field(default=None, max_length=LEXICAL_MAX)
    datatype: str | None = Field(default=None, max_length=IRI_MAX_LENGTH)
    lang: str | None = Field(default=None, max_length=LANG_MAX)

    @model_validator(mode="after")
    def _one_kind(self) -> Self:
        if (self.iri is None) == (self.lexical is None):
            raise ValueError("give either iri or lexical")
        if self.iri is not None and (self.datatype is not None or self.lang is not None):
            raise ValueError("an IRI has no datatype or language")
        return self


class LangText(CamelModel):
    lang: str | None = Field(default=None, max_length=LANG_MAX)
    text: str = Field(min_length=1, max_length=MESSAGE_MAX)


class _RuleValues(CamelModel):
    """The checks of one sh:property (spec 002, 3.3), without the references."""

    min_count: int | None = Field(default=None, ge=0)
    max_count: int | None = Field(default=None, ge=0)
    datatype: str | None = Field(default=None, max_length=IRI_MAX_LENGTH)
    node_kind: NodeKind | None = None
    # sh:in. `allowedValuesLost` marks a list Protégé dropped (sh:in points at nothing).
    allowed_values: list[RdfValue] | None = Field(default=None, max_length=ALLOWED_VALUES_MAX)
    allowed_values_lost: bool = False
    min_inclusive: RdfValue | None = None
    max_inclusive: RdfValue | None = None
    min_exclusive: RdfValue | None = None
    max_exclusive: RdfValue | None = None
    min_length: int | None = Field(default=None, ge=0)
    max_length: int | None = Field(default=None, ge=0)
    pattern: str | None = Field(default=None, max_length=PATTERN_MAX)
    flags: str | None = Field(default=None, max_length=FLAGS_MAX)
    message: list[LangText] = Field(default_factory=list, max_length=MESSAGES_MAX)


class ConstraintRule(_RuleValues):
    path_id: UUID
    class_id: UUID | None = None


class ConstraintRuleFields(_RuleValues):
    """A rule in a change item: references are element ids or temp_refs."""

    path_ref: Ref
    class_ref: Ref | None = None


class ElementFields(CamelModel):
    """Proposed or edited fields of an element; every field is optional.

    Which keys were given matters: only those are stored, returned and applied, and an explicit
    null clears a value. References (`parentRef`, `domainRef`, `rangeRef`, `inverseRef` and the
    rules' `pathRef` / `classRef`) hold an element id or the `temp_ref` of a create item in the
    same change set. Rules that depend on the kind (required fields, naming, references) are
    checked by the service.
    """

    local_name: str | None = Field(default=None, max_length=128)
    # Only for elements brought by an import; elements made in the platform derive their IRI.
    iri: str | None = Field(default=None, max_length=IRI_MAX_LENGTH)
    label_zh: str | None = Field(default=None, max_length=200)
    label_en: str | None = Field(default=None, max_length=200)
    definition_zh: str | None = Field(default=None, max_length=4000)
    definition_en: str | None = Field(default=None, max_length=4000)
    synonyms: list[Synonym] | None = Field(default=None, max_length=SYNONYMS_MAX)
    parent_ref: Ref | None = None
    domain_ref: Ref | None = None
    range_ref: Ref | None = None
    inverse_ref: Ref | None = None
    datatype: Datatype | None = None
    unit: str | None = Field(default=None, max_length=32)
    required: bool | None = None
    multiple: bool | None = None
    auto_shape: bool | None = None
    rules: list[ConstraintRuleFields] | None = Field(default=None, max_length=RULES_MAX)
    turtle: str | None = Field(default=None, max_length=TURTLE_MAX_LENGTH)


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
    ontology_iri: str
    entity_type_count: int
    relation_type_count: int
    property_count: int
    constraint_count: int
    axiom_count: int
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
    # Null for axioms, which have no IRI of their own.
    local_name: str | None
    iri: str | None
    # True when the IRI came with an import rather than from baseIri + localName.
    explicit_iri: bool
    label_zh: str | None
    label_en: str | None
    definition_zh: str | None
    definition_en: str | None
    synonyms: list[Synonym]
    parent_id: UUID | None
    domain_id: UUID | None
    range_id: UUID | None
    inverse_id: UUID | None
    datatype: Datatype | None
    unit: str | None
    required: bool
    multiple: bool
    # Whether required / multiple are exported in the platform's generated SHACL shape.
    auto_shape: bool
    rules: list[ConstraintRule] | None
    turtle: str | None
    subject_id: UUID | None
    flags: list[ElementFlag]
    status: ElementStatus
    origin: Origin
    revision: int
    created_at: datetime
    updated_at: datetime


class ElementCopy(Element):
    """A read-only copy of an element for other modules, which must not get the ORM row."""

    model_config = ConfigDict(frozen=True)


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
    local_name: str | None
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
    # Who submitted it (for AI change sets, who uploaded or asked); null for system work. In
    # separate review mode they may withdraw it but not decide it.
    created_by: UUID | None
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


# ---------- import ----------

ImportWarningCode = Literal[
    "non_standard",
    "multiple_parents",
    "unsupported_shape",
    "lost_list",
    "kind_changed",
]


class ImportCounts(CamelModel):
    create: int
    update: int
    delete: int
    restore: int


class ImportWarning(CamelModel):
    code: ImportWarningCode
    count: int


class ImportResult(CamelModel):
    ontology: OntologySummary
    # Null when the file holds nothing the ontology does not already have.
    change_set_id: UUID | None
    counts: ImportCounts
    warnings: list[ImportWarning]


class ImportParseProblem(Problem):
    """422 `import.parse_error`: where the file stopped being valid, when known."""

    line: int | None
    column: int | None


# ---------- manual edits, impact, expert mode (PR B) ----------

EDIT_ITEMS_MAX = 500


class EditItem(CamelModel):
    """One change made by hand. update, delete and restore name their target and the revision
    the user read (409 `element.stale` when it moved on)."""

    op: ChangeOp
    kind: Kind
    target_element_id: UUID | None = None
    target_revision: int | None = Field(default=None, ge=1)
    temp_ref: Ref | None = None
    fields: ElementFields = Field(default_factory=ElementFields)

    @model_validator(mode="after")
    def check_target(self) -> Self:
        if self.op == "create":
            if self.target_element_id is not None or self.target_revision is not None:
                raise ValueError("A create has no target.")
        elif self.target_element_id is None or self.target_revision is None:
            raise ValueError("update, delete and restore need targetElementId and targetRevision.")
        return self


class EditRequest(CamelModel):
    items: list[EditItem] = Field(min_length=1, max_length=EDIT_ITEMS_MAX)
    # Merge at once when the user may review their own changes (spec 002, section 6).
    apply: bool = False


class EditResult(CamelModel):
    change_set_id: UUID
    merged: bool
    merge: MergeResult | None


class ElementRef(CamelModel):
    id: UUID
    kind: Kind
    label: str
    iri: str | None


class CascadeChange(CamelModel):
    """What deleting an element does to another one: delete it, or update it to let go."""

    op: Literal["delete", "update"]
    element: ElementRef


class Impact(CamelModel):
    """Active elements that refer to one element (spec 002, section 9), and everything a delete
    of it would change, transitively, as a manual save proposes it (section 6)."""

    element_id: UUID
    subtypes: list[ElementRef]
    relations: list[ElementRef]
    properties: list[ElementRef]
    constraints: list[ElementRef]
    axioms: list[ElementRef]
    inverse: ElementRef | None
    cascade: list[CascadeChange]


class TurtleEdit(CamelModel):
    """The whole working version as edited in expert mode."""

    turtle: str = Field(min_length=1, max_length=5 * 1024 * 1024)


ChangeLevel = Literal["breaking", "review", "compatible"]


class FieldChange(CamelModel):
    """One field of an element in two versions. `field` is the Element field name (camelCase);
    references are {id, label} objects, rules and synonyms are given whole."""

    field: str
    before: Any
    after: Any


class ElementChange(CamelModel):
    element_id: UUID
    kind: Kind
    label: str
    iri: str | None
    change: Literal["added", "removed", "changed", "restored"]
    level: ChangeLevel
    # Only for changed and restored elements.
    fields: list[FieldChange]


class CompareSide(CamelModel):
    # Null for the working version.
    release_id: UUID | None
    version: int | None


class CompareCounts(CamelModel):
    breaking: int
    review: int
    compatible: int


class Comparison(CamelModel):
    """What changed from one release to another release or to the working version (spec 002,
    section 9), most severe first."""

    from_: CompareSide = Field(alias="from")
    to: CompareSide
    changes: list[ElementChange]
    counts: CompareCounts


ReviewMode = Literal["single", "separate"]


class PlatformSettings(CamelModel):
    review_mode: ReviewMode


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
