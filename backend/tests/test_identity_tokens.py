"""Personal access tokens (spec 003, section 4). Batch 2 implements them and extends this file."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers, make_client
from test_ontology_support import sign_in


@pytest.mark.xfail(strict=True, reason="M3 batch 2: access tokens")
async def test_a_revoked_token_is_refused_at_once(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": ["ontology:read"]},
        headers=csrf_headers(client),
    )
    assert created.status_code == 201
    token, token_id = created.json()["token"], created.json()["info"]["id"]
    assert token.startswith("op_pat_")
    assert len(token) == len("op_pat_") + 43
    bearer = {"Authorization": f"Bearer {token}"}

    async with make_client(app) as agent:
        before = await agent.get("/api/auth/me", headers=bearer)
        revoked = await client.delete(f"/api/auth/tokens/{token_id}", headers=csrf_headers(client))
        after = await agent.get("/api/auth/me", headers=bearer)

    assert before.status_code == 200
    assert revoked.status_code == 204
    assert after.status_code == 401
    assert after.json()["code"] == "auth.invalid_token"
