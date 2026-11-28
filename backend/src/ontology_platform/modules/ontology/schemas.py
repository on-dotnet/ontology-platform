"""API models of the ontology module.

Names and fields follow docs/specs/001-m1-api-shapes.md and 002-m2-api-shapes.md.
`ProposedItem`, `ElementFields` and `EvidenceIn` are also the Python interface through which
other modules propose changes.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
    model_validator,
)

from ontology_platform.errors import AppError, Problem
from ontology_platform.modules.ontology.models import (
    ChangeOp,
    ChangeSetSource,
    ChangeSetStatus,
    Datatype,
    Decision,
    ElementFlag,
    ElementStatus,
    EvidenceKind,
    ItemFlag,
    Kind,
    MatchDecision,
    MatchKind,
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


MetricAggregate = Literal["count", "sum", "avg", "min", "max", "ratio"]
FilterOp = Literal[
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "startsWith", "in", "isNull", "notNull"
]
type FilterValue = str | int | float | bool


class ReleaseRef(CamelModel):
    id: UUID
    version: int


class _MetricFilter(CamelModel):
    op: FilterOp
    value: FilterValue | list[FilterValue] | None = None


class MetricFilter(_MetricFilter):
    property_id: UUID


class MetricFilterFields(_MetricFilter):
    property_ref: Ref


class _MetricDefinition[FilterType](CamelModel):
    aggregate: MetricAggregate
    filters: list[FilterType] = Field(default_factory=list, max_length=10)
    numerator: list[FilterType] = Field(default_factory=list, max_length=10)
    decimals: int = Field(default=2, ge=0, le=6)
    percent: bool = False


class MetricDefinition(_MetricDefinition[MetricFilter]):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    property_id: UUID | None = None


class MetricDefinitionFields(_MetricDefinition[MetricFilterFields]):
    property_ref: Ref | None = None


# ---------- data bindings (spec 003, 6.2) ----------

KEY_COLUMNS_MAX = 8
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Columns = Annotated[list[Identifier], Field(min_length=1, max_length=KEY_COLUMNS_MAX)]


class ForeignKeyJoin(CamelModel):
    """`side = source`: the source table's `columns` refer to the target table's `references`;
    `side = target`: the other way round."""

    kind: Literal["foreign_key"]
    side: Literal["source", "target"]
    columns: Columns
    references: Columns


class LinkTableJoin(CamelModel):
    """A link table whose two column groups match the key columns of source and target."""

    kind: Literal["link_table"]
    schema_name: Identifier = Field(alias="schema")
    table: Identifier
    source_columns: Columns
    target_columns: Columns


Join = Annotated[ForeignKeyJoin | LinkTableJoin, Field(discriminator="kind")]


class TableBinding(CamelModel):
    """type_binding: an object type to a table or view and its key columns."""

    target: Literal["table"]
    data_source_id: UUID
    schema_name: Identifier = Field(alias="schema")
    table: Identifier
    key_columns: Columns


class ColumnBinding(CamelModel):
    """property_binding: a property to a column of its type binding's table."""

    target: Literal["column"]
    column: Identifier


class JoinBinding(CamelModel):
    """relation_binding: a relation to a foreign key or a link table."""

    target: Literal["join"]
    join: Join


Binding = Annotated[TableBinding | ColumnBinding | JoinBinding, Field(discriminator="target")]


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
    # Bindings: the element bound (an element id or temp_ref), and where it lives in the data.
    subject_ref: Ref | None = None
    binding: Binding | None = None
    metric: MetricDefinitionFields | None = None

    @field_validator("metric", mode="wrap")
    @classmethod
    def validate_metric(cls, value: object, handler: ValidatorFunctionWrapHandler) -> object:
        try:
            return handler(value)
        except ValidationError:
            raise AppError(422, "metric.invalid", "The metric definition is invalid.") from None


CatalogFact = Literal["table", "column", "primary_key", "foreign_key", "sample"]


class CatalogEvidenceSource(CamelModel):
    """Which fact of a data source's catalog a binding suggestion rests on (spec 003, 6.3)."""

    data_source_id: UUID
    schema_name: Identifier = Field(alias="schema")
    table: Identifier
    column: Identifier | None = None
    fact: CatalogFact


class EvidenceIn(CamelModel):
    """A passage of a document (`kind = document`) or a catalog fact (`kind = catalog`)."""

    kind: EvidenceKind = "document"
    document_id: UUID | None = None
    chunk_id: UUID | None = None
    source: CatalogEvidenceSource | None = None
    quote: str = Field(min_length=1, max_length=500)
    # Position in the chunk text; both null when the quote was not found.
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def fits_its_kind(self) -> Self:
        document = self.document_id is not None and self.chunk_id is not None
        if self.kind == "document" and (not document or self.source is not None):
            raise ValueError("Document evidence needs documentId and chunkId and no source")
        position = (self.document_id, self.chunk_id, self.char_start, self.char_end)
        if self.kind == "catalog" and (
            self.source is None or any(value is not None for value in position)
        ):
            raise ValueError("Catalog evidence needs a source and no document position")
        return self


class ProposedMatch(CamelModel):
    """An alignment record proposed with an item (spec 004, 4.3): exactly one of an element,
    an item of another open change set, or the temp_ref of an object type of this one."""

    kind: MatchKind
    element_id: UUID | None = None
    item_id: UUID | None = None
    temp_ref: Ref | None = None
    reason: str | None = Field(default=None, max_length=2000)


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
    match: ProposedMatch | None = None


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


class _ElementBase(CamelModel):
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
    # Default for snapshots of releases published before M3, which have no such key.
    binding: Binding | None = None
    status: ElementStatus
    origin: Origin
    revision: int
    created_at: datetime
    updated_at: datetime


AxiomCategory = Literal["shape", "logic", "individual", "parent", "annotation", "other"]


class Element(_ElementBase):
    metric: MetricDefinition | None = None
    axiom_category: AxiomCategory | None = None
    axiom_note: str | None = None


class SnapshotElement(Element):
    """Internal serialization shared by snapshots and RDF export."""

    axiom_category: AxiomCategory | None = Field(default=None, exclude=True)
    axiom_note: str | None = Field(default=None, exclude=True)


class ElementCopy(_ElementBase):
    """A copy of an element for other modules, which must not get the ORM row.

    Detached from the session, so changing it writes nothing; only the top level is frozen.
    """

    model_config = ConfigDict(frozen=True)


class Evidence(CamelModel):
    id: UUID
    kind: EvidenceKind
    document_id: UUID | None
    chunk_id: UUID | None
    source: CatalogEvidenceSource | None
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


class ItemResolution(CamelModel):
    """What a merge does with an item of an AI-extracted change set (spec 004, section 5).

    For an open change set this is the plan against the working version as it is now; for a
    merged one, what happened.
    """

    # into: the item's content goes into an existing element that is the same thing.
    # rename: created under another local name, the proposed one being taken.
    # update: additions to an element (synonyms, a definition where there is none).
    mode: Literal["create", "into", "rename", "update"]
    element_id: UUID | None
    element_label: str | None
    local_name: str | None
    # Fields (wire names) the element already has a value for; that value stays.
    kept_fields: list[str]


class ItemMatch(CamelModel):
    """An item's alignment record (spec 004, 5.5), or one synthesized from a merged item of
    another change set that recorded this item.

    The other side is an element (`elementId`) or a change item (`itemId`, with its change set).
    """

    kind: MatchKind
    element_id: UUID | None
    item_id: UUID | None
    change_set_id: UUID | None
    change_set_title: str | None
    label: str
    # The model's reason; None for a record of the write-time recheck.
    reason: str | None
    # The reviewer's conclusion, written on this item.
    decision: MatchDecision | None
    # The other item's reviewer kept the two apart: merging is not offered.
    kept_apart: bool


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
    axiom_category: AxiomCategory | None = None
    axiom_note: str | None = None
    decision: Decision
    reject_reason: Literal["out_of_scope", "incorrect", "duplicate", "keep_open"] | None
    confidence: float | None
    rationale: str | None
    flags: list[ItemFlag]
    note: str | None
    decided_by: UUID | None
    decided_at: datetime | None
    applied_element_id: UUID | None
    evidence: list[Evidence]
    resolution: ItemResolution | None
    match: ItemMatch | None


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
    # The submitter's display name; null when there is none or the user no longer exists.
    created_by_name: str | None
    created_at: datetime
    merged_at: datetime | None


class ChangeSetDetail(ChangeSetSummary):
    items: list[ChangeItem]
    suppressed: list["SuppressedItem"]
    suppressed_total: int
    # Digest of the items' resolutions; a merge sends it back (see `MergeRequest`).
    resolution_token: str


class BindingImpact(CamelModel):
    element_id: UUID
    kind: Literal["type_binding", "property_binding", "relation_binding"]
    label: str
    code: str
    message: str


class BindingImpacts(CamelModel):
    items: list[BindingImpact]


class ItemDecisionPatch(CamelModel):
    """Only the given keys change; `edited: null` drops the reviewer's edit."""

    decision: Decision | None = None
    reject_reason: Literal["out_of_scope", "incorrect", "duplicate", "keep_open"] | None = None
    edited: ElementFields | None = None
    note: str | None = Field(default=None, max_length=2000)
    # The reviewer's conclusion about the item's alignment record; null clears it.
    match_decision: MatchDecision | None = None


class BulkDecision(CamelModel):
    item_ids: list[UUID] = Field(max_length=5000)
    decision: Decision
    reject_reason: Literal["out_of_scope", "incorrect", "duplicate", "keep_open"] | None = None


class SuppressedItem(CamelModel):
    kind: Literal["entity_type", "relation_type", "property"]
    label_zh: str | None
    label_en: str | None
    cause: Literal["memory", "depends_on_suppressed"]
    memory_entry_id: UUID | None
    depends_on: str | None


class RejectedMemoryDetail(CamelModel):
    kind: Literal["rejected"] = "rejected"
    reason: Literal["out_of_scope", "incorrect", "duplicate", "keep_open"] | None
    label_en: str | None
    domain: str | None
    range: str | None


class RenamedMemoryDetail(CamelModel):
    kind: Literal["renamed"] = "renamed"
    to_label_zh: str
    to_label_en: str | None
    element_id: UUID


class KeptApartMemoryDetail(CamelModel):
    kind: Literal["kept_apart"] = "kept_apart"
    other_label: str
    other_element_id: UUID | None


class ReviewMemoryEntry(CamelModel):
    id: UUID
    ontology_id: UUID
    kind: Literal["rejected", "renamed", "kept_apart"]
    element_kind: Literal["entity_type", "relation_type", "property"]
    label: str
    detail: RejectedMemoryDetail | RenamedMemoryDetail | KeptApartMemoryDetail
    source_change_set_id: UUID | None
    source_item_id: UUID | None
    decided_by: UUID | None
    decided_by_name: str | None
    created_at: datetime
    hits: int
    last_hit_at: datetime | None


class ReviewMemoryPage(CamelModel):
    items: list[ReviewMemoryEntry]
    next_cursor: str | None
    total: int
    max: int


class ReviewMemoryClear(CamelModel):
    cleared: int


class MergeRequest(CamelModel):
    """`resolutionToken` of the change set detail the reviewer was shown.

    A merge that would do something else by now (another change set was merged meanwhile) is
    refused with 409 `changeset.resolution_changed`. Without a token, only a merge that
    behaves as merges did before there were resolutions is allowed.
    """

    resolution_token: str | None = Field(default=None, max_length=64)


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
    # Callers that list every dependency can reject the whole save if it affects another element.
    # A factory, not `= True`: openapi-typescript makes a field with a schema default required,
    # and existing callers omit this one.
    allow_cascade: bool = Field(
        default_factory=lambda: True,
        description="Defaults to true. False refuses a save whose deletes take unlisted elements.",
    )


class EditResult(CamelModel):
    change_set_id: UUID
    merged: bool
    merge: MergeResult | None


# ---------- the binding view of an object type (spec 003, 6.5 and 12.2) ----------

# How a binding compares with the cached catalog of its data source.
CatalogCheck = Literal[
    "ok", "missing_table", "missing_column", "type_mismatch", "catalog_unavailable"
]


class BoundDataSource(CamelModel):
    id: UUID
    name: str
    status: Literal["active", "archived"]


class TableBindingView(CamelModel):
    element_id: UUID
    revision: int
    data_source: BoundDataSource
    schema_name: str = Field(alias="schema")
    table: str
    key_columns: list[str]
    check: CatalogCheck


class ColumnBindingView(CamelModel):
    element_id: UUID
    revision: int
    column: str
    # The column's type in the cached catalog; null when the catalog does not have it.
    column_type: str | None
    check: CatalogCheck


class PropertyBindingView(CamelModel):
    property_id: UUID
    label: str
    datatype: Datatype | None
    # Defined on a parent type (or on no type), not on this one.
    inherited: bool
    column: ColumnBindingView | None


class JoinBindingView(CamelModel):
    element_id: UUID
    revision: int
    join: Join
    check: CatalogCheck


class RelationBindingView(CamelModel):
    relation_id: UUID
    label: str
    # out: the type is on the domain side; in: on the range side.
    direction: Literal["out", "in"]
    other_type_id: UUID
    other_type_label: str
    join: JoinBindingView | None


class TypeBindingView(CamelModel):
    """The bindings of one object type in the working version, checked against the cached
    catalog: its table, its properties (inherited and unbound ones included) and the bindings
    of the relations into and out of it."""

    type_id: UUID
    table: TableBindingView | None
    properties: list[PropertyBindingView]
    relations: list[RelationBindingView]
    # Open change sets with binding items for this type.
    open_change_set_ids: list[UUID]


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
    # Active bindings of the element (spec 003, 6.5); filled in by M3 batch 4a.
    bindings: list[ElementRef] = Field(default_factory=list)
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
    # Semantic elements; bindings are counted apart.
    element_count: int
    binding_count: int
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
