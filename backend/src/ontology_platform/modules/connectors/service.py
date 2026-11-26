"""Data sources, their cached catalog and read-only access to them (spec 003, section 5).

Only this module may open connections to external data sources or write SQL text; everyone
else calls the functions below. The skeleton fixes their shape: the two small reads other
modules build on (`get_data_source_ref`, `get_catalog_table`) and the usage provider registry
work already, everything else arrives with batch 3.

The HTTP operations commit their own transaction; the functions other modules call never do.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select as sql_select
from sqlalchemy import tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import not_implemented
from ontology_platform.modules.connectors import connection, schemas
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.connectors.statements import Rows, SelectQuery, TableRef, Value
from ontology_platform.modules.identity.service import Principal


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


async def list_data_sources(db: AsyncSession, *, actor: Principal) -> list[schemas.DataSource]:
    raise not_implemented("Listing data sources")


async def get_data_source(
    db: AsyncSession, data_source_id: UUID, *, actor: Principal
) -> schemas.DataSource:
    raise not_implemented("Reading data sources")


async def create_data_source(
    db: AsyncSession,
    body: schemas.DataSourceCreate,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    raise not_implemented("Creating data sources")


async def update_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    body: schemas.DataSourcePatch,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    raise not_implemented("Changing data sources")


async def archive_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    raise not_implemented("Archiving data sources")


async def check_connection(
    db: AsyncSession,
    body: schemas.ConnectionTestRequest,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.ConnectionTest:
    """Test settings that are not saved yet (admins only: it connects to any address)."""
    raise not_implemented("Testing connections")


async def check_data_source(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.ConnectionTest:
    raise not_implemented("Testing connections")


async def request_catalog_refresh(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    actor: Principal,
    ip: str | None,
) -> schemas.DataSource:
    """Queue the `connectors.refresh_catalog` job."""
    raise not_implemented("Reading the catalog")


async def list_catalog_schemas(
    db: AsyncSession, data_source_id: UUID
) -> list[schemas.CatalogSchema]:
    raise not_implemented("Browsing the catalog")


async def list_catalog_tables(
    db: AsyncSession,
    data_source_id: UUID,
    *,
    schema: str | None,
    q: str | None,
    limit: int,
    cursor: str | None,
) -> schemas.CatalogTablePage:
    raise not_implemented("Browsing the catalog")


async def get_catalog_table_detail(
    db: AsyncSession,
    data_source_id: UUID,
    table: TableRef,
) -> schemas.CatalogTable:
    raise not_implemented("Browsing the catalog")
