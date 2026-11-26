"""Metric and rule reads against the active release."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.metrics import aggregate
from ontology_platform.modules.metrics.rule_check import check_rules as check_rules
from ontology_platform.modules.metrics.schemas import MetricInfo, MetricList, MetricValue
from ontology_platform.modules.ontology import bindings, rules
from ontology_platform.modules.ontology.schemas import MetricDefinition
from ontology_platform.modules.query.scan import query_budget
from ontology_platform.modules.query.schemas import KeySet


def _bound(definition: MetricDefinition, subject: bindings.BoundType | None) -> bool:
    if subject is None:
        return False
    needed = {f.property_id for f in (*definition.filters, *definition.numerator)}
    if definition.property_id is not None:
        needed.add(definition.property_id)
    return needed.issubset(p.property_id for p in subject.properties)


async def _model(db: AsyncSession, ontology_id: UUID, release_id: UUID) -> bindings.BoundModel:
    model = await bindings.bound_model(db, ontology_id)
    if model is None or model.release_id != release_id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    return model


async def list_metrics(db: AsyncSession, ontology_id: UUID) -> MetricList:
    released = await bindings.released_metrics(db, ontology_id)
    if not released.metrics:
        return MetricList(release=released.release, items=[])
    model = await _model(db, ontology_id, released.release.id)
    subjects = {s.type_id: s for s in model.types}
    labels = {s.type_id: s.label for s in model.types}
    if any(m.subject_id not in labels for m in released.metrics):
        ontology = await bindings.released_ontology(db, ontology_id)
        if ontology is None or ontology.release_id != released.release.id:
            raise AppError(409, "query.release_changed", "The active release has changed.")
        labels.update(
            (e.id, rules.display_label(e.label_zh, e.label_en, e.local_name))
            for e in ontology.elements
            if e.kind == "entity_type"
        )
    return MetricList(
        release=released.release,
        items=[
            MetricInfo(
                metric_id=m.id,
                label=m.label_zh,
                definition=m.definition_zh or m.definition_en,
                unit=m.unit,
                subject_type_id=m.subject_id,
                subject_type_label=labels[m.subject_id],
                aggregate=m.metric.aggregate,
                bound=_bound(m.metric, subjects.get(m.subject_id)),
            )
            for m in released.metrics
        ],
    )


async def evaluate(
    db: AsyncSession, ontology_id: UUID, metric_id: UUID, *, within: KeySet | None = None
) -> MetricValue:
    async with query_budget() as budget:
        released = await bindings.released_metrics(db, ontology_id)
        metric = next((m for m in released.metrics if m.id == metric_id), None)
        if metric is None:
            raise AppError(404, "metric.not_found", "The metric is not in the active release.")
        model = await _model(db, ontology_id, released.release.id)
        budget.pin(model)
        subject = model.type(metric.subject_id)
        if subject is None or not _bound(metric.metric, subject):
            raise AppError(409, "query.type_not_bound", "The metric needs additional bindings.")
        try:
            return await aggregate.evaluate(db, ontology_id, metric, subject, within)
        except AppError as exc:
            if exc.code != "query.too_many_rows":
                raise
            raise AppError(
                422, "metric.too_many_rows", "Too many matching rows. Narrow the filters."
            ) from exc
