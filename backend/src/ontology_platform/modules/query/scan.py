"""Bounded keyset reads shared by scans and path traversal."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from itertools import batched
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import config
from ontology_platform.modules.connectors.schemas import CatalogColumn
from ontology_platform.modules.connectors.statements import (
    ColumnRef,
    Condition,
    Rows,
    SelectQuery,
    Value,
)
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.query import cursor, errors, planner, rows, schemas

QUERY_SECONDS = 60
STATEMENTS_MAX = 200
type Read = Callable[[AsyncSession, SelectQuery, Sequence[CatalogColumn]], Awaitable[Rows]]


@dataclass
class Budget:
    deadline: float
    statements: int = 0
    releases: dict[UUID, UUID] = field(default_factory=dict)

    def check_time(self) -> None:
        if asyncio.get_running_loop().time() >= self.deadline:
            raise AppError(504, "query.timeout", "The query timed out.")

    def charge(self) -> None:
        self.check_time()
        if self.statements >= STATEMENTS_MAX:
            raise AppError(422, "qa.too_many_queries", "The question requires too many queries.")
        self.statements += 1

    def pin(self, model: bindings.BoundModel) -> None:
        if self.releases.setdefault(model.ontology_id, model.release_id) != model.release_id:
            raise AppError(409, "query.release_changed", "The active release has changed.")


_budget: ContextVar[Budget | None] = ContextVar("query_budget", default=None)


@asynccontextmanager
async def query_budget() -> AsyncIterator[Budget]:
    """Wrap the query phase of a question to share its deadline, release and SELECT count."""
    current = _budget.get()
    if current is not None:
        current.check_time()
        yield current
        return
    budget = Budget(asyncio.get_running_loop().time() + QUERY_SECONDS)
    token = _budget.set(budget)
    try:
        async with asyncio.timeout_at(budget.deadline):
            yield budget
            budget.check_time()
    except TimeoutError:
        raise AppError(504, "query.timeout", "The query timed out.") from None
    finally:
        _budget.reset(token)


def check_size(size: int, maximum: int) -> None:
    if size > maximum:
        raise AppError(422, "query.too_many_rows", "Too many matching rows. Narrow the filters.")


@dataclass
class Execution:
    db: AsyncSession
    model: bindings.BoundModel
    catalog: planner.Catalog
    budget: Budget
    read: Read

    async def check_release(self) -> None:
        current = await bindings.bound_model(self.db, self.model.ontology_id)
        if current is None or current.release_id != self.model.release_id:
            raise AppError(409, "query.release_changed", "The active release has changed.")

    async def pages(self, query: SelectQuery) -> AsyncIterator[Rows]:
        slots = {column: i for i, column in enumerate(query.columns)}
        order = [slots[s.column] for s in query.order_by]
        while True:
            self.budget.charge()
            page = await self.read(self.db, query, ())
            yield page
            if not page.has_more:
                return
            last = len(page.rows) - 1
            if last < 0 or any((last, col) in page.truncated for col in order):
                raise errors.source_mismatch()
            after = tuple(page.rows[last][col] for col in order)
            if None in after or after == query.after:
                raise errors.source_mismatch()
            query = replace(query, after=after)
            await self.check_release()


_OPERATORS = {"eq": "=", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


def step(
    table: planner.Table, filters: Sequence[schemas.Filter], statements: int, count: int
) -> schemas.Step:
    labels = {prop.property_id: prop.label for prop in table.bound.properties}
    conditions = []
    for item in filters:
        operator = _OPERATORS.get(item.op, item.op)
        value = item.value
        operand = str(value).lower() if isinstance(value, bool) else str(value)
        label = f"{labels[item.property_id]} {operator}"
        conditions.append(label if value is None else f"{label} {operand}")
    return schemas.Step(
        table.bound.type_id, table.bound.label, tuple(conditions), statements, count, False
    )


def _within(table: planner.Table, within: schemas.KeySet | None) -> Iterator[tuple[Condition, ...]]:
    if within is None:
        yield ()
        return
    if within.type_id != table.bound.type_id:
        raise AppError(422, "query.invalid_filter", "The keys belong to a different type.")
    names = table.bound.key_columns
    specs = table.key_specs()
    for batch in batched(dict.fromkeys(within.keys), schemas.IN_VALUES_MAX, strict=False):
        # A tuple-IN is expressible as exact prefix conditions and an IN on the last column.
        groups: dict[tuple[Value, ...], list[Value]] = {}
        for key in batch:
            parts = cursor.decode_key(key, specs)
            groups.setdefault(parts[:-1], []).append(parts[-1])
        for prefix, suffixes in groups.items():
            yield (
                *planner.key_conditions(names[:-1], prefix),
                Condition(ColumnRef(names[-1]), "in", tuple(suffixes)),
            )


async def object_pages(
    execution: Execution,
    table: planner.Table,
    filters: Sequence[schemas.Filter],
    *,
    property_ids: Sequence[UUID] | None = None,
    within: schemas.KeySet | None = None,
) -> AsyncIterator[list[schemas.ObjectRow]]:
    where, order = planner.primary_key_terms(table, filters)
    projection = table
    if property_ids is not None:
        wanted = set(property_ids)
        properties = tuple(p for p in table.bound.properties if p.property_id in wanted)
        if len(properties) != len(wanted):
            raise AppError(422, "query.invalid_filter", "A requested property is not bound here.")
        projection = replace(table, bound=replace(table.bound, properties=properties))
    for restriction in _within(table, within):
        query = SelectQuery(
            data_source_id=table.bound.data_source_id,
            table=table.ref,
            columns=projection.projection(),
            where=where + restriction,
            order_by=order,
            limit=config.current().query_max_rows,
        )
        async for page in execution.pages(query):
            yield rows.objects(projection, query, page)
