"""Background jobs of the connectors module."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.connectors import config, connection
from ontology_platform.modules.connectors.catalog import DiscoveredTable
from ontology_platform.modules.connectors.errors import (
    CatalogTooLargeError,
    ConnectorError,
    CredentialUnreadableError,
    PlatformDatabaseError,
)
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.jobs import service as queue
from ontology_platform.modules.jobs.runner import JobContext, register
from ontology_platform.settings import Settings

# Payload: {"dataSourceId": "<uuid>", "actorId": "<uuid>"} (actorId optional for old jobs)
REFRESH_CATALOG = "connectors.refresh_catalog"


def _error_code(error: ConnectorError) -> str:
    if isinstance(error, PlatformDatabaseError):
        return "datasource.platform_database"
    if isinstance(error, CredentialUnreadableError):
        return "datasource.credential_unreadable"
    if isinstance(error, CatalogTooLargeError):
        return "catalog.too_large"
    return "datasource.connect_failed"


async def _replace_catalog(
    db: AsyncSession, row: DataSource, tables: list[DiscoveredTable]
) -> None:
    now = datetime.now(UTC)
    await db.execute(delete(CatalogTable).where(CatalogTable.data_source_id == row.id))
    db.add_all(
        CatalogTable(
            data_source_id=row.id,
            schema_name=table.schema,
            table_name=table.name,
            kind=table.kind,
            comment=table.comment,
            columns=[column.model_dump() for column in table.columns],
            primary_key=list(table.primary_key) if table.primary_key is not None else None,
            foreign_keys=[key.model_dump(by_alias=True) for key in table.foreign_keys],
            refreshed_at=now,
        )
        for table in tables
    )
    row.catalog_status = "ready"
    row.catalog_error_code = None
    row.catalog_refreshed_at = now


async def _record(
    db: AsyncSession,
    job: JobContext,
    source_id: UUID,
    revision: int,
    tables: list[DiscoveredTable] | None,
    failure: ConnectorError | None,
) -> None:
    """Store what a refresh read, under the data source's row lock, if it still applies."""
    row = await db.get(DataSource, source_id, with_for_update=True, populate_existing=True)
    if row is None or row.status == "archived" or row.catalog_status != "refreshing":
        return
    if row.revision != revision:
        # The settings changed while reading: what was read may be another database.
        await queue.enqueue(db, REFRESH_CATALOG, job.payload)
        await job.check_lease(db)
        return
    detail: dict[str, str | int]
    if failure is not None or tables is None:
        code = _error_code(failure) if failure is not None else "datasource.connect_failed"
        row.catalog_status = "failed"
        row.catalog_error_code = code
        detail = {"errorCode": code}
    else:
        await _replace_catalog(db, row, tables)
        detail = {"tableCount": len(tables)}
    audit.record(
        db,
        "datasource.catalog_refreshed",
        target_type="data_source",
        target_id=str(source_id),
        actor_id=_actor_id(job.payload),
        detail=detail,
    )
    await job.check_lease(db)


def _actor_id(payload: dict[str, object]) -> UUID | None:
    """Who asked for the refresh; jobs queued before the field existed have none. A bad value
    must not fail the job: the catalog would stay "refreshing"."""
    raw = payload.get("actorId")
    if not isinstance(raw, str):
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def register_handlers(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Called once by the worker."""
    config.configure(settings)

    async def refresh_catalog(job: JobContext) -> None:
        source_id = UUID(job.payload["dataSourceId"])
        # Read the data source without holding its row: the read may take as long as its
        # timeouts, and edits, tests and archiving must not wait for it.
        async with session_factory() as db:
            row = await db.get(DataSource, source_id)
            # A refresh that already finished after this job was queued satisfied it. Every
            # later request sets refreshing again before making its job visible.
            if row is None or row.status == "archived" or row.catalog_status != "refreshing":
                return
            revision = row.revision
            schema_names = tuple(row.schemas)
            tables: list[DiscoveredTable] | None = None
            failure: ConnectorError | None = None
            unexpected: Exception | None = None
            try:
                params = connection.params_of(row)
                # Not idle in a transaction on the platform database while the source is read;
                # `connect` leaves the session idle after checking the platform's identity.
                await db.commit()
                tables = await connection.read_catalog(db, params, schema_names)
            except ConnectorError as error:
                failure = error
            except Exception as error:
                # A bug, not a connector error: record the refresh as failed so that the page
                # does not wait for ever, then let the runner log and fail the job.
                unexpected = error
        async with session_factory.begin() as db:
            await _record(db, job, source_id, revision, tables, failure)
        # Raised even when the result was dropped, so that a bug is never a quiet success.
        if unexpected is not None:
            raise unexpected

    register(REFRESH_CATALOG, refresh_catalog)
