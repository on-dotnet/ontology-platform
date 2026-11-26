"""Validate a model plan against the exact vocabulary and bindings selected for its question."""

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.qa_prompts import (
    MissingKind,
    PlanFilterOut,
    PlanHopOut,
    QaPlanOut,
)
from ontology_platform.modules.ai.schemas import (
    QaElementRef,
    QaGaps,
    QaMissingElement,
    QaPlan,
    QaPlanHop,
    QaPlanStart,
    QaTypeRef,
)
from ontology_platform.modules.ontology.bindings import BoundModel
from ontology_platform.modules.ontology.qa_context import QaContext, metric_is_bound
from ontology_platform.modules.ontology.schemas import ElementCopy
from ontology_platform.modules.query.schemas import (
    FILTERS_MAX,
    IN_VALUES_MAX,
    QA_HOPS_MAX,
    Filter,
    FilterValue,
    ObjectTypeList,
)

_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")
_CLOCK = r"(?:[01][0-9]|2[0-3])(?::?[0-5][0-9](?::?[0-5][0-9](?:[.,][0-9]{1,6}0*)?)?)?"
_TIMESTAMP = re.compile(rf"[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}[T ]{_CLOCK}(?:Z|[+-]{_CLOCK})?")
_OPERATORS = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
    "contains": "包含",
    "startsWith": "开头为",
    "in": "属于",
    "isNull": "为空",
    "notNull": "非空",
}


def _invalid() -> AppError:
    return AppError(422, "qa.invalid_plan", "The proposed question plan is invalid.")


def _references(out: QaPlanOut) -> Iterator[tuple[str, MissingKind]]:
    if out.start is not None:
        yield out.start, "entity_type"
    if out.metric is not None:
        yield out.metric, "metric"
    for item in out.filters:
        yield item.property, "property"
    for hop in out.path:
        yield hop.relation, "relation_type"
        for item in hop.filters:
            yield item.property, "property"


def _scalar(value: str, datatype: str | None) -> FilterValue:
    try:
        if datatype == "string" and not re.search(r"[\x00\ud800-\udfff]", value):
            return value
        if datatype == "integer" and re.fullmatch(r"[+-]?[0-9]+", value):
            return int(value)
        if datatype == "boolean" and value.lower() in ("true", "false"):
            return value.lower() == "true"
        if datatype == "decimal" and _DECIMAL.fullmatch(value):
            # Filters carry exact decimal and temporal values on the JSON wire as strings.
            return str(Decimal(value))
        if datatype == "date" and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            return date.fromisoformat(value).isoformat()
        if datatype == "dateTime" and _TIMESTAMP.fullmatch(value):
            return datetime.fromisoformat(value).isoformat()
    except (ValueError, InvalidOperation):
        raise _invalid() from None
    raise _invalid()


def _operand(item: PlanFilterOut, prop: ElementCopy) -> FilterValue | list[FilterValue] | None:
    if item.op in ("isNull", "notNull"):
        if item.value is None and item.values is None:
            return None
    elif item.op == "in":
        if item.value is None and item.values is not None and len(item.values) <= IN_VALUES_MAX:
            return [_scalar(v, prop.datatype) for v in item.values]
    elif item.value is not None and item.values is None:
        return _scalar(item.value, prop.datatype)
    raise _invalid()


class _Check:
    def __init__(self, context: QaContext, model: BoundModel, types: ObjectTypeList) -> None:
        self.refs = context.refs
        self.model = model
        self.elements = {e.id: e for e in context.ontology.elements}
        self.metrics = {m.id: m for m in context.metrics.metrics}
        self.labels = {
            e.id: e.label_zh or e.label_en or e.local_name or "" for e in self.elements.values()
        }
        self.labels.update({m.id: m.label_zh for m in self.metrics.values()})
        self.ops = {(t.type_id, p.property_id): p.ops for t in types.items for p in t.properties}
        self.missing_bindings: dict[UUID, QaTypeRef] = {}

    def reference_gaps(self, out: QaPlanOut) -> QaGaps | None:
        elements = [
            QaMissingElement(
                kind=m.kind,
                label_zh=m.label_zh,
                description=m.description,
                near=[
                    QaElementRef(id=self.refs[r], label=self.labels[self.refs[r]])
                    for r in dict.fromkeys(m.near)
                    if r in self.refs
                ],
            )
            for m in out.missing
        ]
        refs = list(dict.fromkeys(_references(out)))
        unknown = [(r, kind) for r, kind in refs if r not in self.refs]
        unknown_near = any(r not in self.refs for m in out.missing for r in m.near)
        if unknown or unknown_near or out.intent == "unanswerable":
            for r, kind in unknown:
                if any(m.kind == kind for m in out.missing):
                    continue
                description = next((a for a in out.assumptions if a.strip()), r)
                elements.append(
                    QaMissingElement(
                        kind=kind, label_zh=description, description=description, near=[]
                    )
                )
            if not elements:
                raise _invalid()
            return QaGaps(elements=elements, bindings=[])
        for r, kind in refs:
            id_ = self.refs[r]
            if kind == "metric":
                if id_ not in self.metrics:
                    raise _invalid()
            elif id_ not in self.elements or self.elements[id_].kind != kind:
                raise _invalid()
        return None

    def missing(self, type_id: UUID) -> None:
        self.missing_bindings[type_id] = QaTypeRef(type_id=type_id, label=self.labels[type_id])

    def filters(self, type_id: UUID, items: list[PlanFilterOut]) -> list[Filter]:
        bound = self.model.type(type_id)
        if bound is None:
            self.missing(type_id)
        properties = {p.property_id for p in bound.properties} if bound else set()
        result = []
        for item in items:
            prop = self.elements[self.refs[item.property]]
            if prop.domain_id is not None and prop.domain_id != type_id:
                raise _invalid()
            value = _operand(item, prop)
            if prop.id not in properties:
                self.missing(type_id)
            elif item.op not in self.ops.get((type_id, prop.id), []):
                raise _invalid()
            result.append(Filter(property_id=prop.id, op=item.op, value=value))
        return result

    def destination(self, origin: UUID, hop: PlanHopOut) -> UUID | None:
        relation = self.elements[self.refs[hop.relation]]
        exact, aliases = [], []
        for binding in self.model.relations:
            source, target = binding.source_type_id, binding.target_type_id
            if hop.direction == "in":
                source, target = target, source
            if binding.relation_id == relation.id and source == origin:
                exact.append(target)
            if binding.inverse_id == relation.id and target == origin:
                aliases.append(source)
        # The public bindings include inverses and subtype endpoints. Query prefers exact matches.
        matches = exact or aliases
        if len(matches) > 1:
            raise AppError(409, "query.source_mismatch", "The relation has ambiguous bindings.")
        if matches:
            return matches[0]
        source_id, target_id = relation.domain_id, relation.range_id
        if hop.direction == "in":
            source_id, target_id = target_id, source_id
        ancestor: UUID | None = origin
        seen: set[UUID] = set()
        while ancestor is not None and ancestor != source_id and ancestor not in seen:
            seen.add(ancestor)
            ancestor = self.elements[ancestor].parent_id
        if source_id is not None and ancestor != source_id:
            raise _invalid()
        self.missing(relation.domain_id or origin)
        return target_id

    def describe_filters(self, filters: list[Filter]) -> str:
        conditions = []
        for f in filters:
            value = f.value
            values = value if isinstance(value, list) else [value]
            display = "、".join(
                str(v).lower() if isinstance(v, bool) else str(v) for v in values if v is not None
            )
            conditions.append(f"{self.labels[f.property_id]} {_OPERATORS[f.op]} {display}".rstrip())
        return f"（{'，'.join(conditions)}）" if conditions else ""


def check_plan(
    out: QaPlanOut, context: QaContext, model: BoundModel, types: ObjectTypeList
) -> QaPlan | QaGaps:
    if model.release_id != context.ontology.release_id or types.release.id != model.release_id:
        raise AppError(409, "query.release_changed", "The active release has changed.")
    check = _Check(context, model, types)
    gaps = check.reference_gaps(out)
    if gaps is not None:
        return gaps
    target = len(out.path) if out.target is None else out.target
    if (
        not 0 <= target <= len(out.path) <= QA_HOPS_MAX
        or any(len(f) > FILTERS_MAX for f in [out.filters, *(hop.filters for hop in out.path)])
        or (out.start is None and (out.path or out.filters))
    ):
        raise _invalid()

    start = None
    hops = []
    positions = []
    description = []
    if out.start is not None:
        current = context.refs[out.start]
        start = QaPlanStart(
            type_id=current,
            label=check.labels[current],
            filters=check.filters(current, out.filters),
        )
        positions.append(current)
        description.append(start.label + check.describe_filters(start.filters))
        for step in out.path:
            destination = check.destination(current, step)
            if destination is None:
                return QaGaps(elements=[], bindings=list(check.missing_bindings.values()))
            current = destination
            relation = context.refs[step.relation]
            hop = QaPlanHop(
                relation_id=relation,
                label=check.labels[relation],
                direction=step.direction,
                target_type_id=current,
                target_label=check.labels[current],
                filters=check.filters(current, step.filters),
            )
            hops.append(hop)
            positions.append(current)
            description.extend(
                [
                    hop.label + ("（反向）" if hop.direction == "in" else ""),
                    hop.target_label + check.describe_filters(hop.filters),
                ]
            )

    metric = check.metrics[context.refs[out.metric]] if out.metric is not None else None
    if metric is not None:
        # A start of another type would be dropped and the metric answered unrestricted.
        if positions and positions[target] != metric.subject_id:
            raise _invalid()
        if not metric_is_bound(metric, model):
            check.missing(metric.subject_id)
    if check.missing_bindings:
        return QaGaps(elements=[], bindings=list(check.missing_bindings.values()))
    if out.intent == "unanswerable" or (out.intent == "metric") != (metric is not None):
        raise _invalid()
    if out.intent != "metric" and start is None:
        raise _invalid()
    if metric is not None:
        action = f"计算{metric.label_zh}"
    else:
        verb = {"objects": "列出", "count": "统计", "rules": "检查约束"}[out.intent]
        action = f"{verb}（{check.labels[positions[target]]}）"
    return QaPlan(
        intent=out.intent,
        start=start,
        hops=hops,
        target=target,
        metric_id=metric.id if metric else None,
        description=" → ".join([*description, action]),
        assumptions=out.assumptions,
    )
