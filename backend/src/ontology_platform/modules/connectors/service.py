"""Data sources, their cached catalog and read-only access to them (spec 003, section 5).

Only this module may open connections to external data sources or write SQL text; everyone
else calls the functions below. The skeleton fixes their shape: the two small reads other
modules build on (`get_data_source_ref`, `get_catalog_table`) and the usage provider registry
work already, everything else arrives with batch 3.

The HTTP operations commit their own transaction; the functions other modules call never do.
"""

import base64
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation
from pydantic.alias_generators import to_camel
from sqlalchemy import func, literal, or_, tuple_
from sqlalchemy import select as sql_select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.connectors import config, connection, jobs, schemas, secrets
from ontology_platform.modules.connectors.errors import PlatformDatabaseError, SourceDisabledError
from ontology_platform.modules.connectors.models import (
    IDENTIFIER_MAX_LENGTH,
    CatalogTable,
    DataSource,
)
from ontology_platform.modules.connectors.statements import Rows, SelectQuery, TableRef, Value
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.jobs import service as queue


@dataclass(frozen=True, slots=True)
class TableUsage:
    """An object type bound to a table of a data source."""

    schema: str
    table: str
    type_id: UUID
    type_label: str
    # Bound in an ontology's working version / in the release that is in effect.
    in_working_version: bool
    in_active_release: bool


# The ontology module knows which tables are bound; connectors must not import it (the
# dependency runs ontology -> connectors only), so main.py and worker.py register its answer
# here, as documents does with its extractor.
type UsageProvider = Callable[[AsyncSession, UUID], Awaitable[list[TableUsage]]]
_usage_provider: UsageProvider | None = None


def register_usage_provider(provider: UsageProvider | None) -> None:
    global _usage_provider
    _usage_provider = provider


async def table_usage(db: AsyncSession, data_source_id: UUID) -> list[TableUsage] | None:
    """The bindings that use the data source, or None when nobody can tell. Callers must treat
    None as "may be in use": archiving is refused, counts are shown as unknown."""
    if _usage_provider is None:
        return None
    return await _usage_provider(db, data_source_id)


# ---------- interface for other modules ----------


async def get_data_source_ref(
    db: AsyncSession, data_source_id: UUID
) -> schemas.DataSourceRef | None:
    row = await db.get(DataSource, data_source_id)
    if row is None:
        return None
    return schemas.DataSourceRef.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "status": row.status,
            "allow_samples": row.allow_samples,
            "has_credential": row.secret is not None,
            "catalog_status": row.catalog_status,
        }
    )


async def get_catalog_table(
    db: AsyncSession,
    data_source_id: UUID,
    table: TableRef,
) -> schemas.CatalogTableCopy | None:
    """The table as the last catalog refresh saw it; None when the cache does not have it."""
    row = await db.scalar(
        sql_select(CatalogTable).where(
            CatalogTable.data_source_id == data_source_id,
            CatalogTable.schema_name == table.schema,
            CatalogTable.table_name == table.name,
        )
    )
    return _catalog_copy(row) if row is not None else None


def _catalog_copy(row: CatalogTable) -> schemas.CatalogTableCopy:
    return schemas.CatalogTableCopy.model_validate(
        {
            "data_source_id": row.data_source_id,
            "schema_name": row.schema_name,
            "name": row.table_name,
            "kind": row.kind,
            "comment": row.comment,
            "columns": row.columns,
            "primary_key": row.primary_key,
            "foreign_keys": row.foreign_keys,
            "refreshed_at": row.refreshed_at,
        }
    )


async def list_catalog_tables_for(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    schema_names: tuple[str, ...] | None = None,
    tables: tuple[TableRef, ...] | None = None,
) -> tuple[schemas.CatalogTableCopy, ...]:
    """Cached catalog tables of the given schemas, or the given tables, by schema and name.
    With neither, every cached table. Tables the cache does not have are left out."""
    statement = sql_select(CatalogTable).where(CatalogTable.data_source_id == data_source_id)
    if schema_names is not None:
        statement = statement.where(CatalogTable.schema_name.in_(schema_names))
    if tables is not None:
        wanted = {(table.schema, table.name) for table in tables}
        statement = statement.where(
            tuple_(CatalogTable.schema_name, CatalogTable.table_name).in_(wanted)
        )
    statement = statement.order_by(CatalogTable.schema_name, CatalogTable.table_name)
    return tuple(_catalog_copy(row) for row in await db.scalars(statement))


async def select(db: AsyncSession, query: SelectQuery) -> Rows:
    """Run one generated SELECT in a read-only transaction, with the statement timeout and the
    row limit of the settings. Cancelling the awaiting task cancels the statement.

    Raises the `connectors.errors` exceptions: SourceDisabledError, SourceUnavailableError,
    SourceBusyError, QueryTimeoutError, SourceMismatchError, InvalidValueError.
    """
    return await connection.run_select(db, query)


async def sample_values(
    db: AsyncSession,
    data_source_id: UUID,
    table: TableRef,
    columns: tuple[str, ...],
) -> dict[str, tuple[Value, ...]]:
    """A few distinct values per column, only for data sources that allow samples. Raises the
    same exceptions as `select`, and SourceDisabledError while samples are switched off."""
    return await connection.run_samples(db, data_source_id, table, columns)


# ---------- HTTP operations ----------


def _not_found() -> AppError:
    return AppError(404, "datasource.not_found", "The data source was not found.")


async def _active_source(db: AsyncSession, source_id: UUID, *, lock: bool = True) -> DataSource:
    # Reads that connect to the data source afterwards take no lock: a connection may take as
    # long as its timeouts, and edits of the same data source must not wait for it.
    row = await db.get(DataSource, source_id, with_for_update=lock, populate_existing=True)
    if row is None:
        raise _not_found()
    if row.status == "archived":
        raise AppError(409, "datasource.archived", "The data source is archived.")
    return row


def _audit(
    db: AsyncSession,
    action: str,
    source_id: UUID | None,
    actor: Principal,
    ip: str | None,
    detail: Mapping[str, object] | None = None,
) -> None:
    audit.record(
        db,
        action,
        actor_id=actor.id,
        target_type="data_source",
        target_id=str(source_id) if source_id is not None else None,
        detail=detail,
        ip=ip,
    )


async def _source_views(
    db: AsyncSession, actor: Principal, source_id: UUID | None = None
) -> list[schemas.DataSource]:
    show_connection = actor.role in (Role.EDITOR, Role.REVIEWER, Role.ADMIN)
    table_count = (
        sql_select(func.count())
        .select_from(CatalogTable)
        .where(CatalogTable.data_source_id == DataSource.id)
        .scalar_subquery()
    )
    statement = sql_select(DataSource, table_count if show_connection else literal(0))
    if source_id is not None:
        statement = statement.where(DataSource.id == source_id)

    result = []
    for row, count in await db.execute(statement.order_by(DataSource.name)):
        usage = await table_usage(db, row.id)
        bound_count = None
        if usage is not None:
            bound_count = len({item.type_id for item in usage if item.in_working_version})
        connection_info = None
        catalog_info = None
        if show_connection:
            connection_info = schemas.Connection.model_validate(row, from_attributes=True)
            catalog_info = {
                "status": row.catalog_status,
                "refreshed_at": row.catalog_refreshed_at,
                "error_code": row.catalog_error_code,
                "table_count": count,
            }
        last_test = None
        if row.last_test_at is not None:
            last_test = {
                "at": row.last_test_at,
                "ok": row.last_test_ok,
                "code": row.last_test_code,
                "warnings": row.last_test_warnings,
            }
        result.append(
            schemas.DataSource.model_validate(
                {
                    "id": row.id,
                    "name": row.name,
                    "kind": row.kind,
                    "status": row.status,
                    "connection": connection_info,
                    "has_credential": bool(row.secret),
                    "credential_updated_at": row.credential_updated_at,
                    "allow_samples": row.allow_samples,
                    "last_test": last_test,
                    "catalog": catalog_info,
                    "bound_type_count": bound_count,
                    "revision": row.revision,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
            )
        )
    return result


async def list_data_sources(db: AsyncSession, *, actor: Principal) -> list[schemas.DataSource]:
    return await _source_views(db, actor)


async def get_data_source(
    db: AsyncSession, data_source_id: UUID, *, actor: Principal
) -> schemas.DataSource:
    views = await _source_views(db, actor, data_source_id)
    if not views:
        raise _not_found()
    return views[0]


async def _commit_source(db: AsyncSession, row: DataSource, actor: Principal) -> schemas.DataSource:
    # Capture the response under the same lock as the write, including an enqueued refresh.
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        cause = exc.orig
        if (
            isinstance(cause, UniqueViolation)
            and cause.diag.constraint_name == "uq_data_sources_name"
        ):
            raise AppError(409, "datasource.name_taken", "That name is already in use.") from None
        raise
    view = await get_data_source(db, row.id, actor=actor)
    await db.commit()
    return view


def _platform_database() -> AppError:
    return AppError(422, "datasource.platform_database", "The platform database cannot be used.")


async def _check_address(db: AsyncSession, host: str, port: int, database: str) -> None:
    try:
        await connection.ensure_not_platform_address(db, host=host, port=port, database=database)
    except PlatformDatabaseError:
        raise _platform_database() from None


async def create_data_source(
    db: AsyncSession,
    body: schemas.DataSourceCreate,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    await _check_address(db, body.host, body.port, body.database)
    source_id = uuid4()
    sealed = secrets.seal(config.current(), source_id, body.password)
    fields = body.model_dump(exclude={"password"})
    row = DataSource(
        id=source_id,
        **fields,
        secret=sealed.secret,
        secret_key_id=sealed.key_id,
        credential_updated_at=datetime.now(UTC),
        created_by=actor.id,
    )
    db.add(row)
    _audit(
        db,
        "datasource.created",
        source_id,
        actor,
        ip,
        {"fields": sorted(to_camel(key) for key in fields), "passwordChanged": True},
    )
    return await _commit_source(db, row, actor)


async def update_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    body: schemas.DataSourcePatch,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    row = await _active_source(db, data_source_id)
    if body.revision != row.revision:
        raise AppError(409, "datasource.stale", "The data source has changed.")

    supplied = body.model_dump(exclude={"password", "revision"}, exclude_none=True)
    changes = {key: value for key, value in supplied.items() if getattr(row, key) != value}
    if changes.keys() & {"host", "port", "database"}:
        await _check_address(
            db, body.host or row.host, body.port or row.port, body.database or row.database
        )
    for key, value in changes.items():
        setattr(row, key, value)
    now = datetime.now(UTC)
    if body.password is not None:
        sealed = secrets.seal(config.current(), data_source_id, body.password)
        row.secret = sealed.secret
        row.secret_key_id = sealed.key_id
        row.credential_updated_at = now
    if body.password is not None or changes.keys() & {"host", "port", "database", "username"}:
        row.last_test_at = row.last_test_ok = row.last_test_code = None
        row.last_test_warnings = []
    if changes or body.password is not None:
        row.revision += 1
        row.updated_at = now
    _audit(
        db,
        "datasource.updated",
        data_source_id,
        actor,
        ip,
        {
            "fields": sorted(to_camel(key) for key in changes),
            "passwordChanged": body.password is not None,
        },
    )
    return await _commit_source(db, row, actor)


async def archive_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    row = await _active_source(db, data_source_id)
    usage = await table_usage(db, data_source_id)
    if usage is None or any(item.in_working_version or item.in_active_release for item in usage):
        raise AppError(409, "datasource.in_use", "The data source may still be in use.")
    row.secret = row.secret_key_id = None
    row.status = "archived"
    if row.catalog_status == "refreshing":
        # A queued worker will leave this source alone. Expose the last completed snapshot.
        row.catalog_status = "ready" if row.catalog_refreshed_at is not None else "never"
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    _audit(db, "datasource.archived", data_source_id, actor, ip)
    return await _commit_source(db, row, actor)


def _saved_params(row: DataSource) -> connection.ConnectionParams:
    try:
        return connection.params_of(row)
    except PlatformDatabaseError:
        raise _platform_database() from None
    except SourceDisabledError:
        # Archived rows are rejected before resolving their credentials.
        raise AppError(
            409, "datasource.credential_unreadable", "The saved credential cannot be read."
        ) from None


async def _test_and_audit(
    db: AsyncSession,
    params: connection.ConnectionParams,
    source_id: UUID | None,
    actor: Principal,
    ip: str | None,
) -> schemas.ConnectionTest:
    await _check_address(db, params.host, params.port, params.database)
    try:
        result = await connection.test_connection(db, params)
    except PlatformDatabaseError:
        raise _platform_database() from None
    _audit(db, "datasource.tested", source_id, actor, ip, {"code": result.code or "ok"})
    return result


async def check_connection(
    db: AsyncSession,
    body: schemas.ConnectionTestRequest,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.ConnectionTest:
    """Test settings that are not saved yet (admins only: it connects to any address)."""
    password = body.password
    if password is None:
        if body.data_source_id is None:
            raise AppError(422, "validation.failed", "A password or data source is required.")
        row = await _active_source(db, body.data_source_id, lock=False)
        password = _saved_params(row).password
    target = body.data_source_id if body.password is None else None
    params = connection.ConnectionParams(
        host=body.host,
        port=body.port,
        database=body.database,
        username=body.username,
        password=password,
        ssl_mode=body.ssl_mode,
        kind=body.kind,
    )
    result = await _test_and_audit(db, params, target, actor, ip)
    await db.commit()
    return result


async def check_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.ConnectionTest:
    row = await _active_source(db, data_source_id, lock=False)
    revision = row.revision
    result = await _test_and_audit(db, _saved_params(row), data_source_id, actor, ip)
    current = await db.get(DataSource, data_source_id, with_for_update=True, populate_existing=True)
    # Changed while the test ran: the result may describe the old settings, so it is not kept.
    if current is not None and current.status == "active" and current.revision == revision:
        current.last_test_at = datetime.now(UTC)
        current.last_test_ok = result.ok
        current.last_test_code = result.code
        current.last_test_warnings = list(result.warnings)
    await db.commit()
    return result


async def request_catalog_refresh(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    """Queue the `connectors.refresh_catalog` job."""
    row = await _active_source(db, data_source_id)
    row.catalog_status = "refreshing"
    row.catalog_error_code = None
    await queue.enqueue(db, jobs.REFRESH_CATALOG, {"dataSourceId": str(data_source_id)})
    return await _commit_source(db, row, actor)


async def _require_catalog(db: AsyncSession, source_id: UUID) -> None:
    found = (
        await db.execute(
            sql_select(DataSource.id, DataSource.catalog_refreshed_at).where(
                DataSource.id == source_id
            )
        )
    ).first()
    if found is None:
        raise _not_found()
    # Never read successfully: a first refresh still running or failed has no catalog either.
    if found.catalog_refreshed_at is None:
        raise AppError(409, "catalog.not_ready", "The catalog has not been read yet.")


async def list_catalog_schemas(
    db: AsyncSession, data_source_id: UUID
) -> list[schemas.CatalogSchema]:
    await _require_catalog(db, data_source_id)
    statement = (
        sql_select(CatalogTable.schema_name, func.count())
        .where(CatalogTable.data_source_id == data_source_id)
        .group_by(CatalogTable.schema_name)
        .order_by(CatalogTable.schema_name)
    )
    return [
        schemas.CatalogSchema(name=name, table_count=count)
        for name, count in await db.execute(statement)
    ]


async def _bound_types(db: AsyncSession, source_id: UUID) -> dict[TableRef, schemas.BoundTypeRef]:
    usage = await table_usage(db, source_id)
    return {
        TableRef(schema=item.schema, name=item.table): schemas.BoundTypeRef(
            id=item.type_id, label=item.type_label
        )
        for item in usage or []
        if item.in_working_version
    }


def _encode_cursor(schema: str, name: str) -> str:
    # PostgreSQL identifiers cannot contain NUL.
    return base64.urlsafe_b64encode(f"{schema}\0{name}".encode()).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        schema, name = base64.b64decode(cursor, altchars=b"-_", validate=True).decode().split("\0")
        if not all(0 < len(part) <= IDENTIFIER_MAX_LENGTH for part in (schema, name)):
            raise ValueError
    except ValueError:
        raise AppError(422, "validation.failed", "The catalog cursor is invalid.") from None
    return schema, name


async def list_catalog_tables(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    schema: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> schemas.CatalogTablePage:
    await _require_catalog(db, data_source_id)
    if not 1 <= limit <= 200:
        raise AppError(422, "validation.failed", "The catalog page size is invalid.")
    statement = sql_select(
        CatalogTable.schema_name,
        CatalogTable.table_name,
        CatalogTable.kind,
        CatalogTable.comment,
        func.jsonb_array_length(CatalogTable.columns),
    ).where(CatalogTable.data_source_id == data_source_id)
    if schema is not None:
        statement = statement.where(CatalogTable.schema_name == schema)
    if q:
        statement = statement.where(
            or_(
                CatalogTable.table_name.icontains(q, autoescape=True),
                CatalogTable.comment.icontains(q, autoescape=True),
            )
        )
    if cursor is not None:
        statement = statement.where(
            tuple_(CatalogTable.schema_name, CatalogTable.table_name) > _decode_cursor(cursor)
        )
    statement = statement.order_by(CatalogTable.schema_name, CatalogTable.table_name)
    rows = (await db.execute(statement.limit(limit + 1))).all()
    bindings = await _bound_types(db, data_source_id)
    items = [
        schemas.CatalogTableBrief.model_validate(
            {
                "schema": ns,
                "name": name,
                "kind": kind,
                "comment": comment,
                "column_count": count,
                "bound_type": bindings.get(TableRef(schema=ns, name=name)),
            }
        )
        for ns, name, kind, comment, count in rows[:limit]
    ]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = _encode_cursor(items[-1].schema_name, items[-1].name)
    return schemas.CatalogTablePage(items=items, next_cursor=next_cursor)


async def get_catalog_table_detail(
    db: AsyncSession,
    data_source_id: UUID,
    table: TableRef,
) -> schemas.CatalogTable:
    await _require_catalog(db, data_source_id)
    cached = await get_catalog_table(db, data_source_id, table)
    if cached is None:
        raise AppError(404, "catalog.table_not_found", "The catalog table was not found.")
    bindings = await _bound_types(db, data_source_id)
    return schemas.CatalogTable.model_validate(
        {
            **cached.model_dump(),
            "column_count": len(cached.columns),
            "bound_type": bindings.get(table),
        }
    )
