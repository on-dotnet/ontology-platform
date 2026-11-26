"""Question answering and its completion callback for competency checks."""

from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError, not_implemented
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.schemas import (
    QaOrigin,
    QaQuestion,
    QaQuestionCreate,
    QaQuestionList,
)
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.jobs.runner import Handler, JobContext

JOB_KIND = "qa.answer"
AskedBy = Literal["me", "all"]


async def create_question(
    db: AsyncSession,
    ontology_id: UUID,
    body: QaQuestionCreate,
    *,
    user_id: UUID,
    origin: QaOrigin = "user",
    cq_question_id: UUID | None = None,
) -> QaQuestion:
    raise NotImplementedError


async def require_visible(db: AsyncSession, question_id: UUID, actor: Principal) -> None:
    statement = select(QaQuestionRow.id).where(QaQuestionRow.id == question_id)
    if actor.role != Role.ADMIN:
        statement = statement.where(QaQuestionRow.asked_by == actor.id)
    if await db.scalar(statement) is None:
        raise AppError(404, "qa.not_found", "Question not found.")


async def get_question(db: AsyncSession, question_id: UUID, *, actor: Principal) -> QaQuestion:
    await require_visible(db, question_id, actor)
    raise not_implemented("Getting a question")


async def list_questions(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    actor: Principal,
    asked_by: AskedBy,
    limit: int,
    cursor: str | None,
) -> QaQuestionList:
    if asked_by == "all" and actor.role != Role.ADMIN:
        raise AppError(403, "auth.forbidden", "Only administrators can list everyone's questions.")
    raise not_implemented("Listing questions")


def make_answerer(
    session_factory: async_sessionmaker[AsyncSession], gateway: ModelGateway, model: str
) -> Handler:
    async def handle(job: JobContext) -> None:
        raise not_implemented("Answering a question")

    return handle


def register_listener(listener: Callable[[AsyncSession, QaQuestion], Awaitable[None]]) -> None:
    raise NotImplementedError
