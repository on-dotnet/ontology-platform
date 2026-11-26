"""Build authoritative facts and project only permitted business values into answer prose."""

import json
from itertools import chain, islice

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.qa_prompts import QA_ANSWER_INSTRUCTIONS, QaAnswerOut
from ontology_platform.modules.ai.qa_run import ROW_LIMIT
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.ontology.qa_context import QaContext

_VALUE_LIMIT = 200


def _facts(
    plan: schemas.QaPlan, evidence: schemas.QaEvidence, total: int | None
) -> schemas.QaFacts:
    metric = evidence.metric
    fact_metric = None
    if metric is not None:
        display = metric.display
        if display is not None and metric.unit and not display.endswith(metric.unit):
            display = f"{display} {metric.unit}"
        fact_metric = schemas.QaFactMetric(label=metric.label, display=display)
    objects = []
    if plan.intent == "objects":
        objects = [
            schemas.QaFactObject(
                type_id=row.type_id, key=row.key, label=" / ".join(k.value for k in row.source.key)
            )
            for row in evidence.rows
        ]
    return schemas.QaFacts(
        count=total,
        metric=fact_metric,
        objects=objects,
        violations=(
            sum(r.violations for r in evidence.rules.results)
            if evidence.rules is not None
            else None
        ),
    )


async def _samples_allowed(
    db: AsyncSession, context: QaContext, evidence: schemas.QaEvidence
) -> bool:
    # Intermediate types and aggregates can read sources that have no displayed rows.
    sources = {row.source.data_source_id for row in chain(evidence.rows, evidence.tail)}
    for element in evidence.elements:
        if element.kind == "entity_type":
            bound = context.model.type(element.id)
            if bound is None:
                return False
            sources.add(bound.data_source_id)
    for source_id in sources:
        source = await connectors.get_data_source_ref(db, source_id)
        if source is None or source.status != "active" or not source.allow_samples:
            return False
    return bool(sources)


def _prompt(
    question: str,
    plan: schemas.QaPlan,
    context: QaContext,
    evidence: schemas.QaEvidence,
    facts: schemas.QaFacts,
) -> tuple[str, dict[str, str], bool]:
    rows = []
    refs: dict[str, str] = {}
    answer_refs = {row.key: f"K{i}" for i, row in enumerate(evidence.rows, start=1)}
    truncated = evidence.truncated or len(evidence.rows) + len(evidence.tail) > ROW_LIMIT
    for i, row in enumerate(islice(chain(evidence.rows, evidence.tail), ROW_LIMIT), start=1):
        ref = f"K{i}"
        refs[ref] = row.key
        bound = context.model.type(row.type_id)
        if bound is None:
            raise ValueError("A result row has no type in the checked model.")
        values = []
        truncated |= bool(row.truncated)
        for prop in bound.properties:
            if prop.property_id in row.values:
                value = row.values[prop.property_id]
                if isinstance(value, str) and len(value) > _VALUE_LIMIT:
                    truncated = True
                    value = value[:_VALUE_LIMIT]
                values.append({"label": prop.label, "value": value})
        parent = answer_refs.get(row.via[plan.target]) if i > len(evidence.rows) else None
        rows.append({"ref": ref, "type": bound.label, "values": values, "answerRef": parent})
    metric = evidence.metric
    rule_counts = []
    if evidence.rules is not None:
        rule_counts = [
            {"label": rule.constraint_label, "violations": rule.violations}
            for rule in evidence.rules.results
        ]
    payload = {
        "question": question,
        "plan": plan.description,
        "rows": rows,
        "total": facts.count,
        "metric": (
            {
                "label": metric.label,
                "display": metric.display,
                "unit": metric.unit,
                "value": metric.value,
                "population": metric.population,
                "matched": metric.matched,
            }
            if metric is not None
            else None
        ),
        "rules": rule_counts,
        "truncated": truncated,
        "limit": ROW_LIMIT,
    }
    return json.dumps(payload, ensure_ascii=False), refs, truncated


async def answer(
    db: AsyncSession,
    gateway: ModelGateway,
    model: str,
    question: str,
    plan: schemas.QaPlan,
    context: QaContext,
    evidence: schemas.QaEvidence,
    total: int | None,
) -> schemas.QaAnswer:
    result = schemas.QaAnswer(
        text=None, facts=_facts(plan, evidence, total), cited_keys=[], counterpoints=[], notes=[]
    )
    if not await _samples_allowed(db, context, evidence):
        result.notes.append("rows_not_shared")
        if evidence.truncated:
            result.notes.append("rows_truncated")
        return result
    text, refs, truncated = _prompt(question, plan, context, evidence, result.facts)
    if truncated:
        result.notes.append("rows_truncated")
    try:
        output = await gateway.structured(
            purpose="qa.answer",
            model=model,
            instructions=QA_ANSWER_INSTRUCTIONS,
            text=text,
            schema=QaAnswerOut,
        )
    except AiError as exc:
        if exc.retryable:
            raise
        result.notes.append("answer_unavailable")
        return result
    result.text = output.answer
    result.counterpoints = output.counterpoints
    result.cited_keys = [refs[ref] for ref in output.cited_keys if ref in refs]
    if any(ref not in refs for ref in output.cited_keys):
        result.notes.append("cited_unknown")
    return result
