"""Public metadata for uploaded documents and their evidence chunks."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict

from ontology_platform.schemas import CamelModel

# Other modules receive these as read-only copies, never the ORM rows (see service.get).
_FROZEN = ConfigDict(frozen=True)


class DocumentProgress(CamelModel):
    model_config = _FROZEN

    step: str
    done: int
    total: int


class DocumentInfo(CamelModel):
    model_config = _FROZEN

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
    model_config = _FROZEN

    id: UUID
    document_id: UUID
    seq: int
    text: str
    page: int | None
    heading: str | None
    char_count: int
