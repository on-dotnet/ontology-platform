import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.jobs import runner, service
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import (
    JobContext,
    JobLeaseLostError,
    RetryableJobError,
    register,
    run_worker,
)


async def test_claim_skips_locked_job(app: FastAPI, db: AsyncSession) -> None:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    job_id = await service.enqueue(db, "sample", {"n": 1})
    async with factory() as other:
        assert await other.get(Job, job_id) is None
        await other.commit()
        await db.commit()
        job = await service.claim(db, "a")
        assert job is not None
        assert (job.id, job.attempts, job.locked_by, job.status) == (job_id, 1, "a", "running")
        assert job.locked_at is not None
        assert job.heartbeat_at == job.locked_at
        async with asyncio.timeout(2):
            assert await service.claim(other, "b") is None


async def test_heartbeat_and_recovery(db: AsyncSession) -> None:
    await service.enqueue(db, "sample", {})
    job = await service.claim(db, "first")
    assert job is not None
    old = datetime.now(UTC) - timedelta(minutes=5)
    job.heartbeat_at = old
    await service.heartbeat(db, job.id, "second")
    await db.refresh(job)
    assert job.heartbeat_at == old
    await service.heartbeat(db, job.id, "first")
    await db.refresh(job)
    assert job.heartbeat_at is not None
    assert job.heartbeat_at > old
    assert await service.requeue_stale(db) == 0
    job.heartbeat_at = old
    assert await service.requeue_stale(db) == 1
    recovered = await service.claim(db, "second")
    assert recovered is not None
    assert (recovered.id, recovered.attempts, recovered.locked_by) == (job.id, 2, "second")


async def test_recovery_stops_after_one_claim_beyond_the_limit(db: AsyncSession) -> None:
    job_id = await service.enqueue(db, "sample", {}, max_attempts=1)
    old = datetime.now(UTC) - timedelta(minutes=5)
    for attempt, requeued in ((1, 1), (2, 0)):
        claimed = await service.claim(db, "w")
        assert claimed is not None
        assert claimed.attempts == attempt
        claimed.heartbeat_at = old
        assert await service.requeue_stale(db) == requeued
    job = await db.get(Job, job_id, populate_existing=True)
    assert job is not None
    assert (job.status, job.error_code) == ("failed", "jobs.abandoned")
    assert await service.claim(db, "w") is None


async def test_backoff_and_terminal_failure(db: AsyncSession) -> None:
    await service.enqueue(db, "sample", {})
    for attempt, delay in enumerate((30, 120, 0), start=1):
        job = await service.claim(db, "a")
        assert job is not None
        assert job.attempts == attempt
        before = datetime.now(UTC)
        await service.fail(db, job.id, "ai.unavailable", "offline", retryable=True)
        await db.refresh(job)
        assert job.error_code == "ai.unavailable"
        assert job.error_detail == "offline"
        assert job.locked_by is None
        assert job.heartbeat_at is None
        if delay:
            assert job.status == "queued"
            seconds = (job.run_after - before).total_seconds()
            assert delay - 2 <= seconds <= delay + 2
            assert await service.claim(db, "a") is None
            job.run_after = before - timedelta(seconds=2)
        else:
            assert job.status == "failed"
            assert job.finished_at is not None


@pytest.mark.parametrize(
    ("outcome", "status", "code"),
    [
        ("success", "succeeded", None),
        ("retry", "queued", "ai.offline"),
        ("bug", "failed", "internal.error"),
    ],
)
async def test_worker_dispatch(
    app: FastAPI, db: AsyncSession, outcome: str, status: str, code: str | None
) -> None:
    stop = asyncio.Event()
    kind = f"test.{outcome}"
    job_id = await service.enqueue(db, kind, {"message": "test"})
    await db.commit()
    received: list[JobContext] = []

    async def handle(context: JobContext) -> None:
        received.append(context)
        stop.set()
        if outcome == "retry":
            raise RetryableJobError("ai.offline")
        if outcome == "bug":
            raise RuntimeError("unexpected detail")

    register(kind, handle)
    async with asyncio.timeout(5):
        await run_worker(app.state.session_factory, "a", stop_event=stop)
    assert len(received) == 1
    assert received[0].id == job_id
    assert received[0].payload == {"message": "test"}
    job = await db.get(Job, job_id)
    assert job is not None
    assert job.status == status
    assert job.error_code == code
    if outcome == "bug":
        assert job.error_detail == "unexpected detail"


async def test_idle_worker_stops(app: FastAPI) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(app.state.session_factory, "a", stop_event=stop))
    await asyncio.sleep(0)
    stop.set()
    async with asyncio.timeout(1):
        await task


async def test_reclaimed_attempt_cannot_finish(app: FastAPI, db: AsyncSession) -> None:
    job_id = await service.enqueue(db, "sample", {})
    first = await service.claim(db, "a")
    assert first is not None
    lease = JobContext(job_id, first.payload, app.state.session_factory, worker_id="a")
    first.heartbeat_at = datetime.now(UTC) - timedelta(minutes=3)
    assert await service.requeue_stale(db) == 1
    assert await service.claim(db, "a") is not None
    with pytest.raises(JobLeaseLostError):
        await lease.check_lease(db)


async def test_worker_renews_long_running_job(
    app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = asyncio.Event()
    renewed = asyncio.Event()
    job_id = await service.enqueue(db, "test.renew", {})
    await db.commit()
    monkeypatch.setattr(runner, "HEARTBEAT_INTERVAL", 0.01)
    heartbeat = service.heartbeat

    async def observe(session: AsyncSession, claimed_id: UUID, owner: str) -> bool:
        assert claimed_id == job_id
        assert owner == "a"
        updated = await heartbeat(session, claimed_id, owner)
        if updated:
            renewed.set()
        return updated

    async def wait_for_renewal(context: JobContext) -> None:
        await renewed.wait()
        stop.set()

    monkeypatch.setattr(service, "heartbeat", observe)
    register("test.renew", wait_for_renewal)
    async with asyncio.timeout(5):
        await run_worker(app.state.session_factory, "a", stop_event=stop)
    job = await db.get(Job, job_id)
    assert job is not None
    assert job.status == "succeeded"


async def test_claim_order_and_delayed_jobs(db: AsyncSession) -> None:
    past = datetime(2000, 1, 1, tzinfo=UTC)
    early = await service.enqueue(db, "sample", {}, run_after=past)
    tied = await service.enqueue(db, "sample", {}, run_after=past)
    later = await service.enqueue(db, "sample", {}, run_after=past + timedelta(hours=1))
    await service.enqueue(db, "sample", {}, run_after=datetime(2100, 1, 1, tzinfo=UTC))
    first = await db.get(Job, early)
    second = await db.get(Job, tied)
    assert first is not None
    assert second is not None
    first.created_at = past
    second.created_at = past + timedelta(minutes=1)
    for expected in (early, tied, later):
        claimed = await service.claim(db, "a")
        assert claimed is not None
        assert claimed.id == expected
        await service.succeed(db, claimed.id)
    assert await service.claim(db, "a") is None
