"""API models of the query module (spec 003 appendix, "对象查询")."""

from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    Field,
    StringConstraints,
    ValidationError,
    ValidatorFunctionWrapHandler,
    field_validator,
)

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.modules.ontology.schemas import FilterOp as FilterOp
from ontology_platform.modules.ontology.schemas import FilterValue as FilterValue
from ontology_platform.modules.ontology.schemas import ReleaseRef as ReleaseRef
from ontology_platform.schemas import CamelModel

FILTERS_MAX = 10
SORT_MAX = 2
IN_VALUES_MAX = 100
PAGE_DEFAULT = 50
PAGE_MAX = 200
CURSOR_MAX_LENGTH = 2048
KEY_MAX_LENGTH = 1024
QA_HOPS_MAX = 5

# Values in results: decimals are strings, to keep their precision.
type Scalar = str | int | bool
Direction = Literal["out", "in"]
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=CURSOR_MAX_LENGTH)]
TypeProblem = Literal["source_mismatch", "source_disabled"]


class Filter(CamelModel):
    property_id: UUID
    op: FilterOp
    # One value, the list of `in` (at most 100), or nothing for isNull / notNull.
    value: FilterValue | list[FilterValue] | None = None

    @field_validator("op", "value", mode="wrap")
    @classmethod
    def validate_operand(cls, value: object, handler: ValidatorFunctionWrapHandler) -> object:
        try:
            return handler(value)
        except ValidationError:
            # Bad operands raise AppError even in model_validate, bypassing validation.failed.
            raise AppError(422, "query.invalid_filter", "The filter is invalid.") from None


class Sort(CamelModel):
    property_id: UUID
    direction: Literal["asc", "desc"] = "asc"


class ObjectProperty(CamelModel):
    property_id: UUID
    label: str
    datatype: Datatype
    unit: str | None
    # The filter operators this property supports: its datatype and the type family of its
    # column decide (spec 003, 5.5). Every bound property can be sorted by.
    ops: list[FilterOp]


class ObjectRelation(CamelModel):
    relation_id: UUID
    label: str
    direction: Direction
    other_type_id: UUID
    other_type_label: str


class ObjectTypeInfo(CamelModel):
    type_id: UUID
    label: str
    local_name: str | None
    iri: str | None
    key_columns: list[str]
    # Set when this type cannot be queried right now; the other types are not affected.
    problem: TypeProblem | None
    # Only the bound properties.
    properties: list[ObjectProperty]
    relations: list[ObjectRelation]


class ObjectTypeList(CamelModel):
    release: ReleaseRef
    items: list[ObjectTypeInfo]


class ObjectSearch(CamelModel):
    type_id: UUID
    filters: list[Filter] = Field(default_factory=list, max_length=FILTERS_MAX)
    sort: list[Sort] = Field(default_factory=list, max_length=SORT_MAX)
    limit: int = Field(default=PAGE_DEFAULT, ge=1, le=PAGE_MAX)
    cursor: Cursor | None = None


class SourceKey(CamelModel):
    column: str
    value: str


class ObjectSource(CamelModel):
    """Where an object comes from: the data source, the table and the primary key."""

    data_source_id: UUID
    data_source_name: str
    schema_name: str = Field(alias="schema")
    table: str
    key: list[SourceKey]


class ObjectRow(CamelModel):
    type_id: UUID
    # URL-safe encoding of the primary key values; used in paths.
    key: str
    # Property id -> value; decimals are strings, to keep their precision.
    values: dict[UUID, Scalar | None]
    # Properties whose text was cut at the cell limit.
    truncated: list[UUID]
    source: ObjectSource


class ObjectPage(CamelModel):
    release: ReleaseRef
    type_id: UUID
    items: list[ObjectRow]
    next_cursor: str | None


class ObjectDetail(ObjectRow):
    release: ReleaseRef
    relations: list[ObjectRelation]


class PathHop(CamelModel):
    relation_id: UUID
    direction: Direction
    filters: list[Filter] = Field(default_factory=list, max_length=FILTERS_MAX)


class PathQuery(CamelModel):
    type_id: UUID
    filters: list[Filter] = Field(max_length=FILTERS_MAX)
    hops: list[PathHop] = Field(min_length=0, max_length=QA_HOPS_MAX)
    target: int | None = None
    limit: int = Field(default=PAGE_DEFAULT, ge=1, le=PAGE_MAX)


@dataclass(frozen=True)
class KeySet:
    type_id: UUID
    keys: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    type_id: UUID
    type_label: str
    conditions: tuple[str, ...]
    statements: int
    rows: int
    truncated: bool


class QueryStep(CamelModel):
    type_id: UUID
    type_label: str
    conditions: list[str]
    statements: int
    rows: int
    truncated: bool


StepOut = QueryStep


class PathRow(ObjectRow):
    via: list[str]


class PathResult(CamelModel):
    release: ReleaseRef
    type_id: UUID
    items: list[PathRow]
    total: int
    truncated: bool
    tail_type_id: UUID | None
    tail: list[PathRow]
    tail_total: int
    steps: list[StepOut]


@dataclass(frozen=True)
class ScanResult:
    release: ReleaseRef
    rows: tuple[ObjectRow, ...]
    steps: tuple[Step, ...]
