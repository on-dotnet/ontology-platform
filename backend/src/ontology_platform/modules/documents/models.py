"""Tables of the documents module (see docs/specs/001-m1-ai-ingestion.md)."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("ontology_id", "sha256"),
        Index("ix_documents_ontology_id_created_at_id", "ontology_id", "created_at", "id"),
        CheckConstraint(
            "status IN ('queued', 'parsing', 'extracting', 'ready', 'failed')", name="status"
        ),
        {"schema": "documents"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID]
    filename: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="queued")
    progress: Mapped[dict[str, Any]] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None]
    char_count: Mapped[int | None]
    change_set_id: Mapped[UUID | None]
    uploaded_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "seq"),
        {"schema": "documents"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.documents.id", ondelete="CASCADE")
    )
    seq: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None]
    heading: Mapped[str | None] = mapped_column(Text)
    char_count: Mapped[int]
