"""Change-set proposals for gaps identified in a question."""

from itertools import islice
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa
from ontology_platform.modules.ai.assistant import OPERATIONS_MAX, to_item
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.prompts import AssistantOut
from ontology_platform.modules.ai.qa_prompts import QA_GAP_INSTRUCTIONS
from ontology_platform.modules.ai.schemas import QaGaps, QaQuestion
from ontology_platform.modules.jobs import service as jobs
from ontology_platform.modules.jobs.runner import (
    Handler,
    JobContext,
    JobLeaseLostError,
    RetryableJobError,
)
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.settings import Settings

JOB_KIND = "qa.gap"
_KINDS = {
    "entity_type": "对象类型",
    "relation_type": "关系类型",
    "property": "属性",
    "metric": "指标",
}


async def enqueue_gap_proposal(
    db: AsyncSession, question_id: UUID, *, user_id: UUID, settings: Settings
) -> tuple[QaQuestion, bool]:
    """Return the question and whether this transaction enqueued its proposal."""
    row = await db.get(QaQuestionRow, question_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise AppError(404, "qa.not_found", "Question not found.")
    if row.status != "unanswerable" or not (row.gaps or {}).get("elements"):
        raise AppError(409, "qa.not_unanswerable", "The question has no missing semantic elements.")
    created = row.gap_status is None
    if row.gap_status in ("queued", "running"):
        created = await jobs.latest_question_job_is_terminal(db, JOB_KIND, question_id)
    if created:
        if not settings.ai_configured:
            raise AppError(409, "ai.not_configured", "No model is configured.")
        row.gap_status = "queued"
        await jobs.enqueue(db, JOB_KIND, {"questionId": str(question_id), "userId": str(user_id)})
    question = await qa.question_detail(db, row)
    await db.commit()
    return question, created


def _message(question: str, gaps: QaGaps) -> str:
    lines = [question, "", "缺少的语义元素："]
    for element in gaps.elements:
        line = f"- {element.label_zh}（{_KINDS[element.kind]}）：{element.description}"
        if element.near:
            line += " 相近元素：" + "、".join(ref.label for ref in element.near)
        lines.append(line)
    return "\n".join(lines)


async def _gap_context(db: AsyncSession, ontology_id: UUID, message: str) -> str:
    context = await ontology_assistant.context_for(
        db, ontology_id, message=message, page="explore", element_id=None
    )
    bindings = await ontology_service.list_elements(db, ontology_id, kind="type_binding", q=None)
    bound_types = {str(binding.subject_id) for binding in bindings if binding.subject_id}
    # Annotate only the types already in the summary, including when context_for truncates it.
    lines = []
    for line in context.splitlines():
        ref, _, fields = line.partition(" | ")
        if ref in bound_types and fields.startswith("entity_type | "):
            line += " primary_key_bound=yes"
        lines.append(line)
    return "\n".join(lines)


async def _lock_pending(
    db: AsyncSession, job: JobContext, question_id: UUID
) -> QaQuestionRow | None:
    await job.check_lease(db)
    row = await db.get(QaQuestionRow, question_id, with_for_update=True)
    return row if row is not None and row.gap_status in ("queued", "running") else None


def make_gap_proposer(
    session_factory: async_sessionmaker[AsyncSession], gateway: ModelGateway, model: str
) -> Handler:
    async def handle(job: JobContext) -> None:
        question_id = UUID(job.payload["questionId"])
        try:
            async with session_factory.begin() as db:
                row = await _lock_pending(db, job, question_id)
                if row is None:
                    return
                if job.attempts > job.max_attempts:
                    raise AppError(500, "internal.error", "The gap proposal was interrupted.")
                row.gap_status = "running"
                question, ontology_id = row.question, row.ontology_id
                message = _message(question, QaGaps.model_validate(row.gaps))
            async with session_factory() as db:
                context = await _gap_context(db, ontology_id, message)
            output = await gateway.structured(
                purpose=JOB_KIND,
                model=model,
                instructions=QA_GAP_INSTRUCTIONS,
                text=f"{context}\n\n{message}",
                schema=AssistantOut,
            )
            allowed = (
                op
                for op in output.operations
                if op.op == "create" and op.kind in ("entity_type", "relation_type", "property")
            )
            items = []
            for op in islice(allowed, OPERATIONS_MAX):
                item = to_item(op)
                if item is not None:
                    items.append(item)
            async with session_factory.begin() as db:
                # A duplicate delivery may have finished while this model call was in flight.
                row = await _lock_pending(db, job, question_id)
                if row is None:
                    return
                proposal = await ontology_assistant.propose(
                    db,
                    ontology_id,
                    message=message,
                    created_by=UUID(job.payload["userId"]),
                    items=items,
                    source="ai_qa",
                    title=f"问答缺口：{question[:40]}",
                )
                row.gap_change_set_id = proposal.change_set_id
                row.gap_status = "done" if proposal.change_set_id is not None else "empty"
                row.gap_dropped = len(output.operations) - len(items) + proposal.dropped
        except JobLeaseLostError:
            raise
        except Exception as exc:
            retry = isinstance(exc, AiError) and exc.retryable and job.attempts < job.max_attempts
            code = exc.code if isinstance(exc, (AiError, AppError)) else "internal.error"
            async with session_factory.begin() as db:
                row = await _lock_pending(db, job, question_id)
                if row is None:
                    return
                row.gap_status = "queued" if retry else "failed"
                row.gap_error_code = None if retry else code
            if retry:
                raise RetryableJobError(code) from exc
            if isinstance(exc, AiError):
                raise AppError(422, code, str(exc)) from exc
            raise

    return handle
