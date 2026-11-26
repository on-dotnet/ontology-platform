"""Background jobs of the connectors module."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import not_implemented
from ontology_platform.modules.connectors import config
from ontology_platform.modules.jobs.runner import JobContext, register
from ontology_platform.settings import Settings

# Payload: {"dataSourceId": "<uuid>"}
REFRESH_CATALOG = "connectors.refresh_catalog"


def register_handlers(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Called once by the worker. The handler arrives with batch 3 (spec 003, 5.5)."""
    config.configure(settings)

    async def refresh_catalog(job: JobContext) -> None:
        raise not_implemented("Reading the catalog")

    register(REFRESH_CATALOG, refresh_catalog)
