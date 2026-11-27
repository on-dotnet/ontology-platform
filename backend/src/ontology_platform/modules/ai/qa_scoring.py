"""Offline comparison of two question plans in the same reference namespace."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from ontology_platform.modules.ai.qa_prompts import QaPlanOut

type PlanInput = QaPlanOut | dict[str, Any]
type Relations = Mapping[str, tuple[str, str]]

# A plan contains only its starting type. Resolving the other positions needs the
# domain and range of each relation, in the same reference namespace as the plans.
STEEL_RELATIONS: Relations = {
    "R1": ("T1", "T4"),
    "R2": ("T4", "T5"),
    "R3": ("T5", "T6"),
    "R4": ("T6", "T2"),
    "R5": ("T3", "T2"),
    "R6": ("T2", "T7"),
}


def parse_plan(value: PlanInput) -> QaPlanOut:
    if isinstance(value, QaPlanOut):
        return value
    # TOML omits nulls. Preserve the caller's copy, including nested filters.
    data = deepcopy(value)
    for field in ("start", "metric", "target"):
        data.setdefault(field, None)
    for step in [data, *data.get("path", [])]:
        for condition in step.get("filters", []):
            condition.setdefault("value", None)
            condition.setdefault("values", None)
    return QaPlanOut.model_validate(data)


def _types(plan: QaPlanOut, relations: Relations) -> list[str | None]:
    types = [plan.start]
    for hop in plan.path:
        source, dest = relations[hop.relation]
        if hop.direction == "in":
            source, dest = dest, source
        if types[-1] != source:
            raise ValueError("path")
        types.append(dest)
    return types


def _filters(plan: QaPlanOut) -> list[list[str]]:
    groups = []
    for conditions in [plan.filters, *(h.filters for h in plan.path)]:
        keys = []
        for condition in conditions:
            if condition.op == "in" and condition.values is not None:
                condition = condition.model_copy(update={"values": sorted(set(condition.values))})
            keys.append(condition.model_dump_json())
        groups.append(sorted(keys))
    return groups


def _missing(plan: QaPlanOut) -> set[tuple[str, str, frozenset[str]]]:
    return {(m.kind, m.label_zh, frozenset(m.near)) for m in plan.missing}


def score_plan(
    expected: PlanInput, actual: PlanInput, *, relations: Relations = STEEL_RELATIONS
) -> tuple[bool, str | None]:
    """Compare plans in one reference namespace and name the first differing component."""
    try:
        left, right = parse_plan(expected), parse_plan(actual)
    except ValidationError:
        return False, "schema"
    if left.intent != right.intent:
        return False, "intent"
    if left.metric != right.metric:
        return False, "metric"
    if _missing(left) != _missing(right):
        return False, "missing"
    try:
        vertices, other = _types(left, relations), _types(right, relations)
    except (KeyError, ValueError):
        return False, "path"
    edges = [(h.relation, h.direction) for h in left.path]
    direct = [(h.relation, h.direction) for h in right.path]
    reverse = [(r, "in" if d == "out" else "out") for r, d in reversed(direct)]
    target = len(edges) if left.target is None else left.target
    position = len(direct) if right.target is None else right.target
    filters, other_filters = _filters(left), _filters(right)
    candidates = [
        (index, groups)
        for nodes, hops, index, groups in (
            (other, direct, position, other_filters),
            (other[::-1], reverse, len(direct) - position, other_filters[::-1]),
        )
        if nodes == vertices and hops == edges
    ]
    if not candidates:
        return False, "path"
    aligned = [groups for index, groups in candidates if index == target]
    if not aligned or not 0 <= target < len(vertices):
        return False, "target"
    if filters not in aligned:
        return False, "filters"
    return True, None
