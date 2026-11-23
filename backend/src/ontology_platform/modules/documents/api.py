"""Upload, inspect, download and retry documents."""

import asyncio
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile

from ontology_platform.db import DbSession
from ontology_platform.errors import AppError, problem_responses
from ontology_platform.modules.documents import service
from ontology_platform.modules.documents.schemas import ChunkInfo, DocumentInfo, DocumentList
from ontology_platform.modules.documents.storage import LocalDocumentStorage
from ontology_platform.modules.identity.api import AppSettings, CurrentUser, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.ontology import service as ontology

router = APIRouter(prefix="/api", tags=["documents"])

DocumentWriter = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]


@router.post(
    "/documents",
    status_code=201,
    responses={200: {"model": DocumentInfo}, **problem_responses(401, 403, 404, 413, 415, 422)},
)
async def upload_document(
    user: DocumentWriter,
    db: DbSession,
    settings: AppSettings,
    response: Response,
    file: UploadFile,
    ontology_id: Annotated[UUID, Form(alias="ontologyId")],
) -> DocumentInfo:
    if await ontology.get_ontology(db, ontology_id) is None:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    data = await file.read(settings.max_upload_mb * 1024**2 + 1)
    document, created = await service.upload(
        db,
        LocalDocumentStorage(settings.documents_dir),
        ontology_id=ontology_id,
        filename=file.filename or "",
        data=data,
        uploaded_by=user.id,
        max_upload_mb=settings.max_upload_mb,
    )
    await db.commit()
    if not created:
        response.status_code = 200
    return DocumentInfo.model_validate(document, from_attributes=True)


@router.get("/documents", responses=problem_responses(401, 404, 422))
async def list_documents(
    user: CurrentUser,
    db: DbSession,
    ontology_id: Annotated[UUID, Query(alias="ontologyId")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> DocumentList:
    documents, next_cursor = await service.list_by_ontology(
        db, ontology_id, limit=limit, cursor=cursor
    )
    return DocumentList(
        items=[DocumentInfo.model_validate(doc, from_attributes=True) for doc in documents],
        next_cursor=next_cursor,
    )


@router.get("/documents/{id}", responses=problem_responses(401, 404, 422))
async def get_document(id: UUID, user: CurrentUser, db: DbSession) -> DocumentInfo:
    return DocumentInfo.model_validate(await service.get(db, id), from_attributes=True)


@router.get("/documents/{id}/chunks/{chunkId}", responses=problem_responses(401, 404, 422))
async def get_document_chunk(
    id: UUID,
    chunkId: UUID,  # noqa: N803
    user: CurrentUser,
    db: DbSession,
) -> ChunkInfo:
    chunk = await service.get_chunk(db, id, chunkId)
    return ChunkInfo.model_validate(chunk, from_attributes=True)


@router.get(
    "/documents/{id}/file",
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        **problem_responses(401, 404, 422),
    },
)
async def download_document(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> Response:
    document = await service.get(db, id)
    storage = LocalDocumentStorage(settings.documents_dir)
    data = await asyncio.to_thread(storage.open, document.storage_key)
    disposition = f"attachment; filename*=UTF-8''{quote(document.filename, safe='')}"
    return Response(
        data,
        media_type=document.media_type,
        headers={
            "Content-Disposition": disposition,
            # The original may be confidential: never sniffed into another type, never cached.
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/documents/{id}/retry", responses=problem_responses(401, 403, 404, 409, 422))
async def retry_document(id: UUID, user: DocumentWriter, db: DbSession) -> DocumentInfo:
    document = await service.retry(db, id)
    await db.commit()
    return DocumentInfo.model_validate(document, from_attributes=True)
