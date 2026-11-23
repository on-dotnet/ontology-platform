"""Public metadata for uploaded documents and their evidence chunks."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from ontology_platform.schemas import CamelModel


class DocumentProgress(CamelModel):
    step: str
    done: int
    total: int


class DocumentInfo(CamelModel):
    id: UUID
    ontology_id: UUID
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    status: Literal["queued", "parsing", "extracting", "ready", "failed"]
    progress: DocumentProgress
    error_code: str | None
    page_count: int | None
    char_count: int | None
    change_set_id: UUID | None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime


class DocumentList(CamelModel):
    items: list[DocumentInfo]
    next_cursor: UUID | None


class ChunkInfo(CamelModel):
    id: UUID
    document_id: UUID
    seq: int
    text: str
    page: int | None
    heading: str | None
    char_count: int
