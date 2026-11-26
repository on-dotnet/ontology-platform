"""Credentials are encrypted at rest and never shown (spec 003, 5.4; section 15, the connector
part of "凭据不回显" and its "另测")."""

import logging
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from external_source import ExternalSource
from ontology_platform.modules.connectors import config, jobs
from ontology_platform.modules.connectors.errors import CredentialUnreadableError
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.connectors.rekey import rekey
from ontology_platform.modules.connectors.secrets import current_key_id, open_password, seal
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs import service as queue
from ontology_platform.modules.jobs.models import Job
from ontology_platform.settings import Settings
from support import csrf_headers
from test_ontology_support import sign_in

OLD_KEY = "old-key-" + "a" * 32
NEW_KEY = "new-key-" + "b" * 32


def _settings(key: str, previous: str | None = None) -> Settings:
    return Settings(
        secret_key=SecretStr(key),
        secret_key_previous=SecretStr(previous) if previous else None,
    )


# ---------- encryption ----------


def test_sealed_credentials_open_only_for_their_row_and_key() -> None:
    settings = _settings(OLD_KEY)
    row_id = uuid4()
    marker = "pw-" + uuid4().hex

    sealed = seal(settings, row_id, SecretStr(marker))
    again = seal(settings, row_id, SecretStr(marker))

    assert marker.encode() not in sealed.secret
    assert sealed.secret != again.secret  # a fresh nonce every time
    assert sealed.secret[:1] == b"\x01"
    assert len(sealed.key_id) == 16
    assert sealed.key_id == current_key_id(settings)
    assert open_password(settings, row_id, sealed.secret, sealed.key_id).get_secret_value() == marker
    with pytest.raises(CredentialUnreadableError):
        open_password(settings, uuid4(), sealed.secret, sealed.key_id)  # moved to another row
    tampered = sealed.secret[:-1] + bytes([sealed.secret[-1] ^ 1])
    with pytest.raises(CredentialUnreadableError):
        open_password(settings, row_id, tampered, sealed.key_id)
    with pytest.raises(CredentialUnreadableError):
        open_password(_settings(NEW_KEY), row_id, sealed.secret, sealed.key_id)


def test_previous_keys_open_old_credentials_during_rotation() -> None:
    row_id = uuid4()
    sealed = seal(_settings(OLD_KEY), row_id, SecretStr("pw"))

    rotating = _settings(NEW_KEY, previous=f"unrelated-{'c' * 32}, {OLD_KEY}")

    assert open_password(rotating, row_id, sealed.secret, sealed.key_id).get_secret_value() == "pw"
    assert seal(rotating, row_id, SecretStr("pw")).key_id == current_key_id(_settings(NEW_KEY))


async def test_rekey_leaves_only_the_new_key(db: AsyncSession) -> None:
    old = _settings(OLD_KEY)
    rows = []
    for index in range(3):
        row = DataSource(
            id=uuid4(), name=f"rekey {index}", kind="postgresql", host="h", port=5432,
            database="d", username="u",
        )
        sealed = seal(old, row.id, SecretStr(f"pw-{index}"))
        row.secret, row.secret_key_id = sealed.secret, sealed.key_id
        rows.append(row)
    lost = DataSource(
        id=uuid4(), name="lost key", kind="postgresql", host="h", port=5432, database="d",
        username="u", secret=b"\x01" + bytes(40), secret_key_id="0" * 16,
    )
    db.add_all([*rows, lost])
    await db.commit()
    rotating = _settings(NEW_KEY, previous=OLD_KEY)

    result = await rekey(db, rotating)
    await db.commit()

    assert (result.rekeyed, result.unreadable) == (3, 1)
    key_ids = set(await db.scalars(select(DataSource.secret_key_id)))
    assert key_ids == {current_key_id(rotating), "0" * 16}
    after = _settings(NEW_KEY)  # OP_SECRET_KEY_PREVIOUS removed
    for index, row in enumerate(rows):
        stored = await db.get(DataSource, row.id, populate_existing=True)
        assert stored is not None and stored.secret is not None
        password = open_password(after, row.id, stored.secret, stored.secret_key_id)
        assert password.get_secret_value() == f"pw-{index}"
    assert (await rekey(db, rotating)).rekeyed == 0


# ---------- never shown: the connector part of the scan ----------


class _Recorder:
    def __init__(self, client: AsyncClient) -> None:
        self.client = client
        self.responses: list[Response] = []

    async def __call__(self, method: str, url: str, **kwargs: Any) -> Response:
        if method != "GET":
            kwargs.setdefault("headers", csrf_headers(self.client))
        response = await self.client.request(method, url, **kwargs)
        self.responses.append(response)
        return response


@pytest.fixture
def worker(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    monkeypatch.setattr(config, "_configured", settings)
    monkeypatch.setattr(runner, "_handlers", {})
    jobs.register_handlers(factory, settings)
    return factory


async def _run_jobs(factory: async_sessionmaker[AsyncSession]) -> None:
    while True:
        async with factory.begin() as db:
            job = await queue.claim(db, "secret-scan")
        if job is None:
            return
        context = runner.JobContext(
            job.id, job.payload, factory, attempts=job.attempts, worker_id="secret-scan"
        )
        await runner._execute(job.kind, context, "secret-scan")


async def _stored_text(db: AsyncSession) -> str:
    """Everything the platform keeps about the flow, as text."""
    parts: list[str] = []
    for table in ("audit.events", "jobs.jobs", "connectors.data_sources", "connectors.catalog_tables"):
        rows = await db.execute(text(f"SELECT to_jsonb(t)::text FROM {table} t"))  # noqa: S608
        parts.extend(row[0] for row in rows)
    return "\n".join(parts)


async def test_passwords_hosts_and_users_never_show(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    worker: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    good = external_source.reader_password
    bad = "op-secret-pw-" + uuid4().hex
    bad_host = f"op-secret-host-{uuid4().hex[:12]}.invalid"
    bad_user = f"op_secret_user_{uuid4().hex[:12]}"
    markers = [good, bad, bad_host, bad_user]
    call = _Recorder(client)
    await sign_in(client, db, Role.ADMIN)
    connection: dict[str, Any] = {
        "kind": "postgresql",
        "host": external_source.host,
        "port": external_source.port,
        "database": external_source.database,
        "username": external_source.reader,
        "sslMode": "disable",
        "schemas": ["mes"],
    }

    created = await call("POST", "/api/data-sources", json={**connection, "name": "MES", "password": bad})
    assert created.status_code == 201
    source = created.json()
    base = f"/api/data-sources/{source['id']}"
    failed_test = await call("POST", f"{base}/test")
    await call("POST", f"{base}/catalog/refresh")
    await _run_jobs(worker)
    failed_catalog = await call("GET", base)
    changed = await call(
        "PATCH", base, json={"password": good, "revision": failed_catalog.json()["revision"]}
    )
    passed_test = await call("POST", f"{base}/test")
    await call("POST", f"{base}/catalog/refresh")
    await _run_jobs(worker)
    await call("GET", f"{base}/catalog/tables/mes/heat")
    await call("POST", "/api/data-sources/test", json={**connection, "password": bad})
    await call("POST", "/api/data-sources/test", json={**connection, "dataSourceId": source["id"]})
    unreachable = await call(
        "POST", "/api/data-sources/test", json={**connection, "host": bad_host, "password": bad}
    )
    unknown_user = await call(
        "POST", "/api/data-sources/test", json={**connection, "username": bad_user, "password": bad}
    )
    renamed = await call(
        "PATCH", base, json={"name": "MES 2", "revision": changed.json()["revision"]}
    )
    archived = await call("POST", f"{base}/archive")
    await call("GET", "/api/data-sources")

    assert failed_test.json()["reason"] == "auth_failed"
    assert failed_catalog.json()["catalog"]["errorCode"] == "datasource.connect_failed"
    assert passed_test.json()["ok"] is True
    assert unreachable.json()["reason"] == "unreachable"
    assert unknown_user.json()["reason"] == "auth_failed"
    assert renamed.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["hasCredential"] is False
    stored = await _stored_text(db)
    logs = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [caplog.text]
    )
    for marker in markers:
        for response in call.responses:
            assert marker not in response.text, response.request.url
            assert all(marker not in value for value in response.headers.values())
        assert marker not in logs
        assert marker not in stored
    job_rows = (await db.execute(select(Job.error_code, Job.error_detail))).all()
    assert job_rows and all(detail is None for _, detail in job_rows)


async def test_a_wrong_key_reads_as_credential_unreadable(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    await sign_in(client, db, Role.ADMIN)
    created = await client.post(
        "/api/data-sources",
        headers=csrf_headers(client),
        json={
            "name": "MES",
            "kind": "postgresql",
            "host": external_source.host,
            "port": external_source.port,
            "database": external_source.database,
            "username": external_source.reader,
            "password": external_source.reader_password,
        },
    )
    source_id = UUID(created.json()["id"])
    # Sealed with a key the platform no longer has.
    sealed = seal(_settings(OLD_KEY), source_id, SecretStr(external_source.reader_password))
    await db.execute(
        update(DataSource)
        .where(DataSource.id == source_id)
        .values(secret=sealed.secret, secret_key_id=sealed.key_id)
    )
    await db.commit()

    response = await client.post(
        f"/api/data-sources/{source_id}/test", headers=csrf_headers(client)
    )

    assert response.status_code == 409
    assert response.json()["code"] == "datasource.credential_unreadable"
