"""Every write operation goes through the session check, which also enforces CSRF.

Login is the only exemption. Since FastAPI 0.137 `app.routes` is an internal tree of included
routers, so the check is behavioural and driven by the public OpenAPI document: every
POST/PUT/PATCH/DELETE operation must answer 401 without a session, and 403 `auth.csrf_failed`
with a session but no X-CSRF-Token header. Dependencies run before body and path validation,
so requests without a body are enough. A new write route that does not depend on
`CurrentUser`, `CurrentSession` or `require_role(...)` makes this test fail.
"""

import re

from fastapi import FastAPI
from httpx import AsyncClient

from ontology_platform.modules.identity.api import CurrentUser
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
