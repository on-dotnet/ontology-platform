"""Parse and replace evidence chunks before invoking the registered extraction pipeline."""

import asyncio
import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import delete

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import parsers, service
from ontology_platform.modules.documents.chunking import TextChunk, chunk_pages
from ontology_platform.modules.documents.models import Chunk
from ontology_platform.modules.documents.parsers import (
    ParsedDocument,
    ParsedPage,
    ScanPart,
    parse_isolated,
)
from ontology_platform.modules.documents.storage import DocumentStorage
from ontology_platform.modules.jobs.runner import (
    JobContext,
    LeaseCheck,
    RetryableJobError,
    register,
)

logger = logging.getLogger(__name__)

type Extractor = Callable[[UUID, LeaseCheck], Awaitable[UUID | None]]
type VisionTranscriber = Callable[[ScanPart], Awaitable[list[ParsedPage]]]

# Recognition limit per document: it bounds the model calls (about two per 8,000 characters)
# and is shown next to the upload control, like `parsers.MAX_SCANNED_PAGES`.
MAX_RECOGNIZED_CHARS = 200_000

_extractor: Extractor | None = None
_transcriber: VisionTranscriber | None = None


def register_extractor(fn: Extractor | None) -> None:
    """An extractor can persist set_change_set in its change-set creation transaction for replay.

    It must call the lease check in that transaction first: an execution that lost its job
    must not add a change set whose evidence points at chunks a newer execution replaced.
    """
    global _extractor
    _extractor = fn


def register_vision_transcriber(fn: VisionTranscriber | None) -> None:
    global _transcriber
    _transcriber = fn


async def _record(job: JobContext, document_id: UUID, **values: object) -> None:
    """Write document columns (progress, counts) in a transaction of this execution."""
    async with job.session_factory.begin() as db:
        await job.check_lease(db)
        doc = await service.get_row(db, document_id)
        for name, value in values.items():
            setattr(doc, name, value)


def _transcript_name(part: ScanPart) -> str:
    return f"transcript-{part.first_page}-{part.page_count}.json"


def _saved_transcript(
    storage: DocumentStorage, document_id: UUID, part: ScanPart
) -> list[ParsedPage] | None:
    data = storage.open_derived(document_id, _transcript_name(part))
    if data is None:
        return None
    try:
        return [ParsedPage(**page) for page in json.loads(data)]
    except (ValueError, TypeError) as exc:
        logger.warning("Ignoring an unreadable saved transcript: %s", exc)
        return None


async def _transcribe_part(
    transcriber: VisionTranscriber, storage: DocumentStorage, document_id: UUID, part: ScanPart
) -> list[ParsedPage]:
    """A part transcribed by an earlier execution is read back instead of paid for again."""
    saved = await asyncio.to_thread(_saved_transcript, storage, document_id, part)
    if saved is not None:
        return saved
    pages = await transcriber(part)
    # A part without text is not kept: a retry asked for after "no text" transcribes it again.
    if any(page.text.strip() for page in pages):
        data = json.dumps([dataclasses.asdict(page) for page in pages], ensure_ascii=False)
        await asyncio.to_thread(
            storage.save_derived, document_id, _transcript_name(part), data.encode("utf-8")
        )
    return pages


async def _transcribe(
    job: JobContext, storage: DocumentStorage, document_id: UUID, parsed: ParsedDocument
) -> list[ParsedPage]:
    if _transcriber is None:
        raise AppError(422, "documents.needs_ocr", "This PDF requires vision transcription.")
    if parsed.page_count > parsers.MAX_SCANNED_PAGES:
        # Kept so that the page can say by how much the scan exceeds the limit.
        await _record(job, document_id, page_count=parsed.page_count)
        raise AppError(422, "documents.too_many_pages", "The scan has too many pages.")
    pages: list[ParsedPage] = []
    total = len(parsed.scan_parts)
    for done, part in enumerate(parsed.scan_parts):
        await _record(job, document_id, progress={"step": "parse", "done": done, "total": total})
        pages.extend(await _transcribe_part(_transcriber, storage, document_id, part))
    if not any(page.text.strip() for page in pages):
        raise AppError(422, "documents.unreadable", "Vision transcription returned no text.")
    return pages


async def _parse(
    job: JobContext, storage: DocumentStorage, document_id: UUID, key: str, media_type: str
) -> tuple[ParsedDocument, list[TextChunk]]:
    data = await asyncio.to_thread(storage.open, key)
    parsed = await parse_isolated(media_type, data)
    pages = (
        await _transcribe(job, storage, document_id, parsed)
        if parsed.needs_vision
        else parsed.pages
    )
    chunks = await asyncio.to_thread(chunk_pages, pages)
    char_count = sum(chunk.char_count for chunk in chunks)
    if char_count > MAX_RECOGNIZED_CHARS:
        await _record(job, document_id, char_count=char_count, page_count=parsed.page_count)
        raise AppError(422, "documents.too_long", "The document has too many characters.")
    return parsed, chunks


async def _process(job: JobContext, storage: DocumentStorage, document_id: UUID) -> None:
    async with job.session_factory.begin() as db:
        await job.check_lease(db)
        doc = await service.get_row(db, document_id)
        if doc.status == "ready":
            return
        if doc.change_set_id is not None:
            # Extraction committed its result before the previous worker acknowledged completion.
            doc.status = "ready"
            doc.error_code = None
            return
        if job.attempts > job.max_attempts:
            # Only reachable through stale-lease recovery: earlier executions died without
            # reporting (worker killed, parser stuck). Stop instead of retrying forever.
            raise AppError(500, "internal.error", "Processing was interrupted too often.")
        doc.status = "parsing"
        doc.error_code = None
        doc.progress = {"step": "parse", "done": 0, "total": 1}
        key, media_type = doc.storage_key, doc.media_type

    parsed, chunks = await _parse(job, storage, document_id, key, media_type)
    async with job.session_factory.begin() as db:
        await job.check_lease(db)
        doc = await service.get_row(db, document_id)
        await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.add_all(
            Chunk(
                document_id=document_id,
                seq=seq,
                text=chunk.text,
                page=chunk.page,
                heading=chunk.heading,
                char_count=chunk.char_count,
            )
            for seq, chunk in enumerate(chunks)
        )
        doc.char_count = sum(chunk.char_count for chunk in chunks)
        doc.page_count = parsed.page_count
        doc.status = "extracting"
        doc.progress = {"step": "parse", "done": 1, "total": 1}

    change_set_id = await _extractor(document_id, job.check_lease) if _extractor else None
    async with job.session_factory.begin() as db:
        await job.check_lease(db)
        doc = await service.get_row(db, document_id)
        doc.change_set_id = change_set_id
        doc.status = "ready"


async def process(job: JobContext, storage: DocumentStorage) -> None:
    document_id = UUID(job.payload["documentId"])
    try:
        await _process(job, storage, document_id)
    except Exception as exc:
        retry = isinstance(exc, RetryableJobError) and job.attempts < job.max_attempts
        code = exc.code if isinstance(exc, (RetryableJobError, AppError)) else "internal.error"
        async with job.session_factory.begin() as db:
            await job.check_lease(db)
            await service.set_status(
                db, document_id, "queued" if retry else "failed", error_code=None if retry else code
            )
        raise


def register_handlers(storage: DocumentStorage) -> None:
    async def handle(job: JobContext) -> None:
        await process(job, storage)

    register("document.process", handle)
