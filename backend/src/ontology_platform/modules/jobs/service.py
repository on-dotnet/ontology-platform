"""Queue operations participate in the caller's transaction."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.jobs.models import Job

STALE_AFTER = timedelta(minutes=2)


async def enqueue(
    db: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    run_after: datetime | None = None,
    max_attempts: int = 3,
) -> UUID:
    job = Job(id=uuid4(), kind=kind, payload=payload, max_attempts=max_attempts)
    if run_after is not None:
        job.run_after = run_after
    db.add(job)
    return job.id


async def claim(db: AsyncSession, worker_id: str) -> Job | None:
    job = await db.scalar(
        select(Job)
        .where(Job.status == "queued", Job.run_after <= func.now())
        .order_by(Job.run_after, Job.created_at, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    if job is not None:
        job.status = "running"
        job.attempts += 1
        job.locked_by = worker_id
        job.locked_at = job.heartbeat_at = datetime.now(UTC)
        await db.flush()
    return job


async def heartbeat(db: AsyncSession, job_id: UUID, worker_id: str) -> bool:
    updated = await db.scalar(
        update(Job)
        .where(Job.id == job_id, Job.status == "running", Job.locked_by == worker_id)
        .values(heartbeat_at=func.now())
        .returning(Job.id)
    )
    return updated is not None


async def succeed(db: AsyncSession, job_id: UUID) -> None:
    await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "running")
        .values(
            status="succeeded",
            locked_by=None,
            locked_at=None,
            heartbeat_at=None,
            error_code=None,
            error_detail=None,
            finished_at=func.now(),
        )
    )


async def fail(
    db: AsyncSession, job_id: UUID, error_code: str, error_detail: str, *, retryable: bool
) -> None:
    job = await db.scalar(
        select(Job)
        .where(Job.id == job_id, Job.status == "running")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        return
    job.error_code = error_code
    job.error_detail = error_detail
    job.locked_by = None
    job.heartbeat_at = job.locked_at = None
    now = datetime.now(UTC)
    if retryable and job.attempts < job.max_attempts:
        job.status = "queued"
        job.run_after = now + timedelta(seconds=30 if job.attempts == 1 else 120)
    else:
        job.status = "failed"
        job.finished_at = now
    await db.flush()


async def requeue_stale(db: AsyncSession, older_than: timedelta = STALE_AFTER) -> int:
    """Queue running jobs whose worker stopped sending heartbeats.

    A recovered job gets one claim beyond `max_attempts`, so that its handler can record why it
    gave up (the documents handler marks the document failed). If that claim dies as well, the
    job fails here instead of cycling forever.
    """
    stale = (Job.status == "running", Job.heartbeat_at < func.now() - older_than)
    released = {"locked_by": None, "locked_at": None, "heartbeat_at": None}
    await db.execute(
        update(Job)
        .where(*stale, Job.attempts > Job.max_attempts)
        .values(status="failed", error_code="jobs.abandoned", finished_at=func.now(), **released)
    )
    recovered = await db.scalars(
        update(Job).where(*stale).values(status="queued", **released).returning(Job.id)
    )
    return len(recovered.all())


async def latest_question_job_is_terminal(db: AsyncSession, kind: str, question_id: UUID) -> bool:
    status = await db.scalar(
        select(Job.status)
        .where(Job.kind == kind, Job.payload["questionId"].as_string() == str(question_id))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    )
    return status in ("succeeded", "failed")
