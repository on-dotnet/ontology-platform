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
from ontology_platform.modules.jobs.runner import JobContext, register
from ontology_platform.settings import Settings

# Payload: {"dataSourceId": "<uuid>"}
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


def register_handlers(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Called once by the worker."""
    config.configure(settings)

    async def refresh_catalog(job: JobContext) -> None:
        source_id = UUID(job.payload["dataSourceId"])
        async with session_factory.begin() as db:
            # Serialize refreshes with each other and with edits to the connection settings.
            row = await db.get(DataSource, source_id, with_for_update=True)
            if row is None or row.status == "archived":
                return
            # A worker that acquired this lock after the refresh requests can satisfy them all.
            # Every later request sets refreshing again before making its job visible.
            if row.catalog_status in ("ready", "failed"):
                return
            detail: dict[str, str | int]
            try:
                tables = await connection.read_catalog(db, connection.params_of(row), row.schemas)
            except ConnectorError as error:
                code = _error_code(error)
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
                detail=detail,
            )
            await job.check_lease(db)

    register(REFRESH_CATALOG, refresh_catalog)
