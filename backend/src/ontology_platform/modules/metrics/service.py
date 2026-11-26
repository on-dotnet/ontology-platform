"""Metric and rule reads against the active release."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import not_implemented
from ontology_platform.modules.metrics.schemas import MetricList, MetricValue, RuleReport
from ontology_platform.modules.query.schemas import KeySet


async def list_metrics(db: AsyncSession, ontology_id: UUID) -> MetricList:
    raise not_implemented("Metric listing")


async def evaluate(
    db: AsyncSession, ontology_id: UUID, metric_id: UUID, *, within: KeySet | None = None
) -> MetricValue:
    raise NotImplementedError


async def check_rules(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    *,
    within: KeySet | None = None,
    limit: int = 50,
) -> RuleReport:
    raise NotImplementedError
