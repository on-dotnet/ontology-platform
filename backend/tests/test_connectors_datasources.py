"""Data source HTTP contracts, persistence, permissions and audit (spec 003, sections 5 and 13)."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors import service
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import Role, User
from support import ADMIN_USERNAME, PROBLEM_JSON, csrf_headers
from test_ontology_support import sign_in

SOURCES = "/api/data-sources"
CREATE_FIELDS = {
    "name",
    "kind",
    "host",
    "port",
    "database",
    "username",
    "sslMode",
    "schemas",
    "allowSamples",
}


def _settings() -> dict[str, Any]:
    return {
        "kind": "postgresql",
        "host": "steel-mes.example",
        "port": 5432,
        "database": "steel_mes",
        "username": "steel_reader",
    }


async def _create(client: AsyncClient, name: str = "MES", **changes: object) -> dict[str, Any]:
    body = {**_settings(), "name": name, "password": uuid4().hex, **changes}
    response = await client.post(SOURCES, json=body, headers=csrf_headers(client))
    assert response.status_code == 201
    result: dict[str, Any] = response.json()
    return result


async def _patch(client: AsyncClient, source: dict[str, Any], **fields: object) -> Response:
    return await client.patch(
        f"{SOURCES}/{source['id']}",
        json={"revision": source["revision"], **fields},
        headers=csrf_headers(client),
    )


async def _stored(db: AsyncSession, source: dict[str, Any]) -> DataSource:
    row = await db.get(DataSource, UUID(source["id"]), populate_existing=True)
    assert row is not None
    return row


async def _events(db: AsyncSession) -> list[AuditEvent]:
    statement = (
        select(AuditEvent)
        .where(AuditEvent.action.startswith("datasource."))
        .order_by(AuditEvent.id)
    )
    return list(await db.scalars(statement))


async def _assert_audit_omits(db: AsyncSession, *markers: str) -> None:
    rows = (await db.execute(select(AuditEvent.__table__))).mappings()
    for row in rows:
        serialized = json.dumps(dict(row), default=str, ensure_ascii=False)
        for marker in markers:
            assert marker not in serialized


def _problem(response: Response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].split(";")[0] == PROBLEM_JSON
    assert response.json()["status"] == status
    assert response.json()["code"] == code


def _external_settings(source: ExternalSource) -> dict[str, Any]:
    return {
        "kind": "postgresql",
        "host": source.host,
        "port": source.port,
        "database": source.database,
        "username": source.reader,
        "password": source.reader_password,
    }


async def test_a_new_data_source_never_returns_its_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    secret = "s3cret-" + uuid4().hex
    body = {
        "name": "钢铁 MES",
        "kind": "postgresql",
        "host": "steel-mes.example",
        "port": 5432,
        "database": "steel_mes",
        "username": "steel_reader",
        "password": secret,
    }

    created = await client.post("/api/data-sources", json=body, headers=csrf_headers(client))
    listed = await client.get("/api/data-sources")
    stored = await db.scalar(select(DataSource.secret).where(DataSource.name == "钢铁 MES"))

    assert created.status_code == 201
    assert created.json()["hasCredential"] is True
    assert secret not in created.text
    assert secret not in listed.text
    assert stored is not None
    assert secret.encode() not in stored

    data = created.json()
    row = await _stored(db, data)
    actor = await db.scalar(select(User.id).where(User.username == ADMIN_USERNAME))
    assert actor is not None
    assert row.created_by == actor
    assert row.secret_key_id
    assert row.credential_updated_at is not None
    assert datetime.fromisoformat(data["credentialUpdatedAt"]) == row.credential_updated_at
    assert data["status"] == "active"
    assert data["allowSamples"] is False
    assert data["lastTest"] is None
    assert data["revision"] == 1
    assert listed.status_code == 200
    assert listed.json() == [data]

    [event] = await _events(db)
    assert (event.action, event.actor_id) == ("datasource.created", actor)
    assert (event.target_type, event.target_id) == ("data_source", data["id"])
    assert sorted(event.detail["fields"]) == sorted(CREATE_FIELDS)
    assert event.detail == {"fields": event.detail["fields"], "passwordChanged": True}
    await _assert_audit_omits(db, secret)


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR, Role.REVIEWER, Role.ADMIN])
async def test_source_list_and_detail_by_role(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, role: Role
) -> None:
    await sign_in(client, db, Role.ADMIN)
    other = await _create(client, "Zulu")
    source = await _create(client, "Alpha", schemas=["mes"], sslMode="require")
    source_id = UUID(source["id"])
    type_id = uuid4()

    async def usage(_db: AsyncSession, data_source_id: UUID) -> list[service.TableUsage]:
        if data_source_id != source_id:
            return []
        return [
            service.TableUsage("mes", "coil", type_id, "Coil", True, True),
            service.TableUsage("mes", "coil_view", type_id, "Coil", True, False),
            service.TableUsage("mes", "slab", uuid4(), "Slab", True, False),
            service.TableUsage("mes", "heat", uuid4(), "Heat", False, True),
        ]

    monkeypatch.setattr(service, "_usage_provider", usage)
    for item, tables in [(source, ["coil", "heat"]), (other, ["coil"])]:
        for table in tables:
            db.add(
                CatalogTable(
                    data_source_id=UUID(item["id"]),
                    schema_name="mes",
                    table_name=table,
                    kind="table",
                    columns=[],
                )
            )
    await db.commit()
    if role != Role.ADMIN:
        await sign_in(client, db, role)
    listed = await client.get(SOURCES)
    detail = await client.get(f"{SOURCES}/{source_id}")
    assert listed.status_code == 200
    assert detail.status_code == 200
    first, second = listed.json()
    assert [first["id"], second["id"]] == [source["id"], other["id"]]
    assert first == detail.json()
    assert first["boundTypeCount"] == 2
    assert second["boundTypeCount"] == 0
    if role == Role.VIEWER:
        for item in [first, second]:
            assert item["connection"] is None
            assert item["catalog"] is None
    else:
        assert first["connection"] == {
            "host": "steel-mes.example",
            "port": 5432,
            "database": "steel_mes",
            "username": "steel_reader",
            "sslMode": "require",
            "schemas": ["mes"],
        }
        assert first["catalog"]["tableCount"] == 2
        assert second["catalog"]["tableCount"] == 1


@pytest.mark.parametrize("role", [Role.VIEWER, Role.EDITOR, Role.REVIEWER])
async def test_forbidden_operations_leave_source_and_audit_unchanged(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    url = f"{SOURCES}/{source['id']}"
    await sign_in(client, db, role)
    headers = csrf_headers(client)
    params = {**_settings(), "password": uuid4().hex}
    denied = [
        await client.post(SOURCES, json={**params, "name": "New"}, headers=headers),
        await _patch(client, source, allowSamples=True),
        await client.post(f"{url}/archive", headers=headers),
        await client.post(f"{SOURCES}/test", json=params, headers=headers),
    ]
    if role == Role.VIEWER:
        denied.append(await client.post(f"{url}/test", headers=headers))
    for response in denied:
        _problem(response, 403, "auth.forbidden")
    await sign_in(client, db, Role.ADMIN)
    assert (await client.get(SOURCES)).json() == [source]
    assert [event.action for event in await _events(db)] == ["datasource.created"]


async def test_update_and_no_op_audit_only_actual_changes(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    original = "original-" + uuid4().hex
    replacement = "replacement-" + uuid4().hex
    source = await _create(client, password=original)
    initial_secret = (await _stored(db, source)).secret
    unchanged = await _patch(client, source, name=source["name"], allowSamples=False)
    assert unchanged.status_code == 200
    assert unchanged.json() == source

    updated = await _patch(
        client, source, allowSamples=True, sslMode="require", schemas=["mes"], port=5432
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["allowSamples"] is True
    assert data["connection"] == {**source["connection"], "sslMode": "require", "schemas": ["mes"]}
    assert data["revision"] == source["revision"] + 1
    assert datetime.fromisoformat(data["updatedAt"]) > datetime.fromisoformat(source["updatedAt"])
    assert data["credentialUpdatedAt"] == source["credentialUpdatedAt"]
    assert (await _stored(db, source)).secret == initial_secret

    changed = await _patch(client, data, password=replacement)
    assert changed.status_code == 200
    assert replacement not in changed.text
    rotated = changed.json()
    assert rotated["revision"] == data["revision"] + 1
    assert datetime.fromisoformat(rotated["credentialUpdatedAt"]) > datetime.fromisoformat(
        data["credentialUpdatedAt"]
    )
    row = await _stored(db, source)
    assert row.secret is not None
    assert row.secret != initial_secret
    assert replacement.encode() not in row.secret
    assert row.credential_updated_at == datetime.fromisoformat(rotated["credentialUpdatedAt"])
    assert (await client.get(f"{SOURCES}/{source['id']}")).json() == rotated

    _, no_op, edit, rotate = await _events(db)
    for event in (no_op, edit, rotate):
        assert event.action == "datasource.updated"
        assert (event.target_type, event.target_id) == ("data_source", source["id"])
        assert event.actor_id == row.created_by
    assert no_op.detail == {"fields": [], "passwordChanged": False}
    assert sorted(edit.detail["fields"]) == ["allowSamples", "schemas", "sslMode"]
    assert edit.detail == {"fields": edit.detail["fields"], "passwordChanged": False}
    assert rotate.detail == {"fields": [], "passwordChanged": True}
    await _assert_audit_omits(db, original, replacement)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("host", "another.example"),
        ("port", 5433),
        ("database", "other_mes"),
        ("username", "other_reader"),
        ("password", "replacement-password"),
        ("name", "Renamed"),
    ],
)
async def test_patch_invalidates_only_affected_connection_results(
    client: AsyncClient, db: AsyncSession, field: str, value: str | int
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    row = await _stored(db, source)
    at = datetime.now(UTC)
    row.last_test_at = at
    row.last_test_ok = False
    row.last_test_code = "datasource.connect_failed"
    row.last_test_warnings = ["account_can_write"]
    await db.commit()

    response = await _patch(client, source, **{field: value})
    assert response.status_code == 200
    row = await _stored(db, source)
    result = response.json()
    if field == "name":
        assert result["name"] == value
        assert datetime.fromisoformat(result["lastTest"]["at"]) == at
        assert result["lastTest"]["ok"] is False
        assert result["lastTest"]["code"] == "datasource.connect_failed"
        assert result["lastTest"]["warnings"] == ["account_can_write"]
        assert row.last_test_at == at
        assert row.last_test_ok is False
        assert row.last_test_code == "datasource.connect_failed"
        assert row.last_test_warnings == ["account_can_write"]
    else:
        if field != "password":
            assert result["connection"][field] == value
        assert result["lastTest"] is None
        assert row.last_test_at is None
        assert row.last_test_ok is None
        assert row.last_test_code is None
        assert row.last_test_warnings == []


@pytest.mark.parametrize(
    ("refreshed", "code", "status"),
    [
        (True, "datasource.credential_unreadable", "ready"),
        (False, "datasource.credential_unreadable", "never"),
        (True, "datasource.connect_failed", "failed"),
    ],
)
async def test_a_new_password_clears_only_an_unreadable_credential_failure(
    client: AsyncClient, db: AsyncSession, refreshed: bool, code: str, status: str
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    row = await _stored(db, source)
    row.catalog_status, row.catalog_error_code = "failed", code
    row.catalog_refreshed_at = datetime.now(UTC) if refreshed else None
    await db.commit()

    renamed = await _patch(client, source, name="Renamed")
    source = renamed.json()
    response = await _patch(client, source, password="replacement-password")

    assert renamed.json()["catalog"]["errorCode"] == code
    assert response.status_code == 200
    assert response.json()["catalog"]["status"] == status
    expected = None if status != "failed" else code
    assert response.json()["catalog"]["errorCode"] == expected


async def test_concurrent_creates_keep_one_source_and_one_audit_event(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    body = {**_settings(), "name": "MES", "password": uuid4().hex}
    headers = csrf_headers(client)
    results = await asyncio.gather(
        client.post(SOURCES, json=body, headers=headers),
        client.post(SOURCES, json=body, headers=headers),
    )
    created, rejected = sorted(results, key=lambda response: response.status_code)
    assert created.status_code == 201
    _problem(rejected, 409, "datasource.name_taken")
    assert (await client.get(SOURCES)).json() == [created.json()]
    [event] = await _events(db)
    assert (event.action, event.target_id) == ("datasource.created", created.json()["id"])


async def test_concurrent_edits_accept_one_revision_and_reject_stale_writes(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    names = ["North", "South"]
    results = await asyncio.gather(*(_patch(client, source, name=name) for name in names))
    assert sorted(r.status_code for r in results) == [200, 409]
    for response, name in zip(results, names, strict=True):
        if response.status_code == 409:
            _problem(response, 409, "datasource.stale")
        else:
            assert response.json()["name"] == name
            assert response.json()["revision"] == source["revision"] + 1
            assert (await client.get(f"{SOURCES}/{source['id']}")).json() == response.json()
    _problem(await _patch(client, source, name="Late"), 409, "datasource.stale")
    assert [e.action for e in await _events(db)] == ["datasource.created", "datasource.updated"]


async def test_rename_to_existing_source_is_atomic(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    first = await _create(client, "Alpha")
    second = await _create(client, "Bravo")
    rejected = await _patch(client, second, name="Alpha", allowSamples=True)
    _problem(rejected, 409, "datasource.name_taken")
    assert (await client.get(SOURCES)).json() == [first, second]
    assert [e.action for e in await _events(db)] == ["datasource.created", "datasource.created"]


async def test_unknown_data_source_errors(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    missing = str(uuid4())
    url = f"{SOURCES}/{missing}"
    headers = csrf_headers(client)
    responses = [
        await client.get(url),
        await client.patch(url, json={"revision": 1, "name": "New"}, headers=headers),
        await client.post(f"{url}/archive", headers=headers),
        await client.post(f"{url}/test", headers=headers),
        await client.post(
            f"{SOURCES}/test", json={**_settings(), "dataSourceId": missing}, headers=headers
        ),
    ]
    for response in responses:
        _problem(response, 404, "datasource.not_found")


@pytest.mark.parametrize(
    ("working", "released", "unknown"),
    [(True, False, False), (False, True, False), (False, False, True)],
    ids=["working", "active-release", "provider-missing"],
)
async def test_archive_requires_known_unused_bindings(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    working: bool,
    released: bool,
    unknown: bool,
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    source_id = UUID(source["id"])
    secret = (await _stored(db, source)).secret

    async def usage(_db: AsyncSession, data_source_id: UUID) -> list[service.TableUsage]:
        assert data_source_id == source_id
        return [service.TableUsage("mes", "coil", uuid4(), "Coil", working, released)]

    monkeypatch.setattr(service, "_usage_provider", None if unknown else usage)
    url = f"{SOURCES}/{source_id}"
    response = await client.post(f"{url}/archive", headers=csrf_headers(client))
    _problem(response, 409, "datasource.in_use")
    expected = {**source, "boundTypeCount": None if unknown else int(working)}
    assert (await client.get(url)).json() == expected
    assert (await client.get(SOURCES)).json() == [expected]
    assert (await _stored(db, source)).secret == secret
    assert [e.action for e in await _events(db)] == ["datasource.created"]


async def test_archive_erases_credentials_and_rejects_later_operations(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await sign_in(client, db, Role.ADMIN)
    marker = "archived-" + uuid4().hex
    source = await _create(client, password=marker)
    url = f"{SOURCES}/{source['id']}"

    async def historical_usage(_db: AsyncSession, data_source_id: UUID) -> list[service.TableUsage]:
        assert str(data_source_id) == source["id"]
        return [service.TableUsage("mes", "coil", uuid4(), "Coil", False, False)]

    monkeypatch.setattr(service, "_usage_provider", historical_usage)
    headers = csrf_headers(client)
    archived = await client.post(f"{url}/archive", headers=headers)
    assert archived.status_code == 200
    data = archived.json()
    assert data["id"] == source["id"]
    assert data["name"] == source["name"]
    assert data["status"] == "archived"
    assert data["hasCredential"] is False
    assert data["revision"] == source["revision"] + 1
    row = await _stored(db, source)
    assert row.secret is None
    assert row.secret_key_id is None
    for response in [
        await _patch(client, data, name="New"),
        await client.post(f"{url}/archive", headers=headers),
        await client.post(f"{url}/test", headers=headers),
        await client.post(
            f"{SOURCES}/test", json={**_settings(), "dataSourceId": source["id"]}, headers=headers
        ),
    ]:
        _problem(response, 409, "datasource.archived")
    assert (await client.get(url)).json() == data
    created, event = await _events(db)
    assert (event.action, event.target_type) == ("datasource.archived", "data_source")
    assert (event.target_id, event.actor_id) == (source["id"], created.actor_id)
    await _assert_audit_omits(db, marker)


@pytest.mark.parametrize("field", ["host", "port", "database"])
async def test_platform_database_guard_checks_the_merged_address(
    client: AsyncClient, db: AsyncSession, database_url: str, field: str
) -> None:
    await sign_in(client, db, Role.ADMIN)
    platform = make_url(database_url)
    assert platform.host
    assert platform.database
    port = platform.port or 5432
    params = {**_settings(), "host": platform.host, "port": port, "database": platform.database}
    marker = "platform-" + uuid4().hex
    headers = csrf_headers(client)
    for response in [
        await client.post(
            SOURCES, json={**params, "name": "Blocked", "password": marker}, headers=headers
        ),
        await client.post(f"{SOURCES}/test", json={**params, "password": marker}, headers=headers),
    ]:
        _problem(response, 422, "datasource.platform_database")
        assert marker not in response.text
        assert platform.database not in response.json()["detail"]
    assert (await client.get(SOURCES)).json() == []

    alternatives = {
        "host": "steel-mes.example",
        "port": 1 if port != 1 else 2,
        "database": platform.database + "_other",
    }
    source = await _create(client, **{**params, field: alternatives[field]})
    update = await _patch(client, source, **{field: params[field]})
    _problem(update, 422, "datasource.platform_database")
    assert (await client.get(SOURCES)).json() == [source]


async def test_saved_connection_to_platform_database_is_rejected(
    client: AsyncClient, db: AsyncSession, database_url: str
) -> None:
    await sign_in(client, db, Role.ADMIN)
    platform = make_url(database_url)
    assert platform.host
    assert platform.database
    source = await _create(
        client,
        host=platform.host,
        port=platform.port or 5432,
        database=platform.database + "_other",
    )
    row = await _stored(db, source)
    # A previously saved configuration must pass the guard again at test time.
    row.database = platform.database
    await db.commit()
    response = await client.post(f"{SOURCES}/{source['id']}/test", headers=csrf_headers(client))
    _problem(response, 422, "datasource.platform_database")


async def test_unreadable_credentials_on_saved_and_unsaved_connection_tests(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(client)
    row = await _stored(db, source)
    row.secret = b"invalid-ciphertext"
    await db.commit()
    headers = csrf_headers(client)
    for response in [
        await client.post(f"{SOURCES}/{source['id']}/test", headers=headers),
        await client.post(
            f"{SOURCES}/test", json={**_settings(), "dataSourceId": source["id"]}, headers=headers
        ),
    ]:
        _problem(response, 409, "datasource.credential_unreadable")
        assert "invalid-ciphertext" not in response.text


@pytest.mark.parametrize("role", [Role.EDITOR, Role.REVIEWER, Role.ADMIN])
async def test_saved_connection_persists_test_result_without_changing_revision(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, role: Role
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = await _create(
        client,
        **{
            **_external_settings(external_source),
            "username": external_source.writer,
            "password": external_source.writer_password,
        },
    )
    if role != Role.ADMIN:
        await sign_in(client, db, role)
    actor = (await client.get("/api/auth/me")).json()["id"]
    url = f"{SOURCES}/{source['id']}"
    tested = await client.post(f"{url}/test", headers=csrf_headers(client))
    assert tested.status_code == 200
    result = tested.json()
    assert result["ok"] is True
    assert result["code"] is None
    assert result["reason"] is None
    assert result["serverVersion"]
    assert result["warnings"] == ["account_can_write"]
    data = (await client.get(url)).json()
    assert data["revision"] == source["revision"]
    row = await _stored(db, source)
    last = data["lastTest"]
    assert datetime.fromisoformat(last["at"]) == row.last_test_at
    assert last["ok"] is True
    assert last["code"] is None
    assert last["warnings"] == ["account_can_write"]
    _, event = await _events(db)
    assert (event.action, event.target_type) == ("datasource.tested", "data_source")
    assert (event.target_id, str(event.actor_id)) == (source["id"], actor)
    assert event.detail == {"code": "ok"}
    await _assert_audit_omits(db, external_source.writer_password)


async def test_failed_saved_connection_returns_reason_and_records_safe_result(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    await sign_in(client, db, Role.ADMIN)
    marker = "wrong-" + uuid4().hex
    params = {**_external_settings(external_source), "password": marker}
    source = await _create(client, **params)
    response = await client.post(f"{SOURCES}/{source['id']}/test", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "code": "datasource.connect_failed",
        "reason": "auth_failed",
        "warnings": [],
        "serverVersion": None,
    }
    assert marker not in response.text
    assert external_source.reader not in response.text
    row = await _stored(db, source)
    assert row.revision == source["revision"]
    assert row.last_test_at is not None
    assert row.last_test_ok is False
    assert row.last_test_code == "datasource.connect_failed"
    assert row.last_test_warnings == []
    _, event = await _events(db)
    assert (event.action, event.target_id) == ("datasource.tested", source["id"])
    assert event.detail == {"code": "datasource.connect_failed"}
    await _assert_audit_omits(db, marker)


async def test_unsaved_tests_use_submitted_settings_and_only_borrow_the_password(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    await sign_in(client, db, Role.ADMIN)
    headers = csrf_headers(client)
    url = f"{SOURCES}/test"
    params = _external_settings(external_source)
    without_password = {key: value for key, value in params.items() if key != "password"}
    missing = await client.post(url, json=without_password, headers=headers)
    _problem(missing, 422, "validation.failed")
    # Only the submitted address and username can work, even when borrowing a saved password.
    source = await _create(client, password=external_source.reader_password)
    with_id = {**without_password, "dataSourceId": source["id"]}
    for body in (params, with_id):
        response = await client.post(url, json=body, headers=headers)
        assert response.status_code == 200
        result = response.json()
        assert result["ok"] is True
        assert result["serverVersion"]
        assert result["code"] is None
        assert result["reason"] is None
        assert result["warnings"] == []
        assert external_source.reader_password not in response.text

    marker = "wrong-override-" + uuid4().hex
    rejected = await client.post(url, json={**with_id, "password": marker}, headers=headers)
    assert rejected.status_code == 200
    assert rejected.json()["ok"] is False
    assert rejected.json()["code"] == "datasource.connect_failed"
    assert rejected.json()["reason"] == "auth_failed"
    assert marker not in rejected.text
    assert (await client.get(SOURCES)).json() == [source]
    created, *tests = await _events(db)
    assert [(e.target_id, e.detail) for e in tests] == [
        (None, {"code": "ok"}),
        (source["id"], {"code": "ok"}),
        # With a password of its own the request did not use the data source: no target.
        (None, {"code": "datasource.connect_failed"}),
    ]
    for event in tests:
        assert (event.action, event.target_type) == ("datasource.tested", "data_source")
        assert event.actor_id == created.actor_id
    await _assert_audit_omits(db, external_source.reader_password, marker)
