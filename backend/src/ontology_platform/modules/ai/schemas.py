"""API models of the ai module."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from ontology_platform.modules.ai.models import (
    MESSAGE_MAX_LENGTH,
    AssistantStatus,
    AssistantStep,
    BindingSuggestionStep,
)
from ontology_platform.modules.metrics.schemas import MetricValue, RuleReport
from ontology_platform.modules.ontology.models import Kind
from ontology_platform.modules.query.schemas import (
    FILTERS_MAX,
    QA_HOPS_MAX,
    Filter,
    KeySet,
    PathHop,
    PathRow,
    StepOut,
)
from ontology_platform.modules.query.schemas import ReleaseRef as ReleaseRef
from ontology_platform.schemas import CamelModel


class AiStatus(CamelModel):
    configured: bool
    reachable: bool | None
    model: str | None


Locale = Literal["zh-CN", "en"]
AssistStatus = Literal["queued", "running", "done", "partial", "failed"]
RiskCode = Literal["weak_evidence", "conflict", "duplicate", "naming", "memory"]
RuleDetail = Literal[
    "evidence_not_found",
    "no_evidence",
    "low_confidence",
    "possible_duplicate",
    "undecided_match",
    "kept_fields",
    "stale_target",
    "local_name_style",
    "missing_label_en",
    "similar_to_rejected",
]
AssistSuggestion = Literal["accept", "reject", "edit", "unsure"]


class AssistRisk(CamelModel):
    code: RiskCode
    source: Literal["rule", "ai"]
    detail: RuleDetail | None
    reason: str | None = Field(max_length=300)
    related_item_ids: list[UUID] = Field(max_length=5)
    related_element_ids: list[UUID] = Field(max_length=5)
    memory_entry_id: UUID | None


class AssistRename(CamelModel):
    label_zh: str | None = None
    label_en: str | None = None
    local_name: str | None = None


class AssistItem(CamelModel):
    item_id: UUID
    stale: bool
    risks: list[AssistRisk]
    suggestion: AssistSuggestion | None
    reason: str | None = Field(max_length=300)
    rename: AssistRename | None


class AssistGroup(CamelModel):
    title: str = Field(max_length=40)
    item_ids: list[UUID]


class AssistCounts(CamelModel):
    total: int
    ai_reviewed: int
    with_risks: int
    suggest_reject: int
    suggest_edit: int
    stale: int
    dropped: int


class ReviewAssist(CamelModel):
    id: UUID
    change_set_id: UUID
    status: AssistStatus
    error_code: str | None
    ai_used: bool
    truncated: bool
    locale: Locale
    requested_by: UUID | None
    requested_by_name: str | None
    created_at: datetime
    finished_at: datetime | None
    summary: str | None = Field(max_length=600)
    groups: list[AssistGroup] = Field(max_length=12)
    items: list[AssistItem]
    counts: AssistCounts


class AssistRequest(CamelModel):
    locale: Locale


class ReviewAssistRiskOut(CamelModel):
    code: str
    reason: str
    related: list[str] = Field(default_factory=list)


class ReviewAssistGroupOut(CamelModel):
    title: str
    items: list[str]


class ReviewAssistItemOut(CamelModel):
    ref: str
    risks: list[ReviewAssistRiskOut]
    suggestion: str
    reason: str
    rename: AssistRename | None = None


class ReviewAssistOut(CamelModel):
    summary: str
    groups: list[ReviewAssistGroupOut]
    items: list[ReviewAssistItemOut]


class ReviewAssistGroupSource(CamelModel):
    batch: int
    group: int


class ReviewAssistSummaryGroupOut(CamelModel):
    title: str
    from_groups: list[ReviewAssistGroupSource] = Field(alias="from")


class ReviewAssistSummaryOut(CamelModel):
    summary: str
    groups: list[ReviewAssistSummaryGroupOut]


# ---------- AI assistant (spec 002 §10) ----------

Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX_LENGTH),
]
Page = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class AssistantContext(CamelModel):
    """Where the user was when they asked: the page and the element they had selected."""

    page: Page
    element_id: UUID | None = None


class AssistantRequestCreate(CamelModel):
    message: Message
    context: AssistantContext


class AssistantRequest(CamelModel):
    id: UUID
    ontology_id: UUID
    message: str
    context: AssistantContext
    status: AssistantStatus
    # The step running or reached: context, model, changeset.
    step: AssistantStep | None
    reply: str | None
    # Proposed operations left out because they failed the checks.
    dropped: int
    change_set_id: UUID | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


# ---------- AI binding suggestions (spec 003 §8) ----------

SUGGESTION_TABLES_MAX = 200
SUGGESTION_SCHEMAS_MAX = 50
SUGGESTION_TYPES_MAX = 300
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TableRef(CamelModel):
    schema_name: Identifier = Field(alias="schema")
    name: Identifier


class BindingSuggestionCreate(CamelModel):
    """Which tables to look at: `tables` or `schemas` (one of them), and optionally which
    object types to suggest bindings for (default: every type without a binding)."""

    data_source_id: UUID
    tables: list[TableRef] | None = Field(
        default=None, min_length=1, max_length=SUGGESTION_TABLES_MAX
    )
    schemas: list[Identifier] | None = Field(
        default=None, min_length=1, max_length=SUGGESTION_SCHEMAS_MAX
    )
    type_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=SUGGESTION_TYPES_MAX)

    @model_validator(mode="after")
    def one_scope(self) -> Self:
        if (self.tables is None) == (self.schemas is None):
            raise ValueError("Give exactly one of tables and schemas")
        return self


class BindingSuggestion(CamelModel):
    id: UUID
    ontology_id: UUID
    data_source_id: UUID
    status: AssistantStatus
    # The step running or reached: catalog, match, columns, changeset.
    step: BindingSuggestionStep | None
    # Null when no suggestion passed the checks.
    change_set_id: UUID | None
    proposed: int
    dropped: int
    samples_sent: bool
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


QaOrigin = Literal["user", "cq"]
QaStatus = Literal["queued", "running", "answered", "unanswerable", "failed"]
QaStep = Literal["plan", "check", "query", "answer", "done"]
QaIntent = Literal["objects", "count", "metric", "rules"]
QaNote = Literal["cited_unknown", "answer_unavailable", "rows_not_shared", "rows_truncated"]


class QaQuestionCreate(CamelModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class QaTypeRef(CamelModel):
    type_id: UUID
    label: str


class QaPlanStart(QaTypeRef):
    filters: list[Filter] = Field(max_length=FILTERS_MAX)


class QaPlanHop(PathHop):
    label: str
    target_type_id: UUID
    target_label: str


class QaPlan(CamelModel):
    intent: QaIntent
    start: QaPlanStart | None
    hops: list[QaPlanHop] = Field(max_length=QA_HOPS_MAX)
    target: int
    metric_id: UUID | None
    description: str
    assumptions: list[str]


class QaElementRef(CamelModel):
    id: UUID
    label: str


class QaMissingElement(CamelModel):
    kind: Literal["entity_type", "relation_type", "property", "metric"]
    label_zh: str
    description: str
    near: list[QaElementRef]


class QaGaps(CamelModel):
    elements: list[QaMissingElement]
    bindings: list[QaTypeRef]


class QaDocumentEvidence(CamelModel):
    document_id: UUID
    document_name: str
    chunk: int
    quote: str


class QaEvidenceElement(QaElementRef):
    kind: Kind
    iri: str | None
    documents: list[QaDocumentEvidence] = Field(max_length=2)


class QaEvidenceBinding(CamelModel):
    schema_name: str = Field(alias="schema")
    table: str
    key_columns: list[str]


class QaEvidence(CamelModel):
    release: ReleaseRef
    elements: list[QaEvidenceElement]
    bindings: list[QaEvidenceBinding]
    steps: list[StepOut]
    rows: list[PathRow] = Field(max_length=50)
    truncated: bool
    tail: list[PathRow] = Field(max_length=50)
    metric: MetricValue | None
    rules: RuleReport | None


class QaFactMetric(CamelModel):
    label: str
    display: str | None


class QaFactObject(QaTypeRef):
    key: str


class QaFacts(CamelModel):
    count: int | None
    metric: QaFactMetric | None
    objects: list[QaFactObject] = Field(max_length=50)
    violations: int | None


class QaAnswer(CamelModel):
    text: str | None
    facts: QaFacts
    cited_keys: list[str]
    counterpoints: list[str]
    notes: list[QaNote]


class QaGapProposal(CamelModel):
    status: Literal["queued", "running", "done", "empty", "failed"]
    change_set_id: UUID | None
    dropped: int
    error_code: str | None


class QaAsker(CamelModel):
    id: UUID
    display_name: str


class QaQuestion(CamelModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    ontology_id: UUID
    question: str
    origin: QaOrigin
    cq_question_id: UUID | None
    asked_by: QaAsker
    status: QaStatus
    step: QaStep | None
    release: ReleaseRef | None
    plan: QaPlan | None
    gaps: QaGaps | None
    answer: QaAnswer | None
    evidence: QaEvidence | None
    gap_proposal: QaGapProposal | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
    # Competency checks need every key, even when the evidence shown to users is truncated.
    answer_keys: KeySet | None = Field(default=None, exclude=True, repr=False)


class QaQuestionList(CamelModel):
    items: list[QaQuestion]
    next_cursor: str | None
