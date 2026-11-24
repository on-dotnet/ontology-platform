"""Tables of the ai module: one row per model call, for usage accounting and troubleshooting,
and the AI assistant's requests.

Prompts and document text are deliberately not stored. An assistant request keeps the user's
own words and the short reply, so that the panel can show them again (spec 002, section 10).
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base

AssistantStatus = Literal["queued", "running", "succeeded", "failed"]
AssistantStep = Literal["context", "model", "changeset"]
MESSAGE_MAX_LENGTH = 2000


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


class AssistantRequest(Base):
    """One instruction to the AI assistant and what came of it."""

    __tablename__ = "assistant_requests"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="status"),
        CheckConstraint("step IS NULL OR step IN ('context', 'model', 'changeset')", name="step"),
        CheckConstraint(f"char_length(message) BETWEEN 1 AND {MESSAGE_MAX_LENGTH}", name="message"),
        CheckConstraint("dropped >= 0", name="dropped"),
        Index(None, "ontology_id", "user_id", "created_at"),
        {"schema": "ai"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID] = mapped_column(
        ForeignKey("ontology.ontologies.id", ondelete="CASCADE"),
    )
    user_id: Mapped[UUID]
    message: Mapped[str] = mapped_column(Text)
    # {page, elementId}: where the user was when they asked.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    step: Mapped[str | None] = mapped_column(String(16))
    reply: Mapped[str | None] = mapped_column(Text)
    # Operations the model proposed that failed the checks and were left out.
    dropped: Mapped[int] = mapped_column(server_default="0", default=0)
    change_set_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ontology.change_sets.id", ondelete="SET NULL"),
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
