"""Compare a saved expectation with the facts of a completed question."""

from decimal import MAX_PREC, Decimal, localcontext

from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.cq.schemas import CqCheckDetail, CqExpect, CqResult

_DIFF_LIMIT = 20


def _compare_objects(expect: CqExpect, question: QaQuestion) -> tuple[CqResult, CqCheckDetail]:
    keys = question.answer_keys
    actual = set(keys.keys) if keys is not None else set()
    expected = set(expect.keys)
    type_matches = keys is not None and keys.type_id == expect.type_id
    detail = CqCheckDetail(
        missing=sorted(expected - actual)[:_DIFF_LIMIT],
        extra=sorted(actual - expected)[:_DIFF_LIMIT],
        actual=str(len(actual)) if keys is not None else None,
        error_code=None if type_matches else "cq.type_mismatch",
    )
    return ("pass" if type_matches and actual == expected else "fail"), detail


def _compare_number(expect: CqExpect, question: QaQuestion) -> tuple[CqResult, CqCheckDetail]:
    # The metric fact holds rounded display text. Its evidence retains the decimal value.
    metric = question.evidence.metric if question.evidence is not None else None
    count = question.answer.facts.count if question.answer is not None else None
    actual = metric.value if metric is not None else (str(count) if count is not None else None)
    if actual is None:
        return "fail", CqCheckDetail(missing=[], extra=[], actual=None, error_code="cq.no_number")
    if expect.number is None:
        raise ValueError("A numeric expectation requires a number.")

    # Rounding the difference to the default 28 digits can hide an exceeded tolerance.
    with localcontext(prec=MAX_PREC):
        difference = (Decimal(actual) - Decimal(expect.number)).copy_abs()
    result: CqResult = "pass" if difference <= Decimal(expect.tolerance) else "fail"
    return result, CqCheckDetail(missing=[], extra=[], actual=actual, error_code=None)


def compare(expect: CqExpect, question: QaQuestion) -> tuple[CqResult, CqCheckDetail | None]:
    if question.status == "unanswerable":
        return "unanswerable", None
    if question.status == "failed":
        detail = CqCheckDetail(missing=[], extra=[], actual=None, error_code=question.error_code)
        return "error", detail
    if question.status != "answered":
        return "pending", None
    if expect.kind == "objects":
        return _compare_objects(expect, question)
    if expect.kind == "number":
        return _compare_number(expect, question)
    return "pass", None
