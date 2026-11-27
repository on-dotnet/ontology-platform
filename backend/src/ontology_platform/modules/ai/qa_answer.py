"""Build authoritative facts and project only permitted business values into answer prose."""

import json
import re
from collections.abc import Mapping
from itertools import chain, islice
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.qa_prompts import QA_ANSWER_INSTRUCTIONS, QaAnswerOut
from ontology_platform.modules.ai.qa_run import ROW_LIMIT
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.ontology.qa_context import QaContext
from ontology_platform.modules.query.schemas import PathRow

_VALUE_LIMIT = 200

# Row refs the answer call uses for rows (K1 to K50); readers know objects by their keys.
_REF = re.compile(r"(?<![0-9A-Za-z])K\d+(?![0-9A-Za-z])")
_REF_SEP = r"\s*(?:[、,，;；/~\uff5e\-\u2013\u2014]|和|及|与|至|到)\s*"
_REF_GROUP = re.compile(rf"\s*[（(]\s*K\d+(?:{_REF_SEP}K\d+)*\s*[）)]")
# Saying the objects cannot be listed contradicts the complete list shown with the answer.
_DENIAL = re.compile(
    r"(?:无法|不能|未能|没法|难以)[^。！？!?]{0,8}(?:列出|列举|罗列)"
    r"|(?:未|没有|并未|不)(?:提供|给出|包含|列出)[^。！？!?]{0,12}(?:编号|名单|清单|列表|明细|具体)"
)
_SENTENCE_END = re.compile(r"(?<=[。！？!?；;\n])")


class _Prompt(NamedTuple):
    text: str
    refs: dict[str, str]
    names: dict[str, str]
    # Ref-shaped business words, such as a grade, that the answer may repeat as they are.
    literals: set[str]
    truncated: bool


def _name(row: PathRow) -> str:
    return " / ".join(k.value for k in row.source.key)


def _resolve(text: str, names: Mapping[str, str], literals: set[str]) -> str | None:
    """Name the objects behind row refs; None if the text refers to a row it was not given."""

    def known(ref: str) -> bool:
        return ref in names and ref not in literals

    def group(match: re.Match[str]) -> str:
        return "" if all(known(ref) for ref in _REF.findall(match[0])) else match[0]

    unknown = False

    def bare(match: re.Match[str]) -> str:
        nonlocal unknown
        ref = match[0]
        if ref in literals:
            return ref
        if ref in names:
            return names[ref]
        unknown = True
        return ref

    resolved = _REF.sub(bare, _REF_GROUP.sub(group, text))
    return None if unknown else resolved


def _without_denials(text: str) -> str:
    return "".join(s for s in _SENTENCE_END.split(text) if not _DENIAL.search(s)).strip()


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
            schemas.QaFactObject(type_id=row.type_id, key=row.key, label=_name(row))
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
) -> _Prompt:
    rows = []
    refs: dict[str, str] = {}
    names: dict[str, str] = {}
    words = [question, plan.description]
    answer_refs = {row.key: f"K{i}" for i, row in enumerate(evidence.rows, start=1)}
    truncated = evidence.truncated or len(evidence.rows) + len(evidence.tail) > ROW_LIMIT
    for i, row in enumerate(islice(chain(evidence.rows, evidence.tail), ROW_LIMIT), start=1):
        ref = f"K{i}"
        refs[ref] = row.key
        bound = context.model.type(row.type_id)
        if bound is None:
            raise ValueError("A result row has no type in the checked model.")
        name = _name(row)[:_VALUE_LIMIT]
        names[ref] = name
        words.append(name)
        values = []
        truncated |= bool(row.truncated)
        for prop in bound.properties:
            if prop.property_id in row.values:
                value = row.values[prop.property_id]
                if isinstance(value, str) and len(value) > _VALUE_LIMIT:
                    truncated = True
                    value = value[:_VALUE_LIMIT]
                values.append({"label": prop.label, "value": value})
                if isinstance(value, str):
                    words.append(value)
        parent = answer_refs.get(row.via[plan.target]) if i > len(evidence.rows) else None
        # The key values name the object; the key columns stay out of the prompt (spec 007 5.5).
        rows.append(
            {"ref": ref, "type": bound.label, "name": name, "values": values, "answerRef": parent}
        )
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
    literals = {ref for word in words for ref in _REF.findall(word)}
    return _Prompt(json.dumps(payload, ensure_ascii=False), refs, names, literals, truncated)


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
    prompt = _prompt(question, plan, context, evidence, result.facts)
    refs = prompt.refs
    if prompt.truncated:
        result.notes.append("rows_truncated")
    try:
        output = await gateway.structured(
            purpose="qa.answer",
            model=model,
            instructions=QA_ANSWER_INSTRUCTIONS,
            text=prompt.text,
            schema=QaAnswerOut,
        )
    except AiError as exc:
        if exc.retryable:
            raise
        result.notes.append("answer_unavailable")
        return result
    # The platform, not the prompt alone, keeps row refs and denials of the shown list out.
    listed = bool(result.facts.objects) and result.facts.count == len(result.facts.objects)

    def readable(text: str) -> str | None:
        resolved = _resolve(text, prompt.names, prompt.literals)
        if resolved is not None and listed:
            resolved = _without_denials(resolved)
        return resolved or None

    text = readable(output.answer)
    if text is None:
        result.notes.append("answer_unavailable")
        return result
    result.text = text
    result.counterpoints = [c for c in map(readable, output.counterpoints) if c is not None]
    result.cited_keys = [refs[ref] for ref in output.cited_keys if ref in refs]
    if any(ref not in refs for ref in output.cited_keys):
        result.notes.append("cited_unknown")
    return result
