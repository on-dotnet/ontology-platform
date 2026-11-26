from datetime import datetime
from typing import Annotated, Literal, NotRequired, TypedDict
from uuid import UUID

from pydantic import ConfigDict, Field, with_config

from ontology_platform.modules.ai.schemas import ReleaseRef
from ontology_platform.schemas import CamelModel

CqExpectKind = Literal["answerable", "objects", "number"]
CqResult = Literal["pending", "pass", "fail", "unanswerable", "error"]
QuestionText = Annotated[str, Field(min_length=1, max_length=500)]
QuestionNote = Annotated[str, Field(max_length=1000)]
ObjectKeys = Annotated[list[str], Field(max_length=100)]


# Optional input keys may be omitted. An explicit null is a different wire value.
@with_config(CamelModel.model_config)
class CqExpectInput(TypedDict):
    kind: CqExpectKind
    type_id: NotRequired[UUID]
    keys: NotRequired[ObjectKeys]
    number: NotRequired[str]
    tolerance: NotRequired[str]


@with_config(CamelModel.model_config)
class CompetencyQuestionCreate(TypedDict):
    text: QuestionText
    expect: CqExpectInput
    note: NotRequired[QuestionNote]


@with_config(CamelModel.model_config)
class CompetencyQuestionPatch(TypedDict):
    revision: Annotated[int, Field(ge=1)]
    text: NotRequired[QuestionText]
    expect: NotRequired[CqExpectInput]
    note: NotRequired[QuestionNote]
    position: NotRequired[int]


class CqExpect(CamelModel):
    kind: CqExpectKind
    type_id: UUID | None
    keys: ObjectKeys
    number: str | None
    tolerance: str


class CqCheckDetail(CamelModel):
    missing: list[str]
    extra: list[str]
    actual: str | None
    error_code: str | None


class CqCheck(CamelModel):
    id: UUID
    question_id: UUID
    release: ReleaseRef
    stale: bool
    qa_question_id: UUID
    result: CqResult
    detail: CqCheckDetail | None
    created_at: datetime
    finished_at: datetime | None


class CompetencyQuestion(CamelModel):
    id: UUID
    ontology_id: UUID
    text: str
    expect: CqExpect
    note: str | None
    position: int
    revision: int
    last_check: CqCheck | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CompetencyQuestionList(CamelModel):
    items: list[CompetencyQuestion]


class CqImportResult(CamelModel):
    created: int
    skipped: int


class CqCheckList(CamelModel):
    checks: list[CqCheck] = Field(max_length=50)


class CoverageElement(CamelModel):
    model_config = ConfigDict(frozen=True)

    id: UUID
    label: str
    present: bool
    bound: bool


class CoverageItem(CamelModel):
    model_config = ConfigDict(frozen=True)

    question_id: UUID
    status: Literal["ok", "element_missing", "binding_missing", "never_checked"]
    elements: list[CoverageElement]


class CqCoverage(CamelModel):
    release: ReleaseRef | None
    items: list[CoverageItem]
