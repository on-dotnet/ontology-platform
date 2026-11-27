"""Offline plan equivalence for the steel demo (spec 007, section 13.4)."""

import tomllib
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
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


def _plan(value: PlanInput) -> QaPlanOut:
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
        left, right = _plan(expected), _plan(actual)
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


@pytest.fixture
def scripts() -> dict[str, Any]:
    path = Path(__file__).parent / "fixtures" / "qa" / "steel" / "plans.toml"
    return tomllib.loads(path.read_text("utf-8"))


def test_reverse_q2(scripts: dict[str, Any]) -> None:
    expected = scripts["Q2"]["plan"]
    actual = {
        **expected,
        "start": "T3",
        "target": 1,
        "filters": expected["path"][-1]["filters"],
        "path": [
            {"relation": "R5", "direction": "out", "filters": []},
            {"relation": "R4", "direction": "in", "filters": []},
            {"relation": "R3", "direction": "in", "filters": []},
            {"relation": "R2", "direction": "in", "filters": []},
            {"relation": "R1", "direction": "in", "filters": expected["filters"]},
        ],
    }
    assert score_plan(expected, actual) == (True, None)
    assert score_plan(actual, expected) == (True, None)
    del actual["target"]
    assert score_plan(expected, actual) == (False, "target")
    actual.update(target=1, start="T2")
    assert score_plan(expected, actual) == (False, "path")


def test_q2_without_target_returns_inspections(scripts: dict[str, Any]) -> None:
    expected = scripts["Q2"]["plan"]
    actual = deepcopy(expected)
    del actual["target"]
    assert score_plan(expected, actual) == (False, "target")


def test_filter_order_and_values(scripts: dict[str, Any]) -> None:
    expected = deepcopy(scripts["Q2"]["plan"])
    expected["filters"].append({"property": "P1", "op": "notNull"})
    actual = deepcopy(expected)
    actual["filters"].reverse()
    assert score_plan(expected, actual) == (True, None)
    actual["filters"][1]["value"] = "Q275B"
    assert score_plan(expected, actual) == (False, "filters")


def test_shorter_path_and_misplaced_filter(scripts: dict[str, Any]) -> None:
    expected = scripts["Q2"]["plan"]
    actual = deepcopy(expected)
    actual["path"].pop()
    assert score_plan(expected, actual) == (False, "path")
    actual = deepcopy(expected)
    actual["path"][3]["filters"] = actual["path"][4]["filters"]
    actual["path"][4]["filters"] = []
    assert score_plan(expected, actual) == (False, "filters")


def test_zero_hop_and_unanswerable(scripts: dict[str, Any]) -> None:
    expected = scripts["Q1"]["plan"]
    assert score_plan(expected, {**expected, "start": "T2"}) == (False, "path")
    assert score_plan(expected, {**expected, "target": 0}) == (True, None)
    gap = scripts["Q5"]["plan"]
    assert score_plan(gap, {**gap, "missing": gap["missing"][:1]}) == (False, "missing")


def test_metric_identity_and_model_input(scripts: dict[str, Any]) -> None:
    expected = scripts["Q3"]["plan"]
    model = _plan(expected)
    assert isinstance(model, QaPlanOut)
    assert score_plan(expected, model) == (True, None)
    assert score_plan(model, {**expected, "metric": "M2"}) == (False, "metric")
