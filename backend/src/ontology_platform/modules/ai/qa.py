"""Question answering and its completion callback for competency checks."""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import defer

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa_answer, qa_plan, qa_prompts, qa_run, schemas
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.schemas import QaGaps, QaOrigin, QaQuestion, QaQuestionCreate
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal, display_names
from ontology_platform.modules.jobs import service as jobs
from ontology_platform.modules.jobs.runner import (
    Handler,
    JobContext,
    JobLeaseLostError,
    RetryableJobError,
)
from ontology_platform.modules.ontology.qa_context import active_release_id, qa_context
from ontology_platform.modules.query import service as query
from ontology_platform.modules.query.errors import invalid_cursor
from ontology_platform.modules.query.schemas import KeySet
from ontology_platform.settings import Settings

JOB_KIND = "qa.answer"
AskedBy = Literal["me", "all"]
type Listener = Callable[[AsyncSession, QaQuestion], Awaitable[None]]
_listeners: list[Listener] = []
_TERMINAL = {"answered", "unanswerable", "failed"}
logger = logging.getLogger(__name__)


def _question(row: QaQuestionRow, names: Mapping[UUID, str], *, detail: bool = True) -> QaQuestion:
    keys = row.answer_keys if detail else None
    return QaQuestion.model_validate(
        {
            "id": row.id,
            "ontology_id": row.ontology_id,
            "question": row.question,
            "origin": row.origin,
            "cq_question_id": row.cq_question_id,
            "asked_by": {"id": row.asked_by, "display_name": names.get(row.asked_by, "")},
            "status": row.status,
            "step": row.step,
            "release": {"id": row.release_id, "version": row.release_version}
            if row.release_id
            else None,
            "plan": row.plan,
            "gaps": row.gaps,
            "answer": row.answer,
            "evidence": row.evidence if detail else None,
            "answer_keys": KeySet(UUID(keys["typeId"]), tuple(keys["keys"])) if keys else None,
            "gap_proposal": {
                "status": row.gap_status,
                "change_set_id": row.gap_change_set_id,
                "dropped": row.gap_dropped,
                "error_code": row.gap_error_code,
            }
            if row.gap_status
            else None,
            "error_code": row.error_code,
            "created_at": row.created_at,
            "finished_at": row.finished_at,
        }
    )


async def _check_limits(db: AsyncSession, user_id: UUID, settings: Settings) -> None:
    # Every API process must serialize the count and enqueue for the same asker.
    lock_id = int.from_bytes(user_id.bytes[:8], signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(lock_id)))
    now = datetime.now(UTC)
    hour = timedelta(hours=1)
    recent = QaQuestionRow.created_at > now - hour
    pending = QaQuestionRow.status.in_(("queued", "running"))
    hourly, running, oldest = (
        await db.execute(
            select(
                func.count().filter(recent),
                func.count().filter(pending),
                func.min(QaQuestionRow.created_at).filter(recent),
            ).where(
                QaQuestionRow.asked_by == user_id,
                QaQuestionRow.origin == "user",
                or_(recent, pending),
            )
        )
    ).one()
    retry_after = 0
    if hourly >= settings.qa_questions_per_hour:
        retry_after = max(1, ceil((oldest + hour - now).total_seconds()))
    if running >= settings.qa_running_max:
        # Completion times are unknown; let the client recheck an occupied slot.
        retry_after = max(15, retry_after)
    if retry_after:
        raise AppError(
            429, "qa.rate_limited", "Too many questions.", headers={"Retry-After": str(retry_after)}
        )


async def create_question(
    db: AsyncSession,
    ontology_id: UUID,
    body: QaQuestionCreate,
    *,
    user_id: UUID,
    origin: QaOrigin = "user",
    cq_question_id: UUID | None = None,
) -> QaQuestion:
    await active_release_id(db, ontology_id)
    settings: Settings = db.info.get("qa_settings") or Settings()
    if not settings.ai_configured:
        raise AppError(409, "ai.not_configured", "No model is configured.")
    if origin == "user":
        await _check_limits(db, user_id, settings)
    row = QaQuestionRow(
        id=uuid4(),
        ontology_id=ontology_id,
        question=body.question,
        origin=origin,
        cq_question_id=cq_question_id,
        asked_by=user_id,
        status="queued",
        created_at=datetime.now(UTC),
    )
    db.add(row)
    await jobs.enqueue(db, JOB_KIND, {"questionId": str(row.id)})
    names = await display_names(db, [user_id])
    await db.commit()
    return _question(row, names)


async def require_visible(db: AsyncSession, question_id: UUID, actor: Principal) -> None:
    statement = select(QaQuestionRow.id).where(QaQuestionRow.id == question_id)
    if actor.role != Role.ADMIN:
        statement = statement.where(QaQuestionRow.asked_by == actor.id)
    if await db.scalar(statement) is None:
        raise AppError(404, "qa.not_found", "Question not found.")


async def get_question(db: AsyncSession, question_id: UUID, *, actor: Principal) -> QaQuestion:
    await require_visible(db, question_id, actor)
    row = await db.get(QaQuestionRow, question_id, populate_existing=True)
    if row is None:
        raise AppError(404, "qa.not_found", "Question not found.")
    return _question(row, await display_names(db, [row.asked_by]))


async def list_questions(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    actor: Principal,
    asked_by: AskedBy,
    limit: int,
    cursor: str | None,
) -> schemas.QaQuestionList:
    if asked_by == "all" and actor.role != Role.ADMIN:
        raise AppError(403, "auth.forbidden", "Only administrators can list everyone's questions.")
    statement = select(QaQuestionRow).where(QaQuestionRow.ontology_id == ontology_id)
    if asked_by == "me":
        statement = statement.where(QaQuestionRow.asked_by == actor.id)
    if cursor is not None:
        try:
            boundary_id = UUID(cursor)
        except ValueError:
            raise invalid_cursor() from None
        position = statement.with_only_columns(QaQuestionRow.created_at)
        boundary = await db.scalar(position.where(QaQuestionRow.id == boundary_id))
        if boundary is None:
            raise invalid_cursor()
        statement = statement.where(
            tuple_(QaQuestionRow.created_at, QaQuestionRow.id) < tuple_(boundary, boundary_id)
        )
    statement = (
        statement.options(defer(QaQuestionRow.evidence), defer(QaQuestionRow.answer_keys))
        .order_by(QaQuestionRow.created_at.desc(), QaQuestionRow.id.desc())
        .limit(limit + 1)
    )
    rows = (await db.scalars(statement)).all()
    page = rows[:limit]
    names = await display_names(db, {row.asked_by for row in page})
    return schemas.QaQuestionList(
        items=[_question(row, names, detail=False) for row in page],
        next_cursor=str(page[-1].id) if len(rows) > limit else None,
    )


def register_listener(listener: Callable[[AsyncSession, QaQuestion], Awaitable[None]]) -> None:
    if listener not in _listeners:
        _listeners.append(listener)


async def _save(db: AsyncSession, job: JobContext, row: QaQuestionRow, **values: Any) -> None:
    await job.check_lease(db)
    for name, value in values.items():
        setattr(row, name, value)
    if row.status in _TERMINAL:
        row.step = "done"
        row.finished_at = datetime.now(UTC)
        await db.flush()
        if _listeners:
            result = _question(row, await display_names(db, [row.asked_by]))
            for listener in tuple(_listeners):
                try:
                    # A listener's failed SQL must roll back only its own changes.
                    async with db.begin_nested():
                        await listener(db, result.model_copy(deep=True))
                except Exception:
                    logger.exception("Question completion listener failed for %s", row.id)
    await db.commit()


async def _answer_question(
    db: AsyncSession, job: JobContext, row: QaQuestionRow, gateway: ModelGateway, model: str
) -> dict[str, Any]:
    context = await qa_context(db, row.ontology_id)
    release = context.metrics.release
    if row.release_id is not None and row.release_id != release.id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    await _save(db, job, row, release_id=release.id, release_version=release.version)
    output = await gateway.structured(
        purpose="qa.plan",
        model=model,
        instructions=qa_prompts.QA_PLAN_INSTRUCTIONS,
        text=json.dumps(
            {"question": row.question, "context": json.loads(context.text)}, ensure_ascii=False
        ),
        schema=qa_prompts.QaPlanOut,
    )
    await _save(db, job, row, step="check")
    types = await query.list_types(db, row.ontology_id)
    if types.release.id != release.id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    plan = qa_plan.check_plan(output, context, context.model, types)
    if isinstance(plan, QaGaps):
        return {"status": "unanswerable", "gaps": plan.model_dump(mode="json", by_alias=True)}
    await _save(db, job, row, step="query", plan=plan.model_dump(mode="json", by_alias=True))
    evidence, keys, total = await qa_run.execute(db, row.ontology_id, context, plan)
    await _save(db, job, row, step="answer")
    answer = await qa_answer.answer(
        db, gateway, model, row.question, plan, context, evidence, total
    )
    if await active_release_id(db, row.ontology_id) != release.id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    return {
        "status": "answered",
        "evidence": evidence.model_dump(mode="json", by_alias=True),
        "answer": answer.model_dump(mode="json", by_alias=True),
        "answer_keys": {"typeId": str(keys.type_id), "keys": list(keys.keys)} if keys else None,
    }


def make_answerer(
    session_factory: async_sessionmaker[AsyncSession], gateway: ModelGateway, model: str
) -> Handler:
    async def handle(job: JobContext) -> None:
        question_id = UUID(job.payload["questionId"])
        async with session_factory() as db:
            await job.check_lease(db)
            row = await db.get(QaQuestionRow, question_id, with_for_update=True)
            if row is None or row.status in _TERMINAL:
                return
            if job.attempts > job.max_attempts:
                await _save(db, job, row, status="failed", error_code="internal.error")
                return
            try:
                async with asyncio.timeout(Settings().qa_job_timeout_seconds):
                    await _save(db, job, row, status="running", step="plan", plan=None)
                    result = await _answer_question(db, job, row, gateway, model)
            except JobLeaseLostError:
                raise
            except TimeoutError:
                result = {"status": "failed", "error_code": "qa.timeout"}
            except (AppError, AiError) as exc:
                retryable = (
                    exc.retryable
                    if isinstance(exc, AiError)
                    else exc.code in ("query.busy", "query.source_unavailable")
                )
                if retryable:
                    await db.rollback()
                    if job.attempts < job.max_attempts:
                        await _save(db, job, row, status="queued", step=None)
                    else:
                        await db.refresh(row)
                        await _save(db, job, row, status="failed", error_code=exc.code)
                    raise RetryableJobError(exc.code) from exc
                result = {"status": "failed", "error_code": exc.code}
            except Exception:
                await db.rollback()
                await db.refresh(row)
                await _save(db, job, row, status="failed", error_code="internal.error")
                raise
            if result["status"] == "failed":
                await db.rollback()
                await db.refresh(row)
            await _save(db, job, row, **result)

    return handle
