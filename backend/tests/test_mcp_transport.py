"""The MCP endpoint (spec 003, section 9). Batch 6a implements it and extends this file, with
every protocol field checked against the 2026-07-28 schema rather than written from memory."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers, make_client
from test_ontology_support import sign_in


async def test_mcp_refuses_requests_without_a_token(client: AsyncClient) -> None:
    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.xfail(strict=True, reason="M3 batch 6a: the MCP transport and tools")
async def test_mcp_answers_a_valid_token(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": ["ontology:read"]},
        headers=csrf_headers(client),
    )
    token = created.json()["token"]

    async with make_client(app) as agent:
        response = await agent.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "server/discover"},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2026-07-28",
                "Mcp-Method": "server/discover",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
