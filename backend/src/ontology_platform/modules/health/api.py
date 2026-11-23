"""Liveness and readiness endpoints."""

from fastapi import APIRouter

from ontology_platform.db import DbSession
from ontology_platform.errors import AppError, problem_responses
from ontology_platform.modules.health import service
from ontology_platform.modules.health.schemas import HealthStatus

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("")
async def health() -> HealthStatus:
    """Liveness: the process is up. Does not touch the database."""
    return HealthStatus()


@router.get("/ready", responses=problem_responses(503))
async def ready(db: DbSession) -> HealthStatus:
    """Readiness: the database answers."""
    if not await service.database_ready(db):
        raise AppError(503, "health.not_ready", "Database is not reachable.")
    return HealthStatus()
