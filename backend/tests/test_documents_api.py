"""Document routes, isolation by ontology, and upload/retry transaction effects."""

import asyncio
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.documents import service
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import create_user
from ontology_platform.modules.jobs.models import Job
from ontology_platform.settings import Settings
from support import ADMIN_PASSWORD, ADMIN_USERNAME, csrf_headers, login
from test_ontology_support import add_ontology


@pytest.fixture
def settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        database_url=database_url,
        admin_username=ADMIN_USERNAME,
        admin_password=SecretStr(ADMIN_PASSWORD),
        documents_dir=str(tmp_path),
        max_upload_mb=1,
    )


async def new_ontology(db: AsyncSession) -> UUID:
    return (await add_ontology(db, key=f"docs-{uuid4().hex[:8]}")).id


async def upload(
    client: AsyncClient,
    ontology_id: UUID,
    filename: str = "炉次.txt",
    data: bytes = b"original text",
) -> Response:
    return await client.post(
        "/api/documents",
        files={"file": (filename, data, "application/octet-stream")},
        data={"ontologyId": str(ontology_id)},
        headers=csrf_headers(client),
    )


async def test_upload_deduplicates_within_ontology(client: AsyncClient, db: AsyncSession) -> None:
    actor = (await login(client)).json()
    ontology_id = await new_ontology(db)
    first = await upload(client, ontology_id)
    duplicate = await upload(client, ontology_id, "renamed.txt")
    other = await upload(client, await new_ontology(db))

    assert first.status_code == other.status_code == 201
    document = first.json()
    assert document["status"] == "queued"
    assert document["uploadedBy"] == actor["id"]
    assert document["progress"] == {"step": "parse", "done": 0, "total": 1}
    assert "storageKey" not in document
    assert "errorDetail" not in document
    assert duplicate.status_code == 200
    assert duplicate.json() == document
    assert other.json()["id"] != document["id"]
    jobs = (await db.scalars(select(Job))).all()
    assert {job.kind for job in jobs} == {"document.process"}
    assert sorted(job.payload["documentId"] for job in jobs) == sorted(
        [document["id"], other.json()["id"]]
    )
    events = await db.scalars(select(AuditEvent).where(AuditEvent.action == "document.uploaded"))
    assert sorted(e.target_id for e in events if e.target_id) == sorted(
        [document["id"], other.json()["id"]]
    )


async def test_filter_paginate_read_and_download(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    ontology_id = await new_ontology(db)
    original = (await upload(client, ontology_id)).json()
    newer = (await upload(client, ontology_id, data=b"more")).json()
    foreign = (await upload(client, await new_ontology(db))).json()
    query = {"ontologyId": str(ontology_id), "limit": "1"}
    first = (await client.get("/api/documents", params=query)).json()
    assert first["items"] == [newer]
    second = await client.get("/api/documents", params={**query, "cursor": first["nextCursor"]})
    assert second.json() == {"items": [original], "nextCursor": None}

    url = f"/api/documents/{original['id']}"
    assert (await client.get(url)).json() == original
    raw = await client.get(f"{url}/file")
    assert raw.content == b"original text"
    assert raw.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote('炉次.txt')}"
    assert raw.headers["x-content-type-options"] == "nosniff"
    assert raw.headers["cache-control"] == "private, no-store"
    chunk = Chunk(document_id=UUID(original["id"]), seq=1, text="hello", page=3, char_count=5)
    db.add(chunk)
    await db.commit()
    fragment = (await client.get(f"{url}/chunks/{chunk.id}")).json()
    assert fragment["text"] == "hello"
    assert fragment["page"] == 3
    assert fragment["documentId"] == original["id"]
    for path in (
        f"/api/documents/{uuid4()}",
        f"/api/documents/{uuid4()}/file",
        f"/api/documents/{foreign['id']}/chunks/{chunk.id}",
    ):
        missing = await client.get(path)
        assert missing.status_code == 404
        assert missing.json()["code"] == "documents.not_found"


async def test_concurrent_uploads_enqueue_once(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    ontology_id = await new_ontology(db)
    a, b = await asyncio.gather(upload(client, ontology_id), upload(client, ontology_id))
    assert sorted([a.status_code, b.status_code]) == [200, 201]
    assert a.json()["id"] == b.json()["id"]
    assert await db.scalar(select(func.count()).select_from(Job)) == 1


async def test_upload_rollback_includes_job_and_audit(db: AsyncSession, tmp_path: Path) -> None:
    user = await create_user(db, username="owner", password="owner-password", role=Role.EDITOR)
    await db.commit()
    await service.upload(
        db,
        LocalDocumentStorage(tmp_path),
        ontology_id=uuid4(),
        filename="draft.txt",
        data=b"draft",
        uploaded_by=user.id,
        max_upload_mb=1,
    )
    await db.flush()
    await db.rollback()
    assert await db.scalar(select(func.count()).select_from(Document)) == 0
    assert await db.scalar(select(func.count()).select_from(Job)) == 0
    audit_ids = select(AuditEvent.id).where(AuditEvent.action == "document.uploaded")
    assert await db.scalar(audit_ids) is None


async def test_upload_limits_and_type(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    too_large = await upload(client, await new_ontology(db), data=b"x" * (1024**2 + 1))
    assert too_large.status_code == 413
    assert too_large.json()["code"] == "documents.too_large"
    unsupported = await upload(client, await new_ontology(db), "fake.pdf")
    assert unsupported.status_code == 415
    assert unsupported.json()["code"] == "documents.unsupported_type"
    unknown = await upload(client, uuid4())
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "ontology.not_found"
    assert await db.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize("role", [Role.EDITOR, Role.REVIEWER, Role.VIEWER])
async def test_document_roles(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    ontology_id = await new_ontology(db)
    anonymous = await client.get("/api/documents", params={"ontologyId": str(ontology_id)})
    assert anonymous.status_code == 401
    for path in ("", "/file", f"/chunks/{uuid4()}"):
        assert (await client.get(f"/api/documents/{uuid4()}{path}")).status_code == 401
    await create_user(db, username="tester", password="tester-password", role=role)
    await db.commit()
    await login(client, username="tester", password="tester-password")
    response = await upload(client, ontology_id)
    listing = await client.get("/api/documents", params={"ontologyId": str(ontology_id)})
    assert listing.status_code == 200
    if role == Role.VIEWER:
        assert response.status_code == 403
        assert response.json()["code"] == "auth.forbidden"
        denied = await client.post(f"/api/documents/{uuid4()}/retry", headers=csrf_headers(client))
        assert denied.status_code == 403
        assert denied.json()["code"] == "auth.forbidden"
    else:
        assert response.status_code == 201


async def test_retry_only_requeues_failed_document(client: AsyncClient, db: AsyncSession) -> None:
    await login(client)
    document_id = UUID((await upload(client, await new_ontology(db))).json()["id"])
    url = f"/api/documents/{document_id}/retry"
    conflict = await client.post(url, headers=csrf_headers(client))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "documents.not_failed"
    document = await db.get(Document, document_id)
    assert document is not None
    document.status = "failed"
    document.error_code = "ai.unavailable"
    await db.commit()

    retried = await client.post(url, headers=csrf_headers(client))
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["errorCode"] is None
    jobs = (await db.scalars(select(Job))).all()
    assert [job.payload for job in jobs] == [{"documentId": str(document_id)}] * 2
