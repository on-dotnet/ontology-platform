"""Personal access tokens (spec 003, section 4; section 15, "令牌" ①②③⑥ and the token events of
"审计"). Enumerating every route with a token (④) lives in test_route_protection.py."""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity import tokens
from ontology_platform.modules.identity.models import AccessToken, Role, User
from ontology_platform.modules.identity.service import hash_token
from support import csrf_headers, make_client
from test_ontology_support import sign_in

TOKEN_PATTERN = re.compile(r"op_pat_[A-Za-z0-9_-]{43}")
ALL_SCOPES = ["ontology:read", "objects:read", "changes:propose"]


async def create(
    client: AsyncClient, *, scopes: list[str] | None = None, **fields: Any
) -> dict[str, Any]:
    body = {"name": "agent", "scopes": scopes or ["ontology:read"], **fields}
    response = await client.post("/api/auth/tokens", json=body, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def row(db: AsyncSession, token_id: str) -> AccessToken:
    db.expire_all()
    token = await db.get(AccessToken, UUID(token_id))
    assert token is not None
    return token


async def events(db: AsyncSession, action: str) -> list[AuditEvent]:
    statement = select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
    return list(await db.scalars(statement))


async def set_user(db: AsyncSession, username: str, **values: Any) -> None:
    await db.execute(update(User).where(User.username == username).values(**values))
    await db.commit()


async def backdate(db: AsyncSession, token_id: str, *, days: int, expires_in: timedelta) -> None:
    """Move a token's creation `days` back, expiring `expires_in` after now."""
    now = datetime.now(UTC)
    statement = (
        update(AccessToken)
        .where(AccessToken.id == UUID(token_id))
        .values(created_at=now - timedelta(days=days), expires_at=now + expires_in)
    )
    await db.execute(statement)
    await db.commit()


# ---------- who may manage tokens (formerly the skeleton's 501 checks) ----------


async def test_managing_tokens_needs_a_session(client: AsyncClient) -> None:
    for method, path in (
        ("GET", "/api/auth/tokens"),
        ("POST", "/api/auth/tokens"),
        ("DELETE", f"/api/auth/tokens/{uuid4()}"),
    ):
        response = await client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "auth.not_authenticated",
        ), path


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_manages_its_own_tokens(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await sign_in(client, db, role)
    token_id = (await create(client))["info"]["id"]
    assert [item["id"] for item in (await client.get("/api/auth/tokens")).json()] == [token_id]
    revoked = await client.delete(f"/api/auth/tokens/{token_id}", headers=csrf_headers(client))
    assert revoked.status_code == 204


# ---------- creating ----------


async def test_a_created_token_is_shown_once_and_only_its_hash_is_stored(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    response = await client.post(
        "/api/auth/tokens",
        json={"name": "  agent  ", "scopes": ["objects:read", "ontology:read", "objects:read"]},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    token, info = response.json()["token"], response.json()["info"]
    assert TOKEN_PATTERN.fullmatch(token)
    assert info["name"] == "agent"
    assert info["prefix"] == token[:15]
    assert info["scopes"] == ["objects:read", "ontology:read"]
    assert info["owner"]["displayName"] == "viewer-user"
    assert info["lastUsedAt"] is None
    assert info["revokedAt"] is None
    created, expires = (datetime.fromisoformat(info[key]) for key in ("createdAt", "expiresAt"))
    assert expires - created == timedelta(days=90)

    stored = await row(db, info["id"])
    assert stored.token_hash == hash_token(token)
    assert stored.token_hash != token
    assert stored.token_prefix == token[:15]
    # Neither the token nor its hash anywhere in the table or the audit trail.
    dump = await db.scalar(text("SELECT string_agg(t::text, ' ') FROM identity.access_tokens t"))
    assert token not in dump
    assert token[15:] not in dump
    audit_dump = await db.scalar(text("SELECT string_agg(e::text, ' ') FROM audit.events e"))
    assert token[15:] not in audit_dump
    assert stored.token_hash not in audit_dump

    listed = await client.get("/api/auth/tokens")
    assert listed.headers["cache-control"] == "no-store"
    assert token[15:] not in listed.text
    assert stored.token_hash not in listed.text
    assert [item["id"] for item in listed.json()] == [info["id"]]


async def test_two_tokens_differ(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    first, second = await create(client), await create(client)
    assert first["token"] != second["token"]


@pytest.mark.parametrize("days", [0, 366])
async def test_the_lifetime_is_one_to_365_days(
    client: AsyncClient, db: AsyncSession, days: int
) -> None:
    await sign_in(client, db, Role.VIEWER)
    response = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": ["ontology:read"], "expiresInDays": days},
        headers=csrf_headers(client),
    )
    assert response.status_code == 422


async def test_the_lifetime_can_be_chosen(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    info = (await create(client, expiresInDays=365))["info"]
    created, expires = (datetime.fromisoformat(info[key]) for key in ("createdAt", "expiresAt"))
    assert expires - created == timedelta(days=365)


async def test_a_viewer_cannot_ask_for_changes_propose(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    response = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": ["ontology:read", "changes:propose"]},
        headers=csrf_headers(client),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "token.scope_not_allowed"
    assert await db.scalar(select(AccessToken.id)) is None


@pytest.mark.parametrize("role", [Role.EDITOR, Role.REVIEWER, Role.ADMIN])
async def test_editors_and_above_can_ask_for_changes_propose(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await sign_in(client, db, role)
    info = (await create(client, scopes=ALL_SCOPES))["info"]
    assert sorted(info["scopes"]) == sorted(ALL_SCOPES)


async def test_at_most_ten_live_tokens(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = [await create(client) for _ in range(10)]
    refused = await client.post(
        "/api/auth/tokens",
        json={"name": "eleventh", "scopes": ["ontology:read"]},
        headers=csrf_headers(client),
    )
    assert refused.status_code == 409
    assert refused.json()["code"] == "token.limit_reached"

    # Revoked and expired tokens do not count.
    revoked = await client.delete(
        f"/api/auth/tokens/{created[0]['info']['id']}", headers=csrf_headers(client)
    )
    assert revoked.status_code == 204
    await backdate(db, created[1]["info"]["id"], days=10, expires_in=-timedelta(days=1))
    await create(client)
    await create(client)
    assert (
        await client.post(
            "/api/auth/tokens",
            json={"name": "again", "scopes": ["ontology:read"]},
            headers=csrf_headers(client),
        )
    ).status_code == 409


async def test_creating_a_token_waits_for_the_owners_row(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    """Concurrent creations cannot both pass the limit: each one counts the live tokens only
    after locking the owner's row, so a second request waits for the first to commit."""
    await sign_in(client, db, Role.VIEWER)
    body = {"name": "waiting", "scopes": ["ontology:read"]}
    holder: AsyncSession = app.state.session_factory()
    try:
        await holder.execute(
            select(User.id).where(User.username == "viewer-user").with_for_update(key_share=True)
        )
        pending = asyncio.ensure_future(
            client.post("/api/auth/tokens", json=body, headers=csrf_headers(client))
        )
        done, _ = await asyncio.wait({pending}, timeout=1)
        assert not done
        await holder.commit()
    finally:
        await holder.close()
    response = await pending
    assert response.status_code == 201


# ---------- using ----------


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
async def test_a_token_authenticates_as_its_owner(
    app: FastAPI, client: AsyncClient, db: AsyncSession, scheme: str
) -> None:
    await sign_in(client, db, Role.EDITOR)
    token = (await create(client))["token"]
    async with make_client(app) as agent:
        response = await agent.get("/api/auth/me", headers={"Authorization": f"{scheme} {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "editor-user"
    assert response.json()["role"] == "editor"


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


async def test_an_expired_token_is_refused(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await create(client)
    await backdate(db, created["info"]["id"], days=5, expires_in=-timedelta(seconds=1))
    async with make_client(app) as agent:
        response = await agent.get("/api/auth/me", headers=bearer(created["token"]))
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


async def test_deactivating_the_owner_disables_the_token(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    token = (await create(client))["token"]
    async with make_client(app) as agent:
        assert (await agent.get("/api/auth/me", headers=bearer(token))).status_code == 200
        await set_user(db, "viewer-user", is_active=False)
        response = await agent.get("/api/auth/me", headers=bearer(token))
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


async def test_the_owners_role_is_read_on_every_request(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    token = (await create(client, scopes=ALL_SCOPES))["token"]
    context = await tokens.authenticate(db, token, ip=None)
    assert context.principal.role is Role.EDITOR
    assert context.scopes == frozenset(ALL_SCOPES)

    await set_user(db, "editor-user", role=Role.VIEWER.value)
    db.expire_all()
    context = await tokens.authenticate(db, token, ip=None)
    assert context.principal.role is Role.VIEWER
    # A viewer cannot propose changes, so the token no longer can either.
    assert context.scopes == frozenset({"ontology:read", "objects:read"})
    async with make_client(app) as agent:
        me = await agent.get("/api/auth/me", headers=bearer(token))
    assert me.json()["role"] == "viewer"


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer op_pat_" + "A" * 43,  # well-formed but unknown
        "Bearer\top_pat_" + "A" * 43,  # any whitespace separates the scheme
        "Bearer op_pat_short",
        "Bearer not-a-token",
        "Bearer ",
        "Bearer",
    ],
)
async def test_an_invalid_token_does_not_fall_back_to_the_cookie(
    client: AsyncClient, db: AsyncSession, authorization: str
) -> None:
    await sign_in(client, db, Role.ADMIN)
    response = await client.get("/api/auth/me", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"
    # Not even on routes that do not take tokens.
    response = await client.get("/api/ontologies", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"


async def test_other_authorization_schemes_are_ignored(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    response = await client.get("/api/auth/me", headers={"Authorization": "Basic YWJjOmRlZg=="})
    assert response.status_code == 200


async def test_a_valid_token_ignores_the_cookie(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    token = (await create(client))["token"]
    await sign_in(client, db, Role.ADMIN)
    me = await client.get("/api/auth/me", headers=bearer(token))
    assert me.json()["username"] == "viewer-user"
    # The admin's session would be allowed here; the token is not.
    listed = await client.get("/api/auth/tokens", headers=bearer(token))
    assert listed.status_code == 403
    assert listed.json()["code"] == "auth.token_not_allowed"


async def test_tokens_cannot_manage_tokens(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    created = await create(client, scopes=ALL_SCOPES)
    token, token_id = created["token"], created["info"]["id"]
    async with make_client(app) as agent:
        responses = [
            await agent.get("/api/auth/tokens", headers=bearer(token)),
            await agent.post(
                "/api/auth/tokens",
                json={"name": "child", "scopes": ["ontology:read"]},
                headers=bearer(token),
            ),
            await agent.delete(f"/api/auth/tokens/{token_id}", headers=bearer(token)),
            await agent.post("/api/auth/logout", headers=bearer(token)),
        ]
    assert [(r.status_code, r.json()["code"]) for r in responses] == [
        (403, "auth.token_not_allowed")
    ] * 4
    assert (await row(db, token_id)).revoked_at is None
    assert len(list(await db.scalars(select(AccessToken.id)))) == 1


async def test_a_scope_is_needed_for_a_scoped_route(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    objects_only = (await create(client, scopes=["objects:read"]))["token"]
    ontology = (await create(client, scopes=["ontology:read"]))["token"]
    async with make_client(app) as agent:
        refused = await agent.get(f"/api/releases/{uuid4()}", headers=bearer(objects_only))
        allowed = await agent.get(f"/api/releases/{uuid4()}", headers=bearer(ontology))
    assert refused.status_code == 403
    assert refused.json()["code"] == "auth.insufficient_scope"
    # Through the gate: the release simply does not exist.
    assert allowed.status_code == 404


async def test_token_requests_skip_csrf(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    token = (await create(client, scopes=["objects:read"]))["token"]
    path = f"/api/ontologies/{uuid4()}/objects/search"
    async with make_client(app) as agent:
        response = await agent.post(path, json={}, headers=bearer(token))
    assert response.status_code not in (401, 403), response.text
    # The cookie session still needs the header on the same route.
    without_csrf = await client.post(path, json={})
    assert without_csrf.json()["code"] == "auth.csrf_failed"


async def test_last_use_is_recorded_at_most_once_a_minute(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await create(client)
    token, token_id = created["token"], created["info"]["id"]
    async with make_client(app) as agent:
        await agent.get("/api/auth/me", headers=bearer(token))
        first = (await row(db, token_id)).last_used_at
        await agent.get("/api/auth/me", headers=bearer(token))
        assert (await row(db, token_id)).last_used_at == first
        stale = datetime.now(UTC) - timedelta(minutes=2)
        await db.execute(
            update(AccessToken).where(AccessToken.id == UUID(token_id)).values(last_used_at=stale)
        )
        await db.commit()
        await agent.get("/api/auth/me", headers=bearer(token))
    stored = await row(db, token_id)
    assert first is not None
    assert stored.last_used_at is not None
    assert stored.last_used_at > stale
    assert stored.last_used_ip == "127.0.0.1"
    listed = (await client.get("/api/auth/tokens")).json()
    assert listed[0]["lastUsedAt"] is not None


# ---------- listing and revoking ----------


async def test_users_list_only_their_own_tokens(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    mine = (await create(client, name="mine"))["info"]["id"]
    async with make_client(app) as other:
        await sign_in(other, db, Role.EDITOR)
        await create(other, name="theirs")
        refused = await other.get("/api/auth/tokens", params={"owner": "all"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "auth.forbidden"
    assert [item["id"] for item in (await client.get("/api/auth/tokens")).json()] == [mine]


async def test_an_admin_lists_everyones_tokens(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    async with make_client(app) as viewer:
        await sign_in(viewer, db, Role.VIEWER)
        await create(viewer, name="viewer token")
    await sign_in(client, db, Role.ADMIN)
    await create(client, name="admin token")
    everyone = (await client.get("/api/auth/tokens", params={"owner": "all"})).json()
    assert {(item["name"], item["owner"]["displayName"]) for item in everyone} == {
        ("viewer token", "viewer-user"),
        ("admin token", "admin"),
    }
    assert [item["name"] for item in (await client.get("/api/auth/tokens")).json()] == [
        "admin token"
    ]


async def test_dead_tokens_are_listed_for_thirty_days(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    ids = [(await create(client, name=f"t{i}"))["info"]["id"] for i in range(5)]
    await backdate(db, ids[0], days=60, expires_in=-timedelta(days=29))  # expired 29 days ago
    await backdate(db, ids[1], days=60, expires_in=-timedelta(days=31))  # expired 31 days ago
    now = datetime.now(UTC)
    for token_id, revoked_days_ago in ((ids[2], 29), (ids[3], 31)):
        await db.execute(
            update(AccessToken)
            .where(AccessToken.id == UUID(token_id))
            .values(revoked_at=now - timedelta(days=revoked_days_ago))
        )
    await db.commit()
    listed = {item["id"] for item in (await client.get("/api/auth/tokens")).json()}
    assert listed == {ids[0], ids[2], ids[4]}


async def test_only_the_owner_or_an_admin_revokes(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    token_id = (await create(client))["info"]["id"]
    async with make_client(app) as other:
        await sign_in(other, db, Role.EDITOR)
        refused = await other.delete(f"/api/auth/tokens/{token_id}", headers=csrf_headers(other))
        missing = await other.delete(f"/api/auth/tokens/{uuid4()}", headers=csrf_headers(other))
    assert (refused.status_code, refused.json()["code"]) == (404, "token.not_found")
    assert (missing.status_code, missing.json()["code"]) == (404, "token.not_found")
    assert (await row(db, token_id)).revoked_at is None

    async with make_client(app) as admin:
        await sign_in(admin, db, Role.ADMIN)
        revoked = await admin.delete(f"/api/auth/tokens/{token_id}", headers=csrf_headers(admin))
        admin_id = (await admin.get("/api/auth/me")).json()["id"]
    assert revoked.status_code == 204
    stored = await row(db, token_id)
    assert stored.revoked_at is not None
    assert str(stored.revoked_by) == admin_id


async def test_revoking_twice_changes_nothing(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    token_id = (await create(client))["info"]["id"]
    path = f"/api/auth/tokens/{token_id}"
    assert (await client.delete(path, headers=csrf_headers(client))).status_code == 204
    first = (await row(db, token_id)).revoked_at
    assert (await client.delete(path, headers=csrf_headers(client))).status_code == 204
    assert (await row(db, token_id)).revoked_at == first
    assert len(await events(db, "token.revoked")) == 1


# ---------- audit ----------


async def test_creating_and_revoking_are_audited_without_the_token(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    created = await create(client, scopes=["objects:read", "changes:propose"])
    token, info = created["token"], created["info"]
    await client.delete(f"/api/auth/tokens/{info['id']}", headers=csrf_headers(client))
    expected_detail = {"prefix": token[:15], "scopes": ["changes:propose", "objects:read"]}
    for action in ("token.created", "token.revoked"):
        [event] = await events(db, action)
        assert event.target_type == "access_token"
        assert event.target_id == info["id"]
        assert str(event.actor_id) == info["owner"]["id"]
        assert event.detail == expected_detail


async def test_refusing_a_known_token_is_audited_once_per_ten_minutes(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await create(client)
    token, token_id = created["token"], created["info"]["id"]
    await client.delete(f"/api/auth/tokens/{token_id}", headers=csrf_headers(client))
    async with make_client(app) as agent:
        for _ in range(3):
            assert (await agent.get("/api/auth/me", headers=bearer(token))).status_code == 401
        [event] = await events(db, "token.rejected")
        assert event.target_id == token_id
        assert event.detail == {
            "prefix": token[:15],
            "scopes": ["ontology:read"],
            "reason": "revoked",
        }
        assert event.ip == "127.0.0.1"
        assert event.actor_id is None
        assert token[15:] not in str(event.detail)

        stale = datetime.now(UTC) - timedelta(minutes=11)
        await db.execute(
            update(AccessToken)
            .where(AccessToken.id == UUID(token_id))
            .values(last_rejected_at=stale)
        )
        await db.commit()
        await agent.get("/api/auth/me", headers=bearer(token))
        # An unknown token is not audited: there is nothing to attribute it to.
        await agent.get("/api/auth/me", headers=bearer("op_pat_" + "B" * 43))
    assert len(await events(db, "token.rejected")) == 2


async def test_concurrent_refusals_are_audited_once(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await create(client)
    await client.delete(f"/api/auth/tokens/{created['info']['id']}", headers=csrf_headers(client))
    async with make_client(app) as agent:
        responses = await asyncio.gather(
            *(agent.get("/api/auth/me", headers=bearer(created["token"])) for _ in range(5))
        )
    assert {response.status_code for response in responses} == {401}
    assert len(await events(db, "token.rejected")) == 1


@pytest.mark.parametrize("reason", ["expired", "inactive"])
async def test_the_rejection_reason_is_audited(
    app: FastAPI, client: AsyncClient, db: AsyncSession, reason: str
) -> None:
    await sign_in(client, db, Role.VIEWER)
    created = await create(client)
    if reason == "expired":
        await backdate(db, created["info"]["id"], days=5, expires_in=-timedelta(seconds=1))
    else:
        await set_user(db, "viewer-user", is_active=False)
    async with make_client(app) as agent:
        await agent.get("/api/auth/me", headers=bearer(created["token"]))
    [event] = await events(db, "token.rejected")
    assert event.detail["reason"] == reason
