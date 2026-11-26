from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ontology_platform.db import Base


class CompetencyQuestionRow(Base):
    __tablename__ = "questions"
    __table_args__ = (
        CheckConstraint("expect_kind IN ('answerable', 'objects', 'number')", name="expect_kind"),
        {"schema": "cq"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    ontology_id: Mapped[UUID]
    text: Mapped[str] = mapped_column(String(500))
    expect_kind: Mapped[str] = mapped_column(String(16))
    expect_objects: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    expect_number: Mapped[Decimal | None] = mapped_column(Numeric)
    tolerance: Mapped[Decimal] = mapped_column(Numeric, server_default="0")
    note: Mapped[str | None] = mapped_column(String(1000))
    position: Mapped[int] = mapped_column(server_default="0")
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revision: Mapped[int] = mapped_column(server_default="1")
    archived_at: Mapped[datetime | None]


class CqCheckRow(Base):
    __tablename__ = "checks"
    __table_args__ = (
        CheckConstraint(
            "result IN ('pending', 'pass', 'fail', 'unanswerable', 'error')", name="result"
        ),
        {"schema": "cq"},
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("cq.questions.id"))
    release_id: Mapped[UUID]
    version: Mapped[int]
    qa_question_id: Mapped[UUID]
    result: Mapped[str] = mapped_column(String(16))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    created_by: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
