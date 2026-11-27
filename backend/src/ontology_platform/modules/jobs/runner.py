"""Dispatch leased jobs and maintain their heartbeats while handlers run."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.jobs import service
from ontology_platform.modules.jobs.models import Job

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL = 15.0
# compose.yaml must give the worker a longer stop_grace_period than this.
STOP_GRACE = 60.0


class RetryableJobError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class JobLeaseLostError(Exception):
    """A newer execution owns the job."""


# `JobContext.check_lease`, handed to code that commits a job's effects in its own transactions.
type LeaseCheck = Callable[[AsyncSession], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class JobContext:
    id: UUID
    payload: dict[str, Any]
    session_factory: async_sessionmaker[AsyncSession]
    attempts: int = 1
    max_attempts: int = 3
    worker_id: str | None = None

    async def check_lease(self, db: AsyncSession) -> None:
        """Lock the current claim before committing effects from this execution."""
        if self.worker_id is None:
            return
        owned = await db.scalar(
            select(Job.id)
            .where(
                Job.id == self.id,
                Job.status == "running",
                Job.locked_by == self.worker_id,
                Job.attempts == self.attempts,
            )
            .with_for_update()
        )
        if owned is None:
            raise JobLeaseLostError


type Handler = Callable[[JobContext], Awaitable[None]]
_handlers: dict[str, Handler] = {}


def register(kind: str, handler: Handler) -> None:
    _handlers[kind] = handler


async def _wait(event: asyncio.Event, interval: float) -> None:
    with suppress(TimeoutError):
        async with asyncio.timeout(interval):
            await event.wait()


async def _renew(context: JobContext, worker_id: str, finished: asyncio.Event) -> None:
    while not finished.is_set():
        await _wait(finished, HEARTBEAT_INTERVAL)
        if finished.is_set():
            return
        try:
            async with context.session_factory.begin() as db:
                await context.check_lease(db)
                await service.heartbeat(db, context.id, worker_id)
        except JobLeaseLostError:
            raise
        except Exception:
            # A brief database hiccup must not take the worker down; the next beat retries.
            logger.warning("Heartbeat for job %s failed", context.id, exc_info=True)


async def _execute(kind: str, context: JobContext, worker_id: str) -> None:
    finished = asyncio.Event()
    error: Exception | None = None
    async with asyncio.TaskGroup() as tasks:
        tasks.create_task(_renew(context, worker_id, finished))
        try:
            await _handlers[kind](context)
        except JobLeaseLostError:
            raise
        except Exception as exc:
            error = exc
            logger.exception("Job %s (%s) failed", context.id, kind)
        finally:
            finished.set()

    async with context.session_factory.begin() as db:
        await context.check_lease(db)
        if error is None:
            await service.succeed(db, context.id)
        elif isinstance(error, RetryableJobError):
            await service.fail(db, context.id, error.code, str(error), retryable=True)
        else:
            code = getattr(error, "code", None)
            code = code if isinstance(code, str) else "internal.error"
            await service.fail(db, context.id, code, str(error), retryable=False)


async def _run(kind: str, context: JobContext, worker_id: str) -> None:
    try:
        await _execute(kind, context, worker_id)
    except* JobLeaseLostError:
        logger.warning("Job %s was reclaimed", context.id)


async def run_worker(
    session_factory: async_sessionmaker[AsyncSession],
    worker_id: str,
    *,
    poll_interval: float = 2.0,
    stop_event: asyncio.Event | None = None,
    concurrency: int = 1,
    stop_grace: float = STOP_GRACE,
) -> None:
    """Runs up to `concurrency` jobs at once (spec 004, 7.3), each with its own claim, heartbeat
    and lease check. On stop, wait up to `stop_grace` seconds for active jobs, then cancel and
    requeue unfinished claims without spending an attempt.

    An error outside a job's handler (recording its outcome failed) stops the worker as it did
    with one job at a time, once the other jobs in progress have finished.
    """
    stop = stop_event if stop_event is not None else asyncio.Event()
    stop_wait = asyncio.create_task(stop.wait())
    running: dict[asyncio.Task[None], tuple[str, JobContext]] = {}
    failed: list[BaseException] = []

    def finished(task: asyncio.Task[None]) -> None:
        running.pop(task, None)
        error = None if task.cancelled() else task.exception()
        if error is not None:
            # Taking the exception silences asyncio's warning: log every one, raise the first.
            logger.error("Worker %s stops after an error", worker_id, exc_info=error)
            failed.append(error)

    try:
        while not stop.is_set() and not failed:
            if len(running) >= concurrency:
                await asyncio.wait({*running, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
                continue
            work: tuple[str, JobContext] | None = None
            async with session_factory.begin() as db:
                await service.requeue_stale(db)
                job = await service.claim(db, worker_id)
                if job is not None:
                    context = JobContext(
                        job.id,
                        job.payload,
                        session_factory,
                        job.attempts,
                        job.max_attempts,
                        worker_id,
                    )
                    work = job.kind, context
            if work is None:
                await _wait(stop, poll_interval)
                continue
            task = asyncio.create_task(_run(*work, worker_id))
            running[task] = work
            task.add_done_callback(finished)
        if stop.is_set() and running:
            _, pending = await asyncio.wait(running, timeout=stop_grace)
            interrupted = [(task, running[task]) for task in pending if task in running]
            for task, _ in interrupted:
                task.cancel()
            await asyncio.gather(*(task for task, _ in interrupted), return_exceptions=True)
            for _, (kind, context) in interrupted:
                try:
                    async with session_factory.begin() as db:
                        released = await service.release(
                            db, context.id, worker_id, context.attempts
                        )
                    if released:
                        logger.warning("Requeued interrupted job %s (%s)", context.id, kind)
                except Exception:
                    logger.exception("Could not requeue interrupted job %s (%s)", context.id, kind)
    except asyncio.CancelledError:
        for task in running:
            task.cancel()
        raise
    finally:
        stop_wait.cancel()
        await asyncio.gather(stop_wait, return_exceptions=True)
        if running:
            await asyncio.gather(*running, return_exceptions=True)
    if failed:
        raise failed[0]
