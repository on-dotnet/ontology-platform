"""FastAPI application factory. Importing this module does not touch the database."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version

from fastapi import FastAPI

from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.errors import install_error_handlers
from ontology_platform.modules.ai.api import router as ai_router
from ontology_platform.modules.connectors.api import router as connectors_router
from ontology_platform.modules.connectors.service import register_usage_provider
from ontology_platform.modules.cq.api import router as cq_router
from ontology_platform.modules.documents.api import router as documents_router
from ontology_platform.modules.health.api import router as health_router
from ontology_platform.modules.identity import service as identity_service
from ontology_platform.modules.identity.api import router as auth_router
from ontology_platform.modules.mcp.api import router as mcp_router
from ontology_platform.modules.metrics.api import router as metrics_router
from ontology_platform.modules.ontology import bindings as ontology_bindings
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.api import router as ontology_router
from ontology_platform.modules.query.api import router as query_router
from ontology_platform.modules.workbench.api import router as workbench_router
from ontology_platform.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_database_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory
    try:
        async with session_factory() as db:
            await identity_service.ensure_admin(
                db,
                settings.admin_username,
                settings.admin_password.get_secret_value(),
            )
        warmup = asyncio.create_task(ontology_service.warm_axiom_categories(session_factory))
        try:
            yield
        finally:
            warmup.cancel()
            with suppress(asyncio.CancelledError):
                await warmup
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    docs = settings.env != "production"
    app = FastAPI(
        title="Ontology Platform API",
        version=version("ontology-platform"),
        lifespan=lifespan,
        openapi_url="/api/openapi.json" if docs else None,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
    )
    app.state.settings = settings
    # connectors asks ontology which tables are bound without importing it (spec 003, 5.2).
    register_usage_provider(ontology_bindings.table_usage)
    install_error_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(ontology_router)
    app.include_router(documents_router)
    app.include_router(ai_router)
    app.include_router(workbench_router)
    app.include_router(connectors_router)
    app.include_router(query_router)
    app.include_router(metrics_router)
    app.include_router(cq_router)
    app.include_router(mcp_router)
    return app


app = create_app()
