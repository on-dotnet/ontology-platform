"""Parse and replace evidence chunks before invoking the registered extraction pipeline."""

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import delete

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import service
from ontology_platform.modules.documents.chunking import TextChunk, chunk_pages
from ontology_platform.modules.documents.models import Chunk
from ontology_platform.modules.documents.parsers import ParsedDocument, ParsedPage, parse_isolated
from ontology_platform.modules.documents.storage import DocumentStorage
from ontology_platform.modules.jobs.runner import (
    JobContext,
    LeaseCheck,
    RetryableJobError,
    register,
)

type Extractor = Callable[[UUID, LeaseCheck], Awaitable[UUID | None]]
type VisionTranscriber = Callable[[bytes], Awaitable[list[ParsedPage]]]

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


async def _parse(
    storage: DocumentStorage, key: str, media_type: str
) -> tuple[ParsedDocument, list[TextChunk]]:
    data = await asyncio.to_thread(storage.open, key)
    parsed = await parse_isolated(media_type, data)
    pages = parsed.pages
    if parsed.needs_vision:
        if _transcriber is None:
            raise AppError(422, "documents.needs_ocr", "This PDF requires vision transcription.")
        pages = await _transcriber(data)
        if not any(page.text.strip() for page in pages):
            raise AppError(422, "documents.unreadable", "Vision transcription returned no text.")
    return parsed, await asyncio.to_thread(chunk_pages, pages)


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

    parsed, chunks = await _parse(storage, key, media_type)
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
