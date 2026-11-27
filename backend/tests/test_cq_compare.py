from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from ontology_platform.modules.ai.schemas import (
    QaAnswer,
    QaEvidence,
    QaFactMetric,
    QaFactObject,
    QaFacts,
    QaQuestion,
    QaStatus,
)
from ontology_platform.modules.cq.compare import compare
from ontology_platform.modules.cq.schemas import CqCheckDetail, CqExpect, CqExpectKind
from ontology_platform.modules.query.cursor import encode_key
from ontology_platform.modules.query.schemas import KeySet


def _expect(
    kind: CqExpectKind,
    *,
    type_id: UUID | None = None,
    keys: tuple[str, ...] = (),
    number: str | None = None,
    tolerance: str = "0",
) -> CqExpect:
    return CqExpect(kind=kind, type_id=type_id, keys=list(keys), number=number, tolerance=tolerance)


def _question(
    *,
    status: QaStatus = "answered",
    keys: KeySet | None = None,
    count: int | None = None,
    evidence: QaEvidence | None = None,
    error_code: str | None = None,
) -> QaQuestion:
    objects: list[QaFactObject] = []
    if keys is not None:
        objects = [QaFactObject(type_id=keys.type_id, key=key, label=key) for key in keys.keys[:50]]
    metric = evidence.metric if evidence is not None else None
    facts = QaFacts(
        count=count,
        metric=QaFactMetric(label=metric.label, display=metric.display) if metric else None,
        objects=objects,
        violations=None,
    )
    answer = QaAnswer(text=None, facts=facts, cited_keys=[], counterpoints=[], notes=[])
    now = datetime.now(UTC)
    return QaQuestion.model_validate(
        {
            "id": uuid4(),
            "ontology_id": uuid4(),
            "question": "检验结果是什么？",
            "origin": "cq",
            "cq_question_id": uuid4(),
            "asked_by": {"id": uuid4(), "display_name": "Editor"},
            "status": status,
            "step": "done",
            "release": evidence.release if evidence else None,
            "plan": None,
            "gaps": None,
            "answer": answer if status == "answered" else None,
            "answer_keys": keys,
            "evidence": evidence,
            "gap_proposal": None,
            "error_code": error_code,
            "created_at": now,
            "finished_at": now,
        }
    )


def test_answerable_needs_only_answered_status() -> None:
    assert compare(_expect("answerable"), _question()) == ("pass", None)


@pytest.mark.parametrize("kind", ["answerable", "objects", "number"])
def test_unanswerable_and_failed_keep_qa_outcome(kind: CqExpectKind) -> None:
    expect = _expect(kind, type_id=uuid4(), number="0")
    assert compare(expect, _question(status="unanswerable")) == ("unanswerable", None)
    failed = _question(status="failed", error_code="qa.timeout")
    assert compare(expect, failed) == (
        "error",
        CqCheckDetail(missing=[], extra=[], actual=None, error_code="qa.timeout"),
    )


def test_objects_compare_full_set_beyond_visible_rows() -> None:
    type_id = uuid4()
    keys = tuple(encode_key([f"H{i}"]) for i in range(75))
    question = _question(keys=KeySet(type_id, keys), count=len(keys))
    expect = _expect("objects", type_id=type_id, keys=tuple(reversed(keys)))
    result, detail = compare(expect, question)
    assert result == "pass"
    assert detail is not None
    assert detail.actual == "75"
    assert compare(_expect("number", number="75"), question)[0] == "pass"

    replacement = encode_key(["H999"])
    expect = _expect("objects", type_id=type_id, keys=(*keys[:-1], replacement))
    assert compare(expect, question) == (
        "fail",
        CqCheckDetail(missing=[replacement], extra=[keys[-1]], actual="75", error_code=None),
    )


def test_each_key_difference_is_limited_to_twenty() -> None:
    type_id = uuid4()
    expected = tuple(encode_key([f"E{i}"]) for i in range(24))
    actual = tuple(encode_key([f"A{i}"]) for i in range(31))
    result, detail = compare(
        _expect("objects", type_id=type_id, keys=expected), _question(keys=KeySet(type_id, actual))
    )
    assert result == "fail"
    assert detail is not None
    assert len(set(detail.missing)) == len(detail.missing) == 20
    assert len(set(detail.extra)) == len(detail.extra) == 20
    assert set(detail.missing) <= set(expected)
    assert set(detail.extra) <= set(actual)
    assert detail.actual == "31"


@pytest.mark.parametrize("keys", [(), (encode_key(["W240101201"]),)])
def test_objects_require_matching_type_even_for_equal_keys(keys: tuple[str, ...]) -> None:
    type_id = uuid4()
    expect = _expect("objects", type_id=type_id, keys=keys)
    assert compare(expect, _question(keys=KeySet(type_id, keys)))[0] == "pass"
    result, detail = compare(expect, _question(keys=KeySet(uuid4(), keys)))
    assert result == "fail"
    assert detail is not None
    assert (detail.error_code, detail.actual) == ("cq.type_mismatch", str(len(keys)))


def test_absent_answer_keys_cannot_match_an_empty_set() -> None:
    result, detail = compare(_expect("objects", type_id=uuid4()), _question())
    assert result == "fail"
    assert detail is not None
    assert detail.error_code == "cq.type_mismatch"


@pytest.mark.parametrize(
    ("count", "number", "tolerance", "passes"),
    [
        (0, "0", "0", True),
        (18, "18.25", "0.25", True),
        (18, "17.75", "0.25", True),
        (18, "17.74999999999999999999999999999999", "0.25", False),
        (9007199254740993, "9007199254740992", "0", False),
    ],
)
def test_numeric_count_and_exact_tolerance(
    count: int, number: str, tolerance: str, passes: bool
) -> None:
    question = _question(count=count)
    result, detail = compare(_expect("number", number=number, tolerance=tolerance), question)
    assert result == ("pass" if passes else "fail")
    assert detail is not None
    assert detail.actual == str(count)


@pytest.mark.parametrize(
    ("value", "tolerance", "result"),
    [
        ("0.9230769230769230769230769231", "0.0005", "pass"),
        ("0.9230769230769230769230769231", "0", "fail"),
        ("0.9230769230769231", "0", "pass"),
        (None, "0", "fail"),
    ],
)
def test_metric_uses_unrounded_evidence_value(
    value: str | None, tolerance: str, result: str
) -> None:
    release = {"id": uuid4(), "version": 2}
    evidence = QaEvidence.model_validate(
        {
            "release": release,
            "elements": [],
            "bindings": [],
            "steps": [],
            "rows": [],
            "truncated": False,
            "tail": [],
            "rules": None,
            "metric": {
                "release": release,
                "metric_id": uuid4(),
                "label": "检验合格率",
                "unit": None,
                "aggregate": "ratio",
                "value": value,
                "display": "92.3%" if value else None,
                "population": 39 if value else 0,
                "matched": 36 if value else 0,
                "nulls": 0,
                "reason": None if value else "empty_population",
                "steps": [],
            },
        }
    )
    expect = _expect("number", number="0.9230769230769231", tolerance=tolerance)
    assert compare(expect, _question(evidence=evidence)) == (
        result,
        CqCheckDetail(
            missing=[], extra=[], actual=value, error_code="cq.no_number" if value is None else None
        ),
    )


def test_missing_numeric_fact_is_not_zero() -> None:
    assert compare(_expect("number", number="0"), _question()) == (
        "fail",
        CqCheckDetail(missing=[], extra=[], actual=None, error_code="cq.no_number"),
    )
