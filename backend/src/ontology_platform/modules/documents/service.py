"""Document metadata and queue operations in the caller's transaction."""

import asyncio
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.documents.parsers import detect_type
from ontology_platform.modules.documents.storage import DocumentStorage
from ontology_platform.modules.jobs import service as jobs


async def upload(
    db: AsyncSession,
    storage: DocumentStorage,
    *,
    ontology_id: UUID,
    filename: str,
    data: bytes,
    uploaded_by: UUID,
    max_upload_mb: int,
) -> tuple[Document, bool]:
    if len(data) > max_upload_mb * 1024**2:
        raise AppError(413, "documents.too_large", "The document exceeds the upload limit.")
    media_type = await asyncio.to_thread(detect_type, filename, data)
    storage_key, sha256 = await asyncio.to_thread(storage.save, data)
    statement = insert(Document).values(
        ontology_id=ontology_id,
        filename=filename,
        media_type=media_type,
        size_bytes=len(data),
        sha256=sha256,
        storage_key=storage_key,
        status="queued",
        progress={"step": "parse", "done": 0, "total": 1},
        uploaded_by=uploaded_by,
    )
    statement = statement.on_conflict_do_nothing(
        index_elements=[Document.ontology_id, Document.sha256]
    )
    document = await db.scalar(statement.returning(Document))
    if document is None:
        existing = select(Document).where(
            Document.ontology_id == ontology_id, Document.sha256 == sha256
        )
        return (await db.scalars(existing)).one(), False
    await jobs.enqueue(db, "document.process", {"documentId": str(document.id)})
    audit.record(
        db,
        "document.uploaded",
        actor_id=uploaded_by,
        target_type="document",
        target_id=str(document.id),
    )
    return document, True


def _not_found() -> AppError:
    return AppError(404, "documents.not_found", "Document or chunk not found.")


async def get(db: AsyncSession, document_id: UUID) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise _not_found()
    return document


async def list_by_ontology(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    limit: int = 50,
    cursor: UUID | None = None,
) -> tuple[list[Document], UUID | None]:
    statement = select(Document).where(Document.ontology_id == ontology_id)
    if cursor is not None:
        boundary = await db.scalar(statement.where(Document.id == cursor))
        if boundary is None:
            raise _not_found()
        statement = statement.where(
            tuple_(Document.created_at, Document.id) < tuple_(boundary.created_at, boundary.id)
        )
    statement = statement.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
    rows = (await db.scalars(statement)).all()
    return list(rows[:limit]), rows[limit - 1].id if len(rows) > limit else None


async def get_chunk(db: AsyncSession, document_id: UUID, chunk_id: UUID) -> Chunk:
    statement = select(Chunk).where(Chunk.id == chunk_id, Chunk.document_id == document_id)
    chunk = await db.scalar(statement)
    if chunk is None:
        raise _not_found()
    return chunk


async def list_chunks(db: AsyncSession, document_id: UUID) -> list[Chunk]:
    await get(db, document_id)
    statement = select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.seq)
    return list(await db.scalars(statement))


async def retry(db: AsyncSession, document_id: UUID) -> Document:
    statement = select(Document).where(Document.id == document_id).with_for_update()
    document = await db.scalar(statement.execution_options(populate_existing=True))
    if document is None:
        raise _not_found()
    if document.status != "failed":
        raise AppError(409, "documents.not_failed", "Only a failed document can be retried.")
    document.status = "queued"
    document.error_code = None
    document.progress = {"step": "parse", "done": 0, "total": 1}
    await jobs.enqueue(db, "document.process", {"documentId": str(document.id)})
    await db.flush()
    await db.refresh(document)
    return document


async def set_progress(
    db: AsyncSession, document_id: UUID, step: str, done: int, total: int
) -> None:
    document = await get(db, document_id)
    document.progress = {"step": step, "done": done, "total": total}


async def set_status(
    db: AsyncSession, document_id: UUID, status: str, *, error_code: str | None = None
) -> None:
    document = await get(db, document_id)
    document.status = status
    document.error_code = error_code


async def set_change_set(db: AsyncSession, document_id: UUID, change_set_id: UUID | None) -> None:
    document = await get(db, document_id)
    document.change_set_id = change_set_id


async def lock(db: AsyncSession, document_id: UUID) -> Document:
    """The document row, locked until the end of the caller's transaction."""
    statement = select(Document).where(Document.id == document_id).with_for_update()
    document = await db.scalar(statement.execution_options(populate_existing=True))
    if document is None:
        raise _not_found()
    return document


async def count_processing(db: AsyncSession) -> int:
    """Documents that are queued or being parsed or extracted, across all ontologies."""
    statement = (
        select(func.count())
        .select_from(Document)
        .where(Document.status.in_(("queued", "parsing", "extracting")))
    )
    return await db.scalar(statement) or 0
