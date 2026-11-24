"""Login, sessions, CSRF, roles and the audit trail around them."""

import asyncio
import hashlib
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

import pytest
from argon2 import PasswordHasher, extract_parameters
from argon2.profiles import RFC_9106_LOW_MEMORY
from fastapi import Depends, FastAPI
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.main import create_app
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity import service
from ontology_platform.modules.identity.api import CurrentUser, require_role
from ontology_platform.modules.identity.models import Role, User, UserSession
from ontology_platform.settings import Settings
from support import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    PROBLEM_JSON,
    cookie_attributes,
    csrf_headers,
    login,
    make_client,
)

UNSAFE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


def add_probe_routes(app: FastAPI) -> None:
    """Routes that exercise the reusable auth dependencies."""

    async def probe(user: CurrentUser) -> dict[str, str]:
        return {"username": user.username}

    app.add_api_route("/api/test/probe", probe, methods=["GET", *UNSAFE_METHODS])
    app.add_api_route(
        "/api/test/admin-only",
        probe,
        methods=["POST"],
        dependencies=[Depends(require_role(Role.ADMIN))],
    )


async def count(db: AsyncSession, model: type[User | UserSession]) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


async def test_login_returns_camel_case_user_and_sets_cookies(client: AsyncClient) -> None:
    response = await login(client)

    assert response.status_code == 200
    user = response.json()
    assert set(user) == {"id", "username", "displayName", "role"}
    assert user["username"] == ADMIN_USERNAME
    assert user["displayName"] == ADMIN_USERNAME
    assert user["role"] == "admin"
    cookies = cookie_attributes(response)
    assert set(cookies) == {"op_session", "op_csrf"}
    assert "httponly" in cookies["op_session"]
    assert "httponly" not in cookies["op_csrf"]
    for attributes in cookies.values():
        assert "samesite=lax" in attributes
        assert "path=/" in attributes
        assert "secure" not in attributes


@pytest.mark.parametrize(
    ("env", "cookie_secure", "expected"),
    [
        ("development", None, False),
        ("production", None, True),
        ("development", True, True),
        ("production", False, False),
    ],
)
async def test_secure_cookie_defaults_to_production(
    app: FastAPI,
    settings: Settings,
    env: str,
    cookie_secure: bool | None,
    expected: bool,
) -> None:
    # model_copy skips validation, so the throwaway test database URL is accepted here.
    overrides = {"env": env, "cookie_secure": cookie_secure}
    configured = create_app(settings.model_copy(update=overrides))

    async with configured.router.lifespan_context(configured), make_client(configured) as client:
        response = await login(client)

    assert response.status_code == 200
    cookies = cookie_attributes(response)
    assert set(cookies) == {"op_session", "op_csrf"}
    assert all(("secure" in attributes) is expected for attributes in cookies.values())


async def test_wrong_password_and_unknown_user_are_indistinguishable(client: AsyncClient) -> None:
    wrong_password = await login(client, password="wrong-password")
    unknown_user = await login(client, username="nobody")

    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.json()["code"] == "auth.invalid_credentials"
        assert "set-cookie" not in response.headers
    assert wrong_password.json() == unknown_user.json()


async def test_unknown_user_still_costs_one_password_check(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str | bytes] = []
    original = PasswordHasher.verify

    def spy(self: PasswordHasher, hash: str | bytes, password: str | bytes) -> Literal[True]:
        checked.append(password)
        return original(self, hash, password)

    monkeypatch.setattr(PasswordHasher, "verify", spy)

    unknown_user = await login(client, username="nobody", password="guess-1")
    wrong_password = await login(client, password="guess-2")

    assert unknown_user.status_code == wrong_password.status_code == 401
    assert checked == ["guess-1", "guess-2"]


async def test_argon2_work_runs_a_few_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    lock = threading.Lock()
    running = 0
    peak = 0

    def slow_verify(
        self: PasswordHasher,
        hash: str | bytes,
        password: str | bytes,
    ) -> Literal[True]:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.1)
        with lock:
            running -= 1
        return True

    monkeypatch.setattr(PasswordHasher, "verify", slow_verify)
    # A fresh semaphore, so the module-level one never binds to this test's event loop.
    monkeypatch.setattr(service, "_argon2_slots", asyncio.Semaphore(service.ARGON2_CONCURRENCY))

    await asyncio.gather(*(service.verify_password("$argon2id$fake", "x") for _ in range(12)))

    assert 1 < peak <= service.ARGON2_CONCURRENCY


async def test_inactive_user_cannot_login(client: AsyncClient, db: AsyncSession) -> None:
    await service.create_user(
        db,
        username="former",
        password="former-password",
        role=Role.EDITOR,
        is_active=False,
    )
    await db.commit()

    response = await login(client, username="former", password="former-password")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_credentials"


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert set(problem) == {"type", "title", "status", "detail", "code"}
    assert problem["status"] == 401
    assert problem["code"] == "auth.not_authenticated"


async def test_me_returns_signed_in_user(client: AsyncClient) -> None:
    user = (await login(client)).json()

    response = await client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == user


async def test_logout_requires_csrf_header(client: AsyncClient) -> None:
    await login(client)

    missing = await client.post("/api/auth/logout")
    wrong = await client.post("/api/auth/logout", headers={"X-CSRF-Token": "wrong"})

    for response in (missing, wrong):
        assert response.status_code == 403
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.json()["code"] == "auth.csrf_failed"
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_logout_ends_the_session(client: AsyncClient) -> None:
    await login(client)
    token = client.cookies["op_session"]

    response = await client.post("/api/auth/logout", headers=csrf_headers(client))

    assert response.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    replay = await client.get("/api/auth/me", headers={"Cookie": f"op_session={token}"})
    assert replay.status_code == 401


async def test_login_replaces_the_session_it_came_with(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await login(client)
    first = client.cookies["op_session"]

    await login(client)
    second = client.cookies["op_session"]

    assert second != first
    replay = await client.get("/api/auth/me", headers={"Cookie": f"op_session={first}"})
    assert replay.status_code == 401
    assert (await client.get("/api/auth/me")).status_code == 200
    assert await count(db, UserSession) == 1


async def test_deactivated_user_loses_session(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    await db.execute(update(User).values(is_active=False))
    await db.commit()

    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.not_authenticated"
    assert await count(db, UserSession) == 0


async def test_session_token_is_stored_hashed(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    token = client.cookies["op_session"]

    stored = (await db.scalars(select(UserSession.token_hash))).all()

    assert stored == [hashlib.sha256(token.encode()).hexdigest()]
    assert token not in stored


async def test_password_is_hashed_with_argon2id(db: AsyncSession) -> None:
    statement = select(User.password_hash).where(User.username == ADMIN_USERNAME)

    password_hash = await db.scalar(statement)

    assert password_hash is not None
    assert password_hash.startswith("$argon2id$")
    assert ADMIN_PASSWORD not in password_hash


def test_production_hashes_keep_the_rfc_9106_low_memory_profile(
    production_hasher: PasswordHasher,
) -> None:
    # The tests swap in a cheap hasher (conftest.py); production must stay on the full profile.
    assert service._hasher is not production_hasher
    assert extract_parameters(production_hasher.hash("x")) == RFC_9106_LOW_MEMORY


async def test_admin_is_created_only_once(
    settings: Settings,
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    changed = settings.model_copy(update={"admin_password": SecretStr("another-password")})
    restarted = create_app(changed)

    async with restarted.router.lifespan_context(restarted):
        pass

    assert await count(db, User) == 1
    assert (await login(client)).status_code == 200


async def test_login_and_logout_are_audited_without_passwords(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await login(client, password="wrong-password-1")
    await login(client, username="ghost", password="ghost-password-2")
    await login(client)
    await client.post("/api/auth/logout", headers=csrf_headers(client))

    events = (await db.scalars(select(AuditEvent).order_by(AuditEvent.id))).all()

    assert [event.action for event in events] == [
        "identity.admin_created",
        "auth.login_failed",
        "auth.login_failed",
        "auth.login_succeeded",
        "auth.logout",
    ]
    failed = [event.detail for event in events if event.action == "auth.login_failed"]
    assert [detail["username"] for detail in failed] == [ADMIN_USERNAME, "ghost"]
    succeeded = events[3]
    assert succeeded.actor_id is not None
    assert succeeded.ip == "127.0.0.1"
    recorded = json.dumps([event.detail for event in events])
    for password in ("wrong-password-1", "ghost-password-2", ADMIN_PASSWORD):
        assert password not in recorded


async def test_idle_session_expires(
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    await login(client)
    stale = datetime.now(UTC) - timedelta(hours=settings.session_idle_hours, minutes=1)
    await db.execute(update(UserSession).values(last_seen_at=stale))
    await db.commit()

    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert await count(db, UserSession) == 0


async def test_session_expires_at_deadline(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    past = datetime.now(UTC) - timedelta(seconds=1)
    await db.execute(update(UserSession).values(expires_at=past))
    await db.commit()

    response = await client.get("/api/auth/me")

    assert response.status_code == 401
    assert await count(db, UserSession) == 0


async def test_last_seen_is_refreshed_at_most_once_a_minute(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await login(client)
    first_seen = await db.scalar(select(UserSession.last_seen_at))
    await client.get("/api/auth/me")
    assert await db.scalar(select(UserSession.last_seen_at)) == first_seen

    earlier = datetime.now(UTC) - timedelta(minutes=2)
    await db.execute(update(UserSession).values(last_seen_at=earlier))
    await db.commit()
    await client.get("/api/auth/me")

    refreshed = await db.scalar(select(UserSession.last_seen_at))
    assert refreshed is not None
    assert refreshed > earlier + timedelta(minutes=1)


@pytest.mark.parametrize("method", UNSAFE_METHODS)
async def test_unsafe_methods_need_csrf(app: FastAPI, client: AsyncClient, method: str) -> None:
    add_probe_routes(app)
    await login(client)

    rejected = await client.request(method, "/api/test/probe")
    accepted = await client.request(method, "/api/test/probe", headers=csrf_headers(client))

    assert rejected.status_code == 403
    assert rejected.json()["code"] == "auth.csrf_failed"
    assert accepted.status_code == 200


async def test_safe_methods_and_login_skip_csrf(app: FastAPI, client: AsyncClient) -> None:
    add_probe_routes(app)
    await login(client)

    assert (await client.get("/api/test/probe")).status_code == 200
    assert (await login(client)).status_code == 200


async def test_unauthenticated_write_is_401(app: FastAPI, client: AsyncClient) -> None:
    add_probe_routes(app)

    response = await client.post("/api/test/probe")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.not_authenticated"


async def test_require_role(app: FastAPI, client: AsyncClient, db: AsyncSession) -> None:
    add_probe_routes(app)
    await service.create_user(db, username="reader", password="reader-password", role=Role.VIEWER)
    await db.commit()

    await login(client, username="reader", password="reader-password")
    denied = await client.post("/api/test/admin-only", headers=csrf_headers(client))
    await login(client)
    allowed = await client.post("/api/test/admin-only", headers=csrf_headers(client))

    assert denied.status_code == 403
    assert denied.json()["code"] == "auth.forbidden"
    assert allowed.status_code == 200
