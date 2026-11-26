"""Read metrics and rule results from the active release."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.identity.api import require_scope
from ontology_platform.modules.metrics import schemas, service
from ontology_platform.modules.query.service import serve_read

router = APIRouter(
    prefix="/api/ontologies/{id}",
    tags=["metrics"],
    dependencies=[Depends(require_scope("objects:read"))],
)
_ERRORS = problem_responses(401, 403, 404, 409, 422, 501, 502, 503, 504)


@router.get("/metrics", responses=_ERRORS)
async def list_metrics(id: UUID, db: DbSession) -> schemas.MetricList:
    return await service.list_metrics(db, id)


@router.post("/metrics/{metricId}/evaluate", responses=_ERRORS)
async def evaluate_metric(
    id: UUID,
    metricId: UUID,  # noqa: N803
    body: schemas.MetricEvaluate,
    request: Request,
    db: DbSession,
) -> schemas.MetricValue:
    within = body.within.to_key_set() if body.within is not None else None
    return await serve_read(
        request, "Metric evaluation", service.evaluate(db, id, metricId, within=within)
    )


@router.post("/rules/check", responses=_ERRORS)
async def check_rules(
    id: UUID, body: schemas.RuleCheckRequest, request: Request, db: DbSession
) -> schemas.RuleReport:
    within = body.within.to_key_set() if body.within is not None else None
    return await serve_read(
        request,
        "Rule check",
        service.check_rules(db, id, body.type_id, within=within, limit=body.limit),
    )
