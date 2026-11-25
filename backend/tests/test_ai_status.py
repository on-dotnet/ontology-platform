"""GET /api/ai/status: configured / reachable, cached, and never leaking the key or proxy."""

from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel, SecretStr

from ontology_platform.main import create_app
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.settings import Settings
from support import login, make_client


class FakeGateway:
    def __init__(self, reachable: bool) -> None:
        self.reachable = reachable
        self.pings = 0

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
        effort: str | None = None,
    ) -> T:
        raise NotImplementedError

    async def ping(self) -> bool:
        self.pings += 1
        return self.reachable


async def test_requires_sign_in(client: AsyncClient) -> None:
    response = await client.get("/api/ai/status")
    assert response.status_code == 401


async def test_not_configured_without_a_key(client: AsyncClient) -> None:
    await login(client)
    response = await client.get("/api/ai/status")
    assert response.status_code == 200
    assert response.json() == {"configured": False, "reachable": None, "model": None}


async def configured_app(settings: Settings) -> FastAPI:
    configured = settings.model_copy(
        update={
            "openai_api_key": SecretStr("sk-test-secret-value"),
            "ai_proxy": SecretStr("http://user:proxy-pass@proxy.example:7897"),
            "ai_model": "test-model",
        }
    )
    return create_app(configured)


async def test_reports_reachability_and_caches_the_ping(settings: Settings) -> None:
    app = await configured_app(settings)
    fake = FakeGateway(reachable=True)
    app.state.model_gateway = fake
    async with app.router.lifespan_context(app), make_client(app) as client:
        await login(client)
        first = await client.get("/api/ai/status")
        second = await client.get("/api/ai/status")

    assert first.json() == {"configured": True, "reachable": True, "model": "test-model"}
    assert second.json() == first.json()
    assert fake.pings == 1
    body = first.text
    assert "sk-test-secret-value" not in body
    assert "proxy-pass" not in body


async def test_unreachable_model_is_reported(settings: Settings) -> None:
    app = await configured_app(settings)
    app.state.model_gateway = FakeGateway(reachable=False)
    async with app.router.lifespan_context(app), make_client(app) as client:
        await login(client)
        response = await client.get("/api/ai/status")

    assert response.json()["reachable"] is False
