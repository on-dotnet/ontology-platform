import asyncio
import os
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from docx import Document as DocxDocument
from fastapi import FastAPI
from openpyxl import Workbook  # type: ignore[import-untyped]
from pypdf import PdfReader, PdfWriter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import parsers, processing, service
from ontology_platform.modules.documents.parsers import ParsedPage, ScanPart
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.jobs.runner import JobContext, LeaseCheck, RetryableJobError


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
    leases: list[LeaseCheck] = []

    async def extract(doc_id: UUID, check_lease: LeaseCheck) -> UUID:
        nonlocal calls
        assert doc_id == document_id
        leases.append(check_lease)
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
    # Each execution hands the extractor its own lease check for the change-set transaction.
    assert leases == [job.check_lease, second_attempt.check_lease]


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

    async def transcribe(part: ScanPart) -> list[ParsedPage]:
        assert (part.first_page, part.page_count) == (1, 1)
        assert len(PdfReader(BytesIO(part.data)).pages) == 1
        return [ParsedPage(1, "page one")]

    async def empty_transcription(_: ScanPart) -> list[ParsedPage]:
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

    async def unavailable(_: UUID, __: LeaseCheck) -> UUID:
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

    async def extractor(document: UUID, _: LeaseCheck) -> None:
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

    async def extract(doc_id: UUID, _: LeaseCheck) -> UUID:
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


FIXTURES = Path(__file__).parent / "fixtures/documents"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _word_with_headings() -> bytes:
    document = DocxDocument()
    document.add_paragraph("前言")
    document.add_heading("炼钢", level=1)
    document.add_heading("转炉", level=2)
    document.add_paragraph("每个炉次只冶炼一个钢种。")
    file = BytesIO()
    document.save(file)
    return file.getvalue()


def _workbook_with_sheets() -> bytes:
    workbook = Workbook()
    workbook.create_sheet("炉次").append(["钢种", "重量"])
    file = BytesIO()
    workbook.save(file)
    return file.getvalue()


@pytest.mark.parametrize(
    ("media_type", "data"),
    [
        ("text/markdown", "# 转炉\n\n每个炉次只冶炼一个钢种。".encode()),
        ("application/pdf", (FIXTURES / "text.pdf").read_bytes()),
        ("application/pdf", (FIXTURES / "blank.pdf").read_bytes()),
        # Headings and sheet numbers must survive the trip too.
        (DOCX, _word_with_headings()),
        (XLSX, _workbook_with_sheets()),
    ],
)
async def test_the_child_process_parses_like_the_parser(media_type: str, data: bytes) -> None:
    assert await parsers.parse_isolated(media_type, data) == parsers.parse_document(
        media_type, data
    )


async def test_parser_errors_come_back_from_the_child_process() -> None:
    with pytest.raises(AppError) as caught:
        await parsers.parse_isolated("application/x-unknown", b"x")
    error = caught.value
    assert (error.status, error.code, error.detail) == (
        415,
        "documents.unsupported_type",
        "Unsupported document type.",
    )


async def test_a_crashed_parser_makes_the_document_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsers, "PARSE_COMMAND", (sys.executable, "-c", "import os; os._exit(3)"))
    with pytest.raises(AppError) as caught:
        await parsers.parse_isolated("text/plain", b"steel")
    assert caught.value.code == "documents.unreadable"


async def test_a_parser_that_hangs_is_killed_and_fails_the_document(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "parser.pid"
    hang = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    monkeypatch.setattr(parsers, "PARSE_COMMAND", (sys.executable, "-c", hang))
    monkeypatch.setattr(parsers, "PARSE_TIMEOUT", 3.0)
    storage = LocalDocumentStorage(tmp_path / "store")
    document_id, job = await prepare(app, storage, "malformed.txt", b"steel")

    with pytest.raises(AppError) as caught:
        await processing.process(job, storage)

    assert caught.value.code == "documents.parse_timeout"
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        assert (doc.status, doc.error_code) == ("failed", "documents.parse_timeout")


async def test_a_cancelled_parse_kills_the_child_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "parser.pid"
    hang = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(60)"
    monkeypatch.setattr(parsers, "PARSE_COMMAND", (sys.executable, "-c", hang))
    task = asyncio.create_task(parsers.parse_isolated("text/plain", b"steel"))
    # Polling a file the child writes; there is no event to wait for across processes.
    for _ in range(200):
        if pid_file.exists() and pid_file.read_text():
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail("the parser process did not start")

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


async def test_the_child_process_gets_no_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_OPENAI_API_KEY", "sk-test-not-a-key")
    report = (
        "import json, os, sys; sys.stdout.write(json.dumps({'pages': [{'number': None, "
        "'text': ' '.join(sorted(os.environ)), 'heading': None}], 'pageCount': 1, "
        "'needsVision': False, 'scanParts': []}))"
    )
    monkeypatch.setattr(parsers, "PARSE_COMMAND", (sys.executable, "-c", report))

    [page] = (await parsers.parse_isolated("text/plain", b"steel")).pages

    assert "OP_OPENAI_API_KEY" not in page.text.split()


async def test_unexpected_output_makes_the_document_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parsers, "PARSE_COMMAND", (sys.executable, "-c", "print('warning')"))
    with pytest.raises(AppError) as caught:
        await parsers.parse_isolated("text/plain", b"steel")
    assert caught.value.code == "documents.unreadable"


def blank_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    file = BytesIO()
    writer.write(file)
    return file.getvalue()


async def test_a_scan_is_transcribed_in_parts_of_five_pages(app: FastAPI, tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path)
    document_id, job = await prepare(app, storage, "scan.pdf", blank_pdf(12))
    parts: list[tuple[int, int, int]] = []

    async def transcribe(part: ScanPart) -> list[ParsedPage]:
        parts.append((part.first_page, part.page_count, len(PdfReader(BytesIO(part.data)).pages)))
        return [ParsedPage(part.first_page, f"第 {part.first_page} 页起")]

    processing.register_vision_transcriber(transcribe)
    try:
        await processing.process(job, storage)
    finally:
        processing.register_vision_transcriber(None)

    assert parts == [(1, 5, 5), (6, 5, 5), (11, 2, 2)]
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
        chunks = await service.list_chunks(db, document_id)
    assert (doc.status, doc.page_count) == ("ready", 12)
    assert [chunk.page for chunk in chunks] == [1, 6, 11]


async def test_a_scan_with_too_many_pages_fails_before_transcription(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing, "MAX_SCANNED_PAGES", 2)
    storage = LocalDocumentStorage(tmp_path)
    document_id, job = await prepare(app, storage, "scan.pdf", blank_pdf(3))
    calls: list[ScanPart] = []

    async def transcribe(part: ScanPart) -> list[ParsedPage]:
        calls.append(part)
        return [ParsedPage(1, "x")]

    processing.register_vision_transcriber(transcribe)
    try:
        with pytest.raises(AppError) as caught:
            await processing.process(job, storage)
    finally:
        processing.register_vision_transcriber(None)

    assert caught.value.code == "documents.too_many_pages"
    assert calls == []
    async with job.session_factory() as db:
        doc = await service.get(db, document_id)
    # The page count stays so that the page can say how far over the limit the scan is.
    assert (doc.status, doc.error_code, doc.page_count) == (
        "failed",
        "documents.too_many_pages",
        3,
    )


async def test_a_document_over_the_character_limit_fails_before_recognition(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing, "MAX_RECOGNIZED_CHARS", 100)
    storage = LocalDocumentStorage(tmp_path)
    calls: list[UUID] = []

    async def extract(document: UUID, _: LeaseCheck) -> None:
        calls.append(document)

    processing.register_extractor(extract)
    try:
        at_limit, job = await prepare(app, storage, "short.txt", ("炉" * 100).encode())
        await processing.process(job, storage)
        over_limit, job = await prepare(app, storage, "long.txt", ("钢" * 101).encode())
        with pytest.raises(AppError) as caught:
            await processing.process(job, storage)
    finally:
        processing.register_extractor(None)

    assert caught.value.code == "documents.too_long"
    assert calls == [at_limit]
    async with job.session_factory() as db:
        doc = await service.get(db, over_limit)
        chunks = await service.list_chunks(db, over_limit)
    assert (doc.status, doc.error_code, doc.char_count) == ("failed", "documents.too_long", 101)
    assert chunks == []
