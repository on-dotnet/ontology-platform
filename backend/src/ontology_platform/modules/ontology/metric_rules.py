"""Metric definitions in proposals, working elements and release snapshots."""

import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from ontology_platform.modules.ontology import binding_rules, rules, schemas
from ontology_platform.modules.ontology.models import Element

INVALID = "metric.invalid"
_NUMERIC = {"integer", "decimal"}
_ORDERED = _NUMERIC | {"date", "dateTime"}
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?")
_CLOCK = r"(?:[01][0-9]|2[0-3])(?::?[0-5][0-9](?::?[0-5][0-9](?:[.,][0-9]{1,6}0*)?)?)?"
_TIMESTAMP = re.compile(rf"[^T ]+[T ]{_CLOCK}(?:Z|[+-]{_CLOCK})?")


def property_refs(definition: schemas.MetricDefinitionFields) -> Iterator[str]:
    if definition.property_ref is not None:
        yield definition.property_ref
    for condition in (*definition.filters, *definition.numerator):
        yield condition.property_ref


def _rows(definition: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield definition
    yield from definition.get("filters", [])
    yield from definition.get("numerator", [])


def stored_ids(definition: dict[str, Any] | None) -> set[UUID]:
    return {
        ref
        for row in _rows(definition or {})
        if row.get("propertyId") and (ref := rules.parse_id(str(row["propertyId"]))) is not None
    }


def stored(definition: schemas.MetricDefinitionFields, ids: Mapping[str, UUID]) -> dict[str, Any]:
    data = definition.model_dump(mode="json", by_alias=True)
    for row in _rows(data):
        ref = row.pop("propertyRef")
        row["propertyId"] = str(ids[ref]) if ref is not None else None
    return data


def as_fields(definition: dict[str, Any]) -> schemas.MetricDefinitionFields:
    parsed = schemas.MetricDefinition.model_validate(definition)
    data = parsed.model_dump(mode="json", by_alias=True)
    for row in _rows(data):
        row["propertyRef"] = row.pop("propertyId")
    return schemas.MetricDefinitionFields.model_validate(data)


def _scalar_ok(value: schemas.FilterValue, datatype: str) -> bool:
    # The logical datatype is known before binding. Column widths and ranges are checked by query.
    text = str(value)
    if datatype == "string":
        return isinstance(value, str) and not re.search(r"[\x00\ud800-\udfff]", value)
    if datatype == "boolean":
        return isinstance(value, bool) or text.lower() in ("true", "false")
    if datatype == "integer":
        return re.fullmatch(r"[+-]?[0-9]+", text) is not None
    try:
        if datatype == "decimal":
            if not _DECIMAL.fullmatch(text) and text not in ("NaN", "Infinity", "-Infinity"):
                return False
            Decimal(text)
        elif datatype == "date" and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
            date.fromisoformat(text)
        elif datatype == "dateTime" and _TIMESTAMP.fullmatch(text):
            datetime.fromisoformat(text)
        else:
            return False
    except (ValueError, InvalidOperation):
        return False
    return True


def _filter_ok(condition: schemas.MetricFilterFields, datatype: str | None) -> bool:
    if datatype is None:
        return False
    op, value = condition.op, condition.value
    if op in ("isNull", "notNull"):
        return value is None
    if op == "in":
        return (
            datatype != "boolean"
            and isinstance(value, list)
            and len(value) <= 100
            and all(_scalar_ok(entry, datatype) for entry in value)
        )
    if value is None or isinstance(value, list) or not _scalar_ok(value, datatype):
        return False
    if op in ("contains", "startsWith"):
        return datatype == "string"
    return datatype != "boolean" or op in ("eq", "ne")


def _problem(
    definition: schemas.MetricDefinitionFields | None,
    subject: binding_rules.Node | None,
    lookup: Callable[[str], binding_rules.Node | None],
) -> str | None:
    if subject is None or subject.kind != "entity_type" or not subject.active:
        return "the metric needs an active subject type"
    if definition is None:
        return "the metric definition is missing"
    aggregate = definition.aggregate
    if bool(definition.numerator) != (aggregate == "ratio"):
        return "only a ratio has numerator conditions and it needs at least one"
    datatypes: dict[str, str | None] = {}
    for ref in property_refs(definition):
        prop = lookup(ref)
        if prop is None or prop.kind != "property" or not prop.active or prop.domain != subject.key:
            return "each metric property must be active and belong directly to the subject type"
        datatypes[ref] = prop.datatype
    if aggregate in ("sum", "avg", "min", "max"):
        aggregate_ref = definition.property_ref
        allowed = _NUMERIC if aggregate in ("sum", "avg") else _ORDERED
        if aggregate_ref is None or datatypes[aggregate_ref] not in allowed:
            return "the aggregate needs a property of a compatible datatype"
    for condition in (*definition.filters, *definition.numerator):
        if not _filter_ok(condition, datatypes[condition.property_ref]):
            return "the filter operator or operand is incompatible with its property"
    return None


def proposal_problems(
    elements: Mapping[UUID, Element],
    items: Sequence[binding_rules.Proposed],
    *,
    only: int | None = None,
) -> Iterator[tuple[int, str]]:
    nodes = binding_rules.change_set_nodes(elements.values(), items)

    def lookup(ref: str) -> binding_rules.Node | None:
        return nodes.get(binding_rules.ref_key(ref) or "")

    for position, item in enumerate(items):
        if item.kind != "metric" or item.op == "delete" or (only is not None and only != position):
            continue
        node = nodes[binding_rules.item_key(item, position)]
        definition = item.fields.metric
        target = elements.get(item.target_id) if item.target_id is not None else None
        if "metric" not in item.fields.model_fields_set and target and target.metric is not None:
            definition = as_fields(target.metric)
        problem = _problem(definition, nodes.get(node.subject or ""), lookup)
        if problem:
            yield position, problem


def valid_stored(
    definition: dict[str, Any] | None, subject_id: UUID | None, elements: Mapping[UUID, Element]
) -> bool:
    def lookup(ref: str) -> binding_rules.Node | None:
        element_id = rules.parse_id(ref)
        element = elements.get(element_id) if element_id is not None else None
        return binding_rules.element_node(element) if element is not None else None

    if definition is None or subject_id is None:
        return False
    try:
        fields = as_fields(definition)
    except ValidationError:
        return False
    return _problem(fields, lookup(str(subject_id)), lookup) is None
