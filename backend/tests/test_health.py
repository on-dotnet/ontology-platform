"""Liveness and readiness probes."""

from httpx import AsyncClient

from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.main import create_app
from ontology_platform.settings import Settings
from support import PROBLEM_JSON, make_client

UNREACHABLE_DATABASE = "postgresql+psycopg://nobody:nothing@127.0.0.1:1/nothing"


async def test_health_does_not_touch_the_database() -> None:
    app = create_app(Settings(database_url=UNREACHABLE_DATABASE))

    async with make_client(app) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_database_answers(client: AsyncClient) -> None:
    response = await client.get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_not_ready_when_database_is_unreachable() -> None:
    app = create_app(Settings(database_url=UNREACHABLE_DATABASE))
    engine = create_database_engine(UNREACHABLE_DATABASE)
    app.state.session_factory = create_session_factory(engine)

    try:
        async with make_client(app) as client:
            response = await client.get("/api/health/ready")
    finally:
        await engine.dispose()

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "health.not_ready"
