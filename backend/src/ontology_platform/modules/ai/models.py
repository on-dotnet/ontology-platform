"""Tables of the ai module: one row per model call, for usage accounting and troubleshooting,
and the AI assistant's requests.

Prompts and document text are deliberately not stored. An assistant request keeps the user's
own words and the short reply, so that the panel can show them again (spec 002, section 10).
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base

AssistantStatus = Literal["queued", "running", "succeeded", "failed"]
AssistantStep = Literal["context", "model", "changeset"]
MESSAGE_MAX_LENGTH = 2000
BindingSuggestionStep = Literal["catalog", "match", "columns", "changeset"]


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
    # Rows of other modules are referenced by id without a foreign key, like ai.runs.
    ontology_id: Mapped[UUID]
    user_id: Mapped[UUID]
    message: Mapped[str] = mapped_column(Text)
    # {page, elementId}: where the user was when they asked.
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    step: Mapped[str | None] = mapped_column(String(16))
    reply: Mapped[str | None] = mapped_column(Text)
    # Operations the model proposed that failed the checks and were left out.
    dropped: Mapped[int] = mapped_column(server_default="0", default=0)
    change_set_id: Mapped[UUID | None]
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class BindingSuggestion(Base):
    """One request for AI binding suggestions and what came of it (spec 003, section 8).

    Neither catalog content nor sample values are stored here: what the model was shown lives
    on as the evidence of the change set it led to.
    """

    __tablename__ = "binding_suggestions"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="status"),
        CheckConstraint(
            "step IS NULL OR step IN ('catalog', 'match', 'columns', 'changeset')",
            name="step",
        ),
        CheckConstraint("proposed >= 0 AND dropped >= 0", name="counts"),
        Index(None, "ontology_id", "user_id", "created_at"),
        {"schema": "ai"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    # Rows of other modules are referenced by id without a foreign key, like ai.runs.
    ontology_id: Mapped[UUID]
    data_source_id: Mapped[UUID]
    user_id: Mapped[UUID]
    # {tables: [{schema, name}] | null, schemas: [...] | null, typeIds: [...] | null}
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16))
    step: Mapped[str | None] = mapped_column(String(16))
    change_set_id: Mapped[UUID | None]
    # Suggestions that became change items, and those left out by the checks.
    proposed: Mapped[int] = mapped_column(server_default="0", default=0)
    dropped: Mapped[int] = mapped_column(server_default="0", default=0)
    # Whether sample values were read and sent to the model for this request.
    samples_sent: Mapped[bool] = mapped_column(default=False, server_default=false())
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class QaQuestionRow(Base):
    __tablename__ = "qa_questions"
    __table_args__ = (
        CheckConstraint("char_length(question) BETWEEN 1 AND 500", name="question"),
        CheckConstraint("origin IN ('user', 'cq')", name="origin"),
        CheckConstraint(
            "status IN ('queued', 'running', 'answered', 'unanswerable', 'failed')", name="status"
        ),
        CheckConstraint(
            "step IS NULL OR step IN ('plan', 'check', 'query', 'answer', 'done')", name="step"
        ),
        CheckConstraint(
            "gap_status IS NULL OR gap_status IN ('queued', 'running', 'done', 'empty', 'failed')",
            name="gap_status",
        ),
        CheckConstraint("gap_dropped >= 0", name="gap_dropped"),
        Index(None, "asked_by", "created_at"),
        Index(None, "ontology_id", "created_at"),
        {"schema": "ai"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID]
    question: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(16))
    cq_question_id: Mapped[UUID | None]
    asked_by: Mapped[UUID]
    status: Mapped[str] = mapped_column(String(16))
    step: Mapped[str | None] = mapped_column(String(16))
    release_id: Mapped[UUID | None]
    release_version: Mapped[int | None]
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    gaps: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    answer_keys: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    gap_status: Mapped[str | None] = mapped_column(String(16))
    gap_change_set_id: Mapped[UUID | None]
    gap_dropped: Mapped[int] = mapped_column(default=0, server_default="0")
    gap_error_code: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
