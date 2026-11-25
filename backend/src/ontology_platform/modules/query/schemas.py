"""API models of the query module (spec 003 appendix, "对象查询")."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.schemas import CamelModel

FILTERS_MAX = 10
SORT_MAX = 2
IN_VALUES_MAX = 100
PAGE_DEFAULT = 50
PAGE_MAX = 200
CURSOR_MAX_LENGTH = 2048
KEY_MAX_LENGTH = 1024

# Values in results: decimals are strings, to keep their precision.
type Scalar = str | int | bool
# Values in filters may also be JSON numbers with a fraction (agents send them as such); the
# platform turns them into decimals and checks them against the column's type family.
type FilterValue = str | int | float | bool
FilterOp = Literal[
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "startsWith", "in", "isNull", "notNull"
]
Direction = Literal["out", "in"]
Cursor = Annotated[str, StringConstraints(min_length=1, max_length=CURSOR_MAX_LENGTH)]
TypeProblem = Literal["source_mismatch", "source_disabled"]


class ReleaseRef(CamelModel):
    id: UUID
    version: int


class Filter(CamelModel):
    property_id: UUID
    op: FilterOp
    # One value, the list of `in` (at most 100), or nothing for isNull / notNull.
    value: FilterValue | list[FilterValue] | None = None


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
