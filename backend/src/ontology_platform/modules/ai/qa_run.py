"""Execute a checked question plan against one release and collect its evidence."""

from collections.abc import Iterable
from itertools import chain
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import schemas
from ontology_platform.modules.metrics import service as metrics
from ontology_platform.modules.metrics.schemas import RuleReport
from ontology_platform.modules.ontology import releases
from ontology_platform.modules.ontology.bindings import MetricCopy
from ontology_platform.modules.ontology.qa_context import QaContext, qa_documents
from ontology_platform.modules.ontology.rules import display_label
from ontology_platform.modules.query import service as query
from ontology_platform.modules.query.scan import query_budget
from ontology_platform.modules.query.schemas import KeySet, PathQuery, PathRow, StepOut

ROW_LIMIT = 50


def _element_ids(
    plan: schemas.QaPlan, metric: MetricCopy | None, rules: RuleReport | None
) -> set[UUID]:
    ids: set[UUID] = set()
    if plan.start is not None:
        ids.add(plan.start.type_id)
        ids.update(f.property_id for f in plan.start.filters)
    for hop in plan.hops:
        ids.update((hop.relation_id, hop.target_type_id))
        ids.update(f.property_id for f in hop.filters)
    if metric is not None:
        ids.update((metric.id, metric.subject_id))
        definition = metric.metric
        if definition.property_id is not None:
            ids.add(definition.property_id)
        ids.update(f.property_id for f in (*definition.filters, *definition.numerator))
    if rules is not None:
        for result in rules.results:
            ids.add(result.constraint_id)
            if result.property_id is not None:
                ids.add(result.property_id)
    return ids


async def _elements(
    db: AsyncSession,
    context: QaContext,
    plan: schemas.QaPlan,
    metric: MetricCopy | None,
    rules: RuleReport | None,
    rows: Iterable[PathRow],
) -> list[schemas.QaEvidenceElement]:
    needed = _element_ids(plan, metric, rules)
    needed.update(prop for row in rows for prop in row.values)
    documents = await qa_documents(db, context, needed)
    elements = [e for e in context.ontology.elements if e.id in needed]
    if metric is not None:
        # ReleasedMetrics omits the IRI. Read it from the same immutable release.
        _, copies = await releases.metric_elements(
            db, context.model.ontology_id, release_id=context.model.release_id
        )
        elements.extend(m for m in copies if m.id == metric.id)
    return [
        schemas.QaEvidenceElement(
            id=e.id,
            kind=e.kind,
            label=display_label(e.label_zh, e.label_en, e.local_name),
            iri=e.iri,
            documents=[
                schemas.QaDocumentEvidence(
                    document_id=doc.document_id,
                    document_name=doc.document_name,
                    chunk=doc.chunk,
                    quote=doc.quote,
                )
                for doc in documents.get(e.id, [])
            ],
        )
        for e in elements
    ]


async def execute(
    db: AsyncSession, ontology_id: UUID, context: QaContext, plan: schemas.QaPlan
) -> tuple[schemas.QaEvidence, KeySet | None, int | None]:
    keys = None
    total = None
    rows = []
    tail = []
    truncated = False
    steps: list[StepOut] = []
    metric = None
    metric_value = None
    rules = None
    async with query_budget() as budget:
        budget.pin(context.model)
        if plan.start is not None:
            path = PathQuery(
                type_id=plan.start.type_id,
                filters=plan.start.filters,
                hops=list(plan.hops),
                target=plan.target,
            )
            page = None
            if plan.intent in ("objects", "count"):
                page = await query.traverse(db, ontology_id, path, limit=ROW_LIMIT)
                total = page.total
                rows, tail = page.items, page.tail
                truncated = page.truncated or len(tail) < page.tail_total
                steps.extend(page.steps)
            before = budget.statements
            keys = await query.traverse_keys(db, ontology_id, path)
            statements = budget.statements - before
            if page is not None and not path.hops:
                # Both reads are the identical zero-hop filter.
                steps[0].statements += statements
                steps[0].truncated = page.truncated
            else:
                label = plan.hops[plan.target - 1].target_label if plan.target else plan.start.label
                steps.append(
                    StepOut(
                        type_id=keys.type_id,
                        type_label=label,
                        conditions=[f"提取答案对象的全部主键：{plan.description}"],
                        statements=statements,
                        rows=len(keys.keys),
                        truncated=False,
                    )
                )
        if plan.intent == "metric":
            metric = next((m for m in context.metrics.metrics if m.id == plan.metric_id), None)
            if metric is None:
                raise AppError(422, "qa.invalid_plan", "A metric plan needs a released metric.")
            if keys is not None and keys.type_id != metric.subject_id:
                raise AppError(422, "qa.invalid_plan", "The path must select the metric subject.")
            metric_value = await metrics.evaluate(db, ontology_id, metric.id, within=keys)
            steps.extend(metric_value.steps)
        elif plan.intent == "rules":
            if keys is None:
                raise AppError(422, "qa.invalid_plan", "A rule plan needs a target type.")
            rules = await metrics.check_rules(
                db, ontology_id, keys.type_id, within=keys, limit=ROW_LIMIT, language="zh"
            )
            steps.extend(rules.steps)
            truncated = any(len(result.samples) < result.violations for result in rules.results)

        elements = await _elements(db, context, plan, metric, rules, chain(rows, tail))
        type_ids = {e.id for e in elements if e.kind == "entity_type"}
        bindings = [
            schemas.QaEvidenceBinding(
                schema=t.schema, table=t.table, key_columns=list(t.key_columns)
            )
            for t in context.model.types
            if t.type_id in type_ids
        ]
        evidence = schemas.QaEvidence(
            release=context.metrics.release,
            elements=elements,
            bindings=bindings,
            steps=steps,
            rows=rows,
            truncated=truncated,
            tail=tail,
            metric=metric_value,
            rules=rules,
        )
    return evidence, keys, total
