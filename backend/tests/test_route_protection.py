"""Every write operation goes through the session check, which also enforces CSRF.

Login is the only exemption. Since FastAPI 0.137 `app.routes` is an internal tree of included
routers, so the check is behavioural and driven by the public OpenAPI document: every
POST/PUT/PATCH/DELETE operation must answer 401 without a session, and 403 `auth.csrf_failed`
with a session but no X-CSRF-Token header. Dependencies run before body and path validation,
so requests without a body are enough. A new write route that does not depend on
`CurrentUser`, `CurrentSession` or `require_role(...)` makes this test fail.

The second half does the same for access tokens: only the routes the M3 appendix lists accept
one, every other operation answers 403 `auth.token_not_allowed`.
"""

import re
from typing import Annotated

from fastapi import Depends, FastAPI
from httpx import AsyncClient

from ontology_platform.modules.identity.api import CurrentUser, require_scope
from ontology_platform.modules.identity.service import Principal
from support import login

WRITE_METHODS = {"post", "put", "patch", "delete"}
CSRF_EXEMPT = {("post", "/api/auth/login")}
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"


def write_operations(app: FastAPI) -> list[tuple[str, str]]:
    operations: list[tuple[str, str]] = []
    for path, path_item in app.openapi()["paths"].items():
        for method in path_item:
            if method in WRITE_METHODS and (method, path) not in CSRF_EXEMPT:
                operations.append((method.upper(), re.sub(r"\{[^}]+\}", PLACEHOLDER, path)))
    return operations


async def unprotected(app: FastAPI, client: AsyncClient) -> list[str]:
    operations = write_operations(app)
    failures: set[str] = set()
    for method, path in operations:
        response = await client.request(method, path)
        if response.status_code != 401:
            failures.add(f"{method} {path}")
    await login(client)
    for method, path in operations:
        response = await client.request(method, path)
        if response.status_code != 403 or response.json()["code"] != "auth.csrf_failed":
            failures.add(f"{method} {path}")
    return sorted(failures)


async def test_every_write_operation_checks_session_and_csrf(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    assert ("POST", "/api/auth/logout") in write_operations(app)
    assert await unprotected(app, client) == []


async def test_a_write_route_without_session_check_is_caught(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    async def open_write() -> None:
        return None

    async def guarded_write(user: CurrentUser) -> None:
        return None

    app.add_api_route("/api/test/open", open_write, methods=["POST"])
    app.add_api_route("/api/test/guarded", guarded_write, methods=["DELETE"])

    assert await unprotected(app, client) == ["POST /api/test/open"]


# ---------- access tokens (spec 003 §4, §15 "令牌" ④) ----------
# The appendix's "令牌作用域" column: the only operations an access token may call. Every other
# /api operation, read or write, must answer 403 `auth.token_not_allowed` to a valid token that
# holds every scope. /mcp is not in the OpenAPI document; batch 6 tests it.
TOKEN_ROUTES = {
    ("get", "/api/auth/me"),
    ("get", "/api/releases/{id}"),
    ("get", "/api/releases/{id}/export"),
    ("get", "/api/ontologies/{id}/objects/types"),
    ("post", "/api/ontologies/{id}/objects/search"),
    ("get", "/api/ontologies/{id}/objects/{typeId}/{key}"),
    ("get", "/api/ontologies/{id}/objects/{typeId}/{key}/related"),
    # Spec 007 appendix "接口与角色": the M4 operations with scope `objects:read`.
    ("post", "/api/ontologies/{id}/objects/traverse"),
    ("get", "/api/ontologies/{id}/metrics"),
    ("post", "/api/ontologies/{id}/metrics/{metricId}/evaluate"),
    ("post", "/api/ontologies/{id}/rules/check"),
}
# Probes that read no credentials at all, so there is nothing for a token to unlock.
PUBLIC_ROUTES = {("get", "/api/health"), ("get", "/api/health/ready")}
ALL_SCOPES = ["ontology:read", "objects:read", "changes:propose"]


def all_operations(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (method, path)
        for path, path_item in app.openapi()["paths"].items()
        for method in path_item
        if method in WRITE_METHODS | {"get"}
    }


async def token_holder(client: AsyncClient) -> dict[str, str]:
    await login(client)
    created = await client.post(
        "/api/auth/tokens",
        json={"name": "everything", "scopes": ALL_SCOPES},
        headers={"X-CSRF-Token": client.cookies["op_csrf"]},
    )
    assert created.status_code == 201, created.text
    # Drop the session: the token alone must decide.
    client.cookies.clear()
    return {"Authorization": f"Bearer {created.json()['token']}"}


async def token_mismatches(app: FastAPI, client: AsyncClient) -> list[str]:
    """Operations whose answer to a valid all-scope token disagrees with TOKEN_ROUTES."""
    headers = await token_holder(client)
    failures: list[str] = []
    for method, path in sorted(all_operations(app) - PUBLIC_ROUTES):
        url = re.sub(r"\{[^}]+\}", PLACEHOLDER, path)
        response = await client.request(method.upper(), url, headers=headers)
        body = response.json() if "json" in response.headers.get("content-type", "") else None
        code = body.get("code") if isinstance(body, dict) else None
        if (method, path) in TOKEN_ROUTES:
            accepted = response.status_code not in (401, 403)
        else:
            accepted = not (response.status_code == 403 and code == "auth.token_not_allowed")
        if accepted != ((method, path) in TOKEN_ROUTES):
            failures.append(f"{method.upper()} {path} -> {response.status_code} {code}")
    return failures


async def test_tokens_reach_only_the_listed_operations(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    operations = all_operations(app)
    assert operations >= TOKEN_ROUTES
    assert operations >= PUBLIC_ROUTES
    assert await token_mismatches(app, client) == []


async def test_a_route_that_takes_tokens_without_being_listed_is_caught(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    async def scoped_read(
        user: Annotated[Principal, Depends(require_scope("objects:read"))],
    ) -> None:
        return None

    async def session_read(user: CurrentUser) -> None:
        return None

    async def open_read() -> None:
        return None

    app.add_api_route("/api/test/scoped", scoped_read, methods=["GET"])
    app.add_api_route("/api/test/session", session_read, methods=["GET"])
    app.add_api_route("/api/test/open", open_read, methods=["GET"])

    assert await token_mismatches(app, client) == [
        "GET /api/test/open -> 200 None",
        "GET /api/test/scoped -> 200 None",
    ]


async def test_the_public_probes_read_no_credentials(client: AsyncClient) -> None:
    # Why they may be left out above: even an invalid token changes nothing for them.
    headers = {"Authorization": "Bearer op_pat_" + "A" * 43}
    for method, path in sorted(PUBLIC_ROUTES):
        response = await client.request(method.upper(), path, headers=headers)
        assert response.status_code == 200, path
