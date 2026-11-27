"""Offline plan equivalence for the steel demo (spec 007, section 13.4)."""

import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from ontology_platform.modules.ai.qa_prompts import QaPlanOut
from ontology_platform.modules.ai.qa_scoring import parse_plan, score_plan


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
    model = parse_plan(expected)
    assert isinstance(model, QaPlanOut)
    assert score_plan(expected, model) == (True, None)
    assert score_plan(model, {**expected, "metric": "M2"}) == (False, "metric")
