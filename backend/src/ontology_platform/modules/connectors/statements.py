"""The only form in which a read reaches a data source: a structured SELECT (spec 003, 5.1).

Other modules describe what to read with these frozen values and hand them to
`connectors.service.select`; the connector renders them with quoted identifiers and bound
parameters. There is deliberately no field that could carry SQL text.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

type Value = str | int | Decimal | bool | date | datetime | None
Operator = Literal[
    "eq", "ne", "lt", "le", "gt", "ge", "contains", "starts_with", "in", "is_null", "not_null"
]
# Which table of the query a column belongs to: the main one or the joined one.
Side = Literal["main", "joined"]


@dataclass(frozen=True, slots=True)
class TableRef:
    schema: str
    name: str


@dataclass(frozen=True, slots=True)
class ColumnRef:
    name: str
    side: Side = "main"


@dataclass(frozen=True, slots=True)
class Condition:
    column: ColumnRef
    operator: Operator
    # One value, the values of `in`, or None for `is_null` / `not_null`. Always sent as bound
    # parameters, typed by the connector from the column's source type.
    value: Value | tuple[Value, ...] = None


@dataclass(frozen=True, slots=True)
class SortKey:
    column: ColumnRef
    descending: bool = False


@dataclass(frozen=True, slots=True)
class Join:
    """An inner join of the main table with one other table on equal columns."""

    table: TableRef
    # (column of the main table, column of the joined table)
    on: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SelectQuery:
    data_source_id: UUID
    table: TableRef
    columns: tuple[ColumnRef, ...]
    join: Join | None = None
    where: tuple[Condition, ...] = ()
    order_by: tuple[SortKey, ...] = ()
    # Keyset pagination: the `order_by` values of the last row of the previous page.
    after: tuple[Value, ...] | None = None
    limit: int = 50


@dataclass(frozen=True, slots=True)
class Rows:
    """The result of one SELECT, in the order of `SelectQuery.columns`.

    Values are normalized to `Value` by the connector: uuid columns come back as `str`, real
    and double precision columns as `Decimal`, so that callers never see driver types.
    """

    rows: tuple[tuple[Value, ...], ...]
    # Whether more rows matched than `limit` let through.
    has_more: bool
    # (row index, column index) of text values cut at the cell limit.
    truncated: frozenset[tuple[int, int]] = frozenset()
