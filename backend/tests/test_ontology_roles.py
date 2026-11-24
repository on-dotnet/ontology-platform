"""Who may call which ontology, change set and release route."""

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_support import sign_in

ID = "00000000-0000-4000-8000-000000000000"

Call = tuple[str, str, dict[str, Any] | None]

READS: list[Call] = [
    ("GET", "/api/ontologies", None),
    ("GET", f"/api/ontologies/{ID}", None),
    ("GET", f"/api/ontologies/{ID}/elements", None),
    ("GET", f"/api/ontologies/{ID}/elements/{ID}", None),
    ("GET", f"/api/ontologies/{ID}/graph", None),
    ("GET", f"/api/ontologies/{ID}/export?format=turtle", None),
    ("GET", f"/api/ontologies/{ID}/releases", None),
    ("GET", "/api/change-sets", None),
    ("GET", f"/api/change-sets/{ID}", None),
    ("GET", f"/api/releases/{ID}", None),
    ("GET", f"/api/releases/{ID}/export?format=turtle", None),
    ("GET", f"/api/ontologies/{ID}/elements/{ID}/impact", None),
    ("GET", "/api/settings/platform", None),
]
CREATE: Call = ("POST", "/api/ontologies", {"name": "Role Check"})
# Placeholder ids: a permitted caller gets 404, a refused one 403.
EDIT_ITEM = {
    "op": "create",
    "kind": "entity_type",
    "fields": {"localName": "Mill", "labelZh": "轧机"},
}
WRITES: list[Call] = [
    ("POST", f"/api/ontologies/{ID}/edits", {"items": [EDIT_ITEM], "apply": True}),
    ("POST", f"/api/ontologies/{ID}/turtle", {"turtle": "@prefix ex: <urn:t:> ."}),
    # Creators withdraw their own change sets; whose it is is checked after it is found.
    ("POST", f"/api/change-sets/{ID}/reject", None),
]
REVIEWS: list[Call] = [
    ("PATCH", f"/api/change-sets/{ID}/items/{ID}", {"decision": "accepted"}),
    ("POST", f"/api/change-sets/{ID}/decisions", {"itemIds": [], "decision": "accepted"}),
    ("POST", f"/api/change-sets/{ID}/merge", None),
    ("POST", f"/api/ontologies/{ID}/releases", {"title": "v1"}),
    ("POST", f"/api/releases/{ID}/activate", None),
]


async def call(client: AsyncClient, request: Call) -> Response:
    method, path, body = request
    headers = csrf_headers(client) if "op_csrf" in client.cookies else {}
    return await client.request(method, path, json=body, headers=headers)


async def test_every_route_needs_a_session(client: AsyncClient) -> None:
    for request in [*READS, CREATE, *WRITES, *REVIEWS]:
        response = await call(client, request)
        assert response.status_code == 401, request
        assert response.json()["code"] == "auth.not_authenticated"


@pytest.mark.parametrize("role", list(Role))
async def test_roles(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    await sign_in(client, db, role)
    may_create = role in {Role.ADMIN, Role.EDITOR, Role.REVIEWER}
    may_review = role in {Role.ADMIN, Role.REVIEWER}

    for request in READS:
        response = await call(client, request)
        assert response.status_code in {200, 404}, request

    created = await call(client, CREATE)
    if may_create:
        assert created.status_code == 201
    else:
        assert created.status_code == 403
        assert created.json()["code"] == "auth.forbidden"

    for request in WRITES:
        response = await call(client, request)
        assert response.status_code == (404 if may_create else 403), request

    for request in REVIEWS:
        response = await call(client, request)
        if may_review:
            assert response.status_code == 404, request
        else:
            assert response.status_code == 403, request
            assert response.json()["code"] == "auth.forbidden"
