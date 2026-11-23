"""Tables of the ai module: one row per model call, for usage accounting and troubleshooting.

Prompts and document text are deliberately not stored.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base


class AiRun(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'failed')", name="status"),
        Index(None, "created_at"),
        Index(None, "document_id"),
        {"schema": "ai"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    purpose: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    document_id: Mapped[UUID | None]
    status: Mapped[str] = mapped_column(String(16))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    latency_ms: Mapped[int]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
