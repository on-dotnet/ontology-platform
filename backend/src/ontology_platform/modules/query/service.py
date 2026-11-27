"""Browse objects through the bindings of the active release."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Sequence
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError, not_implemented
from ontology_platform.modules.connectors import config
from ontology_platform.modules.connectors import errors as connector_errors
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import CatalogColumn
from ontology_platform.modules.connectors.statements import ColumnRef, Rows, SelectQuery, SortKey
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.query import cursor as tokens
from ontology_platform.modules.query import errors, planner, rows, schemas
from ontology_platform.modules.query import scan as scanning
from ontology_platform.modules.query import traverse as traversal


async def until_disconnected[T](request: Request, work: Awaitable[T]) -> T:
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=0.25)
            if done:
                return task.result()
            if await request.is_disconnected():
                raise HTTPException(499, "The client disconnected.")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def serve_read[T](request: Request, operation: str, work: Awaitable[T]) -> T:
    """Internal callers see the service stub; HTTP clients receive a problem response."""
    try:
        return await until_disconnected(request, work)
    except NotImplementedError:
        raise not_implemented(operation) from None


async def _model(db: AsyncSession, ontology_id: UUID) -> bindings.BoundModel:
    model = await bindings.bound_model(db, ontology_id)
    if model is None:
        await ontology.get_ontology_summary(db, ontology_id)
        raise AppError(409, "query.no_release", "The ontology has no active release.")
    return model


def _release(model: bindings.BoundModel) -> schemas.ReleaseRef:
    return schemas.ReleaseRef(id=model.release_id, version=model.version)


async def list_types(db: AsyncSession, ontology_id: UUID) -> schemas.ObjectTypeList:
    model = await _model(db, ontology_id)
    catalog = planner.Catalog(db)
    relations = planner.relations(model, unusable=await planner.unusable_inverses(catalog, model))
    items = []
    for bound in model.types:
        table = await catalog.table(bound)
        items.append(
            schemas.ObjectTypeInfo(
                type_id=bound.type_id,
                label=bound.label,
                local_name=bound.local_name,
                iri=bound.iri,
                key_columns=list(bound.key_columns),
                problem=table.problem,
                properties=table.properties(),
                relations=relations.get(bound.type_id, []),
            )
        )
    return schemas.ObjectTypeList(release=_release(model), items=items)


async def _read(db: AsyncSession, query: SelectQuery, key_specs: Sequence[CatalogColumn]) -> Rows:
    try:
        return await connectors.select(db, query)
    except connector_errors.InvalidValueError as exc:
        raise errors.invalid_value(exc, key_specs, bool(query.where)) from None
    except connector_errors.SourceDisabledError:
        raise errors.source_disabled() from None
    except connector_errors.SourceMismatchError:
        raise errors.source_mismatch() from None
    except connector_errors.SourceUnavailableError:
        raise AppError(502, "query.source_unavailable", "The data source is unavailable.") from None
    except connector_errors.SourceBusyError:
        raise AppError(503, "query.busy", "The data source is busy.") from None
    except connector_errors.QueryTimeoutError:
        raise AppError(504, "query.timeout", "The query timed out.") from None


async def _page(
    db: AsyncSession,
    model: bindings.BoundModel,
    table: planner.Table,
    query: SelectQuery,
    context: dict[str, object],
    key_specs: Sequence[CatalogColumn] = (),
) -> schemas.ObjectPage:
    result = await _read(db, query, key_specs)
    return schemas.ObjectPage(
        release=_release(model),
        type_id=table.bound.type_id,
        items=rows.objects(table, query, result),
        next_cursor=rows.next_cursor(model.release_id, context, query, result),
    )


async def search(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.ObjectSearch,
) -> schemas.ObjectPage:
    model = await _model(db, ontology_id)
    context = tokens.search_context(body)
    position = tokens.read_page(body.cursor, model.release_id, context)
    table = await planner.Catalog(db).table(planner.bound_type(model, body.type_id))
    table.require_available()
    conditions, order = planner.search_terms(table, body)
    query = SelectQuery(
        data_source_id=table.bound.data_source_id,
        table=table.ref,
        columns=table.projection(),
        where=conditions,
        order_by=order,
        after=rows.after(position, table, order),
        limit=body.limit,
    )
    return await _page(db, model, table, query, context)


async def get_object(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    key: str,
) -> schemas.ObjectDetail:
    model = await _model(db, ontology_id)
    catalog = planner.Catalog(db)
    table = await catalog.table(planner.bound_type(model, type_id))
    table.require_available()
    key_specs = table.key_specs()
    parts = tokens.decode_key(key, key_specs)
    query = SelectQuery(
        data_source_id=table.bound.data_source_id,
        table=table.ref,
        columns=table.projection(),
        where=planner.key_conditions(table.bound.key_columns, parts),
        limit=1,
    )
    result = await _read(db, query, key_specs)
    if not result.rows:
        raise errors.object_not_found()
    if result.has_more:
        raise errors.source_mismatch()
    (row,) = rows.objects(table, query, result)
    unusable = await planner.unusable_inverses(catalog, model, type_id)
    return schemas.ObjectDetail(
        **row.model_dump(),
        release=_release(model),
        relations=planner.relations(model, type_id, unusable).get(type_id, []),
    )


async def related(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    key: str,
    *,
    relation_id: UUID,
    direction: schemas.Direction,
    limit: int,
    cursor: str | None,
) -> schemas.ObjectPage:
    if not 1 <= limit <= schemas.PAGE_MAX:
        raise AppError(422, "validation.failed", "The page size is out of range.")
    model = await _model(db, ontology_id)
    context: dict[str, object] = {
        "origin": str(type_id),
        "key": key,
        "relation": str(relation_id),
        "direction": direction,
    }
    position = tokens.read_page(cursor, model.release_id, context)
    catalog = planner.Catalog(db)
    origin = await catalog.table(planner.bound_type(model, type_id))
    origin.require_available()
    parts = tokens.decode_key(key, origin.key_specs())
    step = planner.resolve_relation(model, type_id, relation_id, direction)
    target = await catalog.table(step.other)
    target.require_available()
    join, names = planner.hop_join(origin, target, step.relation, step.direction)
    joined = await catalog.table_columns(target.bound.data_source_id, join.table)
    try:
        key_specs = [joined[name] for name in names]
    except KeyError:
        raise errors.source_mismatch() from None
    order = tuple(SortKey(ColumnRef(name)) for name in target.bound.key_columns)
    query = SelectQuery(
        data_source_id=target.bound.data_source_id,
        table=target.ref,
        columns=target.projection(),
        join=join,
        where=planner.joined_key(origin, parts, key_specs),
        order_by=order,
        after=rows.after(position, target, order),
        limit=limit,
    )
    return await _page(db, model, target, query, context, key_specs)


@asynccontextmanager
async def _execution(db: AsyncSession, ontology_id: UUID) -> AsyncIterator[scanning.Execution]:
    async with scanning.query_budget() as budget:
        model = await _model(db, ontology_id)
        budget.pin(model)
        execution = scanning.Execution(db, model, planner.Catalog(db), budget, _read)
        yield execution
        await execution.check_release()


async def traverse(
    db: AsyncSession, ontology_id: UUID, body: schemas.PathQuery, *, limit: int = 50
) -> schemas.PathResult:
    if not 1 <= limit <= schemas.PAGE_MAX:
        raise AppError(422, "validation.failed", "The page size is out of range.")
    async with _execution(db, ontology_id) as execution:
        walk = await traversal.walk(execution, body)
        return walk.result(_release(execution.model), limit)


async def traverse_keys(
    db: AsyncSession, ontology_id: UUID, body: schemas.PathQuery
) -> schemas.KeySet:
    async with _execution(db, ontology_id) as execution:
        walk = await traversal.walk(execution, body)
        return schemas.KeySet(walk.type_id, tuple(walk.paths))


async def scan(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    filters: Sequence[schemas.Filter],
    *,
    property_ids: Sequence[UUID],
    within: schemas.KeySet | None = None,
    max_rows: int,
) -> schemas.ScanResult:
    async with _execution(db, ontology_id) as execution:
        table = await execution.catalog.table(planner.bound_type(execution.model, type_id))
        table.require_available()
        maximum = min(max_rows, config.current().metric_rows_max)
        start = execution.budget.statements
        objects: list[schemas.ObjectRow] = []
        async for page in scanning.object_pages(
            execution, table, filters, property_ids=property_ids, within=within
        ):
            scanning.check_size(len(objects) + len(page), maximum)
            objects.extend(page)
        step = scanning.step(table, filters, execution.budget.statements - start, len(objects))
        return schemas.ScanResult(_release(execution.model), tuple(objects), (step,))
