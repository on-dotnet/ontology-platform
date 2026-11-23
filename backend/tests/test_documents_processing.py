from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import processing, service
from ontology_platform.modules.documents.parsers import ParsedPage
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError


async def prepare(
    app: FastAPI, storage: LocalDocumentStorage, filename: str, data: bytes
) -> tuple[UUID, JobContext]:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory.begin() as db:
        doc, _ = await service.upload(
            db,
            storage,
            ontology_id=uuid4(),
            uploaded_by=uuid4(),
            filename=filename,
            data=data,
            max_upload_mb=20,
        )
    return doc.id, JobContext(
        id=uuid4(),
        payload={"documentId": str(doc.id)},
        session_factory=factory,
    )


async def test_retry_replaces_chunks_and_links_change_set(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    text = "钢坯。\n" * 1020
    document_id, job = await prepare(app, storage, "steel.md", text.encode())
    result = uuid4()
    calls = 0

    async def extract(doc_id: UUID) -> UUID:
        nonlocal calls
        assert doc_id == document_id
        calls += 1
        if calls == 1:
            raise RetryableJobError("ai.unavailable")
        return result

    processing.register_extractor(extract)
    try:
        with pytest.raises(RetryableJobError):
            await processing.process(job, storage)
        async with job.session_factory() as db:
            assert (await service.get(db, document_id)).status == "queued"
        second_attempt = replace(job, attempts=2)
        await processing.process(second_attempt, storage)
        await processing.process(second_attempt, storage)
    finally:
        processing.register_extractor(None)
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        chunks = await service.list_chunks(db, document_id)
        assert doc.status == "ready"
        assert doc.change_set_id == result
        assert doc.char_count == len(text)
        assert len(chunks) >= 2
        assert "".join(chunk.text for chunk in chunks) == text
        assert calls == 2


async def test_vision_registration(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    data = (Path(__file__).parent / "fixtures/documents/blank.pdf").read_bytes()
    document_id, job = await prepare(app, storage, "blank.pdf", data)
    with pytest.raises(AppError, match="transcription") as caught:
        await processing.process(job, storage)
    assert caught.value.code == "documents.needs_ocr"
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        assert (doc.status, doc.error_code) == ("failed", "documents.needs_ocr")

    async def transcribe(original: bytes) -> list[ParsedPage]:
        assert original == data
        return [ParsedPage(1, "page one")]

    async def empty_transcription(_: bytes) -> list[ParsedPage]:
        return [ParsedPage(1, "  ")]

    processing.register_vision_transcriber(empty_transcription)
    try:
        with pytest.raises(AppError, match="no text") as empty:
            await processing.process(job, storage)
        assert empty.value.code == "documents.unreadable"
    finally:
        processing.register_vision_transcriber(None)

    processing.register_vision_transcriber(transcribe)
    try:
        await processing.process(job, storage)
    finally:
        processing.register_vision_transcriber(None)
    async with job.session_factory() as db:
        assert (await service.get(db, document_id)).status == "ready"
        (chunk,) = await service.list_chunks(db, document_id)
        assert (chunk.page, chunk.text) == (1, "page one")


async def test_exhausted_extractor_retries_fail_document(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    document_id, job = await prepare(app, storage, "steel.txt", b"steel")

    async def unavailable(_: UUID) -> UUID:
        raise RetryableJobError("ai.unavailable")

    processing.register_extractor(unavailable)
    try:
        with pytest.raises(RetryableJobError, match=r"ai\.unavailable"):
            await processing.process(replace(job, attempts=job.max_attempts), storage)
    finally:
        processing.register_extractor(None)
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        assert (doc.status, doc.error_code) == ("failed", "ai.unavailable")


async def test_a_job_recovered_too_often_fails_the_document(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    document_id, job = await prepare(app, storage, "steel.txt", b"steel")
    calls: list[UUID] = []

    async def extractor(document: UUID) -> None:
        calls.append(document)

    processing.register_extractor(extractor)
    try:
        with pytest.raises(AppError, match="interrupted"):
            await processing.process(replace(job, attempts=job.max_attempts + 1), storage)
    finally:
        processing.register_extractor(None)
    assert calls == []
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        assert (doc.status, doc.error_code) == ("failed", "internal.error")


async def test_recovery_preserves_committed_evidence(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    document_id, job = await prepare(app, storage, "steel.txt", b"steel")
    result = uuid4()
    anchors: list[UUID] = []

    async def extract(doc_id: UUID) -> UUID:
        async with job.session_factory.begin() as db:
            (chunk,) = await service.list_chunks(db, doc_id)
            anchors.append(chunk.id)
            await service.set_change_set(db, doc_id, result)
        raise RetryableJobError("ai.unavailable")

    processing.register_extractor(extract)
    try:
        with pytest.raises(RetryableJobError, match=r"ai\.unavailable"):
            await processing.process(job, storage)
        await processing.process(replace(job, attempts=2), storage)
    finally:
        processing.register_extractor(None)
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        assert (doc.status, doc.change_set_id) == ("ready", result)
        assert [chunk.id for chunk in await service.list_chunks(db, document_id)] == anchors
