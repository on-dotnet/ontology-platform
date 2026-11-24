"""The AI assistant (spec 002, section 10): a user describes a change, the model proposes
operations, deterministic code checks them, and what passes becomes a change set for review.

The assistant never writes the ontology: its only output is a change set with source
`ai_assistant` whose items all wait for review, like every other AI proposal.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.models import AssistantRequest
from ontology_platform.modules.ai.prompts import (
    ASSISTANT_INSTRUCTIONS,
    AssistantOperationOut,
    AssistantOut,
)
from ontology_platform.modules.jobs import service as jobs
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem

JOB_KIND = "assistant.propose"
PURPOSE = "assistant"
RATIONALE_MAX_LENGTH = 2000
REPLY_MAX_LENGTH = 4000
# A request is one change in the user's words; more operations than this are not one change.
OPERATIONS_MAX = 50
_PLAIN_FIELDS = (
    "label_zh",
    "label_en",
    "local_name",
    "definition_zh",
    "definition_en",
    "datatype",
    "unit",
    "required",
    "multiple",
    "turtle",
)
_REF_FIELDS = (
    ("parent_ref", "parent"),
    ("domain_ref", "domain"),
    ("range_ref", "range"),
    ("inverse_ref", "inverse"),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> AppError:
    return AppError(404, "assistant.not_found", "Assistant request not found.")


def _out(row: AssistantRequest) -> schemas.AssistantRequest:
    return schemas.AssistantRequest(
        id=row.id,
        ontology_id=row.ontology_id,
        message=row.message,
        context=schemas.AssistantContext.model_validate(row.context),
        status=cast(Any, row.status),
        step=cast(Any, row.step),
        reply=row.reply,
        dropped=row.dropped,
        change_set_id=row.change_set_id,
        error_code=row.error_code,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


async def create_request(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.AssistantRequestCreate,
    *,
    user_id: UUID,
) -> schemas.AssistantRequest:
    """Store the request and queue the job that answers it."""
    if await ontology.get_ontology(db, ontology_id) is None:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    row = AssistantRequest(
        id=uuid4(),
        ontology_id=ontology_id,
        user_id=user_id,
        message=body.message,
        context=body.context.model_dump(mode="json", by_alias=True),
        status="queued",
        dropped=0,
        created_at=_now(),
    )
    db.add(row)
    await db.flush()
    await jobs.enqueue(db, JOB_KIND, {"requestId": str(row.id)})
    await db.commit()
    return _out(row)


async def get_request(
    db: AsyncSession,
    request_id: UUID,
    *,
    user_id: UUID,
) -> schemas.AssistantRequest:
    """A request of the user's own; others' are as good as missing."""
    row = await db.get(AssistantRequest, request_id)
    if row is None or row.user_id != user_id:
        raise _not_found()
    return _out(row)


async def list_requests(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    user_id: UUID,
    limit: int,
) -> list[schemas.AssistantRequest]:
    """The user's latest requests about the ontology, newest first."""
    statement = (
        select(AssistantRequest)
        .where(AssistantRequest.ontology_id == ontology_id, AssistantRequest.user_id == user_id)
        .order_by(AssistantRequest.created_at.desc(), AssistantRequest.id.desc())
        .limit(limit)
    )
    return [_out(row) for row in await db.scalars(statement)]


def _id(value: str | None) -> UUID | None:
    try:
        return UUID(value.strip()) if value else None
    except ValueError:
        return None


def to_item(operation: AssistantOperationOut) -> ProposedItem | None:
    """The model's operation as a change item; None when its fields do not even validate."""
    given = operation.fields
    fields: dict[str, Any] = {}
    if operation.op != "delete":
        for name in _PLAIN_FIELDS:
            value = getattr(given, name)
            if value is not None:
                fields[name] = value
        synonyms = [{"lang": "zh", "text": text} for text in given.synonyms_zh or []]
        synonyms += [{"lang": "en", "text": text} for text in given.synonyms_en or []]
        if synonyms:
            fields["synonyms"] = synonyms
        for key, name in _REF_FIELDS:
            ref = getattr(given, name)
            if ref is not None:
                ref = ref.strip()
                fields[key] = None if ref.lower() == "none" else ref
    creates = operation.op == "create"
    try:
        return ProposedItem(
            op=operation.op,
            kind=operation.kind,
            target_element_id=None if creates else _id(operation.target),
            temp_ref=((operation.temp_ref or "").strip() or None) if creates else None,
            proposed=ElementFields.model_validate(fields),
            confidence=min(max(operation.confidence, 0.0), 1.0),
            rationale=operation.rationale[:RATIONALE_MAX_LENGTH] or None,
        )
    except ValidationError:
        return None


async def _set(
    session_factory: async_sessionmaker[AsyncSession],
    job: JobContext,
    request_id: UUID,
    **values: Any,
) -> None:
    async with session_factory.begin() as db:
        await job.check_lease(db)
        row = await db.get(AssistantRequest, request_id, with_for_update=True)
        if row is not None:
            for name, value in values.items():
                setattr(row, name, value)


def make_assistant(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    model: str,
) -> Callable[[JobContext], Awaitable[None]]:
    """The handler of `assistant.propose` jobs."""

    async def handle(job: JobContext) -> None:
        request_id = UUID(job.payload["requestId"])
        async with session_factory.begin() as db:
            await job.check_lease(db)
            row = await db.get(AssistantRequest, request_id, with_for_update=True)
            if row is None or row.status in ("succeeded", "failed"):
                return  # a replayed job: the request has its answer
            # Only reachable through stale-lease recovery: earlier runs died without reporting
            # (worker killed). Stop instead of asking the model once more.
            interrupted = job.attempts > job.max_attempts
            if interrupted:
                row.status, row.error_code, row.finished_at = "failed", "internal.error", _now()
            else:
                row.status, row.step = "running", "context"
            ontology_id, user_id, message = row.ontology_id, row.user_id, row.message
            context = schemas.AssistantContext.model_validate(row.context)
        if interrupted:
            raise AppError(500, "internal.error", "The assistant was interrupted too often.")
        try:
            async with session_factory() as db:
                text = await ontology_assistant.context_for(
                    db,
                    ontology_id,
                    message=message,
                    page=context.page,
                    element_id=context.element_id,
                )
            await _set(session_factory, job, request_id, step="model")
            output = await gateway.structured(
                purpose=PURPOSE,
                model=model,
                instructions=ASSISTANT_INSTRUCTIONS,
                text=f"{text}\n\nThe user's request:\n{message}",
                schema=AssistantOut,
            )
            # Operations past the cap are dropped like those that fail the checks.
            items = [to_item(operation) for operation in output.operations[:OPERATIONS_MAX]]
            valid = [item for item in items if item is not None]
            async with session_factory.begin() as db:
                await job.check_lease(db)
                row = await db.get(AssistantRequest, request_id, with_for_update=True)
                if row is None:
                    return
                row.step = "changeset"
                proposal = await ontology_assistant.propose(
                    db,
                    ontology_id,
                    message=message,
                    created_by=user_id,
                    items=valid,
                )
                row.status = "succeeded"
                row.reply = output.reply.strip()[:REPLY_MAX_LENGTH] or None
                row.dropped = proposal.dropped + len(output.operations) - len(valid)
                row.change_set_id = proposal.change_set_id
                row.finished_at = _now()
        except AiError as exc:
            if exc.retryable and job.attempts < job.max_attempts:
                await _set(session_factory, job, request_id, status="queued")
                raise RetryableJobError(exc.code) from exc
            await _fail(session_factory, job, request_id, exc.code)
            raise AppError(422, exc.code, str(exc)) from exc
        except Exception as exc:
            code = exc.code if isinstance(exc, AppError) else "internal.error"
            await _fail(session_factory, job, request_id, code)
            raise

    return handle


async def _fail(
    session_factory: async_sessionmaker[AsyncSession],
    job: JobContext,
    request_id: UUID,
    code: str,
) -> None:
    await _set(
        session_factory,
        job,
        request_id,
        status="failed",
        error_code=code[:64],
        finished_at=_now(),
    )
