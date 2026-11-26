"""Check released property shapes against the bound objects of their target type."""

import asyncio
import json
import operator
import re
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.metrics import schemas as metrics
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.schemas import (
    ConstraintRule,
    ElementCopy,
    LangText,
    RdfValue,
)
from ontology_platform.modules.query import planner, schemas
from ontology_platform.modules.query import service as query
from ontology_platform.modules.query.scan import query_budget

_XSD = "http://www.w3.org/2001/XMLSchema#"
_DECIMAL = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
_NUMERIC = {
    "integer": re.compile(r"[+-]?[0-9]+"),
    "decimal": re.compile(_DECIMAL),
    "double": re.compile(rf"{_DECIMAL}(?:[eE][+-]?[0-9]+)?"),
}
_DAY = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_ZONE = r"(?:Z|[+-](?:(?:0[0-9]|1[0-3]):[0-5][0-9]|14:00))?"
_TIMESTAMP = re.compile(
    rf"{_DAY}T[0-2][0-9]:[0-5][0-9]:[0-5][0-9](?:\.(?P<fraction>[0-9]+))?{_ZONE}"
)
_BOUNDS = {
    "minInclusive": operator.ge,
    "maxInclusive": operator.le,
    "minExclusive": operator.gt,
    "maxExclusive": operator.lt,
}
type Parsed = str | bool | Decimal | date


def _parse(value: schemas.Scalar, datatype: str) -> Parsed:
    if datatype == "string" and isinstance(value, str):
        return value
    if datatype == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip() in {"true", "false", "1", "0"}:
            return value.strip() in {"true", "1"}
    if datatype in _NUMERIC and not isinstance(value, bool):
        text = str(value).strip()
        if _NUMERIC[datatype].fullmatch(text):
            return Decimal(text)
    if isinstance(value, str):
        text = value.strip()
        if datatype == "date" and re.fullmatch(rf"{_DAY}{_ZONE}", text):
            return date.fromisoformat(text[:10])
        if datatype == "dateTime" and (match := _TIMESTAMP.fullmatch(text)):
            # fromisoformat silently truncates digits past microseconds.
            if (match["fraction"] or "")[6:].strip("0"):
                raise ValueError("The timestamp exceeds microsecond precision.")
            instant = datetime.fromisoformat(text)
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=UTC)
            return instant.astimezone(UTC)
    raise ValueError("Invalid literal for the datatype.")


def _literal(term: RdfValue, datatype: str) -> tuple[Parsed, schemas.Scalar]:
    kind = (term.datatype or "string").removeprefix(_XSD)
    if term.lexical is None or (kind != datatype and not {kind, datatype} <= _NUMERIC.keys()):
        raise ValueError("The literal and property have incompatible datatypes.")
    parsed = _parse(term.lexical, kind)
    if isinstance(parsed, bool):
        return parsed, parsed
    if kind == "integer" and isinstance(parsed, Decimal) and abs(parsed) <= 2**53 - 1:
        return parsed, int(parsed)
    return parsed, term.lexical


def _object_value(value: schemas.Scalar, datatype: str) -> Parsed:
    # A date column can back a dateTime property; its serialized value has no time part.
    if datatype == "dateTime" and isinstance(value, str) and re.fullmatch(_DAY, value):
        return datetime.combine(date.fromisoformat(value), time.min, tzinfo=UTC)
    # Decimal.__str__ can use an exponent even for an exact fixed-point column.
    return _parse(value, "double" if datatype == "decimal" else datatype)


def _components(rule: ConstraintRule) -> Iterator[tuple[str, object]]:
    fields: tuple[tuple[str, object], ...] = (
        ("minCount", rule.min_count),
        ("maxCount", rule.max_count),
        ("datatype", rule.datatype),
        ("nodeKind", rule.node_kind),
        ("class", rule.class_id),
        ("allowedValues", True if rule.allowed_values_lost else rule.allowed_values),
        ("minInclusive", rule.min_inclusive),
        ("maxInclusive", rule.max_inclusive),
        ("minExclusive", rule.min_exclusive),
        ("maxExclusive", rule.max_exclusive),
        ("minLength", rule.min_length),
        ("maxLength", rule.max_length),
        ("pattern", rule.pattern),
    )
    for name, value in fields:
        if value is not None:
            yield name, value
    if rule.flags and rule.pattern is None:
        yield "flags", rule.flags


@dataclass(frozen=True)
class Pattern:
    expression: str
    ignore_case: bool


@dataclass
class Check:
    name: metrics.RuleCheck
    expected: schemas.Scalar | list[schemas.Scalar]
    accepts: Callable[[schemas.Scalar], bool] | Pattern


def _compile(name: str, operand: object, rule: ConstraintRule, datatype: str) -> Check | None:
    if name == "minCount" and isinstance(operand, int) and operand >= 1:
        return Check("minCount", operand, lambda _: True)
    if name in _BOUNDS and isinstance(operand, RdfValue):
        expected, shown = _literal(operand, datatype)
        compare = _BOUNDS[name]
        return Check(
            cast(metrics.RuleCheck, name),
            shown,
            lambda value: bool(compare(_object_value(value, datatype), expected)),
        )
    if name == "allowedValues" and not rule.allowed_values_lost and rule.allowed_values is not None:
        literals = [_literal(term, datatype) for term in rule.allowed_values]
        allowed = {value for value, _ in literals}
        return Check(
            "allowedValues",
            [shown for _, shown in literals],
            lambda value: _object_value(value, datatype) in allowed,
        )
    if name == "pattern" and rule.flags not in {None, "", "i"}:
        return None
    if name in {"minLength", "maxLength", "pattern"} and datatype != "string":
        raise ValueError("A text check requires a string property.")
    if name == "pattern" and isinstance(operand, str):
        return Check("pattern", operand, Pattern(operand, rule.flags == "i"))
    if name == "minLength" and isinstance(operand, int):
        return Check("minLength", operand, lambda value: len(_text(value)) >= operand)
    if name == "maxLength" and isinstance(operand, int):
        return Check("maxLength", operand, lambda value: len(_text(value)) <= operand)
    return None


def _text(value: schemas.Scalar) -> str:
    if isinstance(value, str):
        return value
    raise ValueError("Expected a text value.")


def _language(preferences: str) -> str:
    preferred = "zh"
    best = 0.0
    for entry in preferences.lower().split(","):
        tag, _, weight = entry.strip().partition(";")
        language = tag.strip().partition("-")[0]
        if language not in {"zh", "en"}:
            continue
        try:
            quality = float(weight.strip().removeprefix("q=")) if weight else 1.0
        except ValueError:
            continue
        if best < quality <= 1:
            preferred, best = language, quality
    return preferred


def _message(messages: Sequence[LangText], language: str) -> str | None:
    for message in messages:
        if (message.lang or "").lower().partition("-")[0] == language:
            return message.text
    return next((m.text for m in messages if not m.lang), messages[0].text if messages else None)


def _label(element: ElementCopy, language: str) -> str:
    if language == "en" and element.label_en:
        return element.label_en
    return element.label_zh or element.label_en or element.local_name or str(element.id)


def _plan(
    constraint: ElementCopy,
    rule: ConstraintRule,
    path: ElementCopy | None,
    bound_ids: set[UUID],
    language: str,
) -> tuple[metrics.RuleResult, list[Check]]:
    prop = path if path is not None and path.kind == "property" else None
    result = metrics.RuleResult(
        constraint_id=constraint.id,
        constraint_label=_label(constraint, language),
        property_id=prop.id if prop else None,
        property_label=_label(prop, language) if prop else None,
        checks=[],
        unchecked=[],
        message=_message(rule.message, language),
        violations=0,
        samples=[],
    )
    checks = []
    for name, operand in _components(rule):
        reason: metrics.UncheckedReason
        if prop is None:
            reason = "path_not_property"
        elif prop.id not in bound_ids:
            reason = "path_not_bound"
        else:
            try:
                check = _compile(name, operand, rule, prop.datatype or "")
            except (ValueError, InvalidOperation, OverflowError):
                reason = "value_mismatch"
            else:
                if check is not None:
                    checks.append(check)
                    continue
                reason = "check_not_supported"
        result.unchecked.append(metrics.Unchecked(check=name, reason=reason))
    return result, checks


type PatternFailures = dict[tuple[UUID, Pattern], list[int] | None]


def _pattern_indices(
    expression: str, ignore_case: bool, values: list[schemas.Scalar | None] | None
) -> list[int] | None:
    if values is None:
        return None
    try:
        regex = re.compile(expression, re.IGNORECASE if ignore_case else 0)
        return [i for i, v in enumerate(values) if v is not None and regex.search(_text(v)) is None]
    except (ValueError, re.PatternError, OverflowError, RecursionError):
        return None


async def _run_patterns(
    plans: Sequence[tuple[metrics.RuleResult, list[Check]]], rows: Sequence[schemas.ObjectRow]
) -> PatternFailures:
    requests = list(
        dict.fromkeys(
            (result.property_id, check.accepts)
            for result, checks in plans
            for check in checks
            if result.property_id is not None and isinstance(check.accepts, Pattern)
        )
    )
    if not requests:
        return {}
    # Send each requested property once, even when several shapes use its values.
    columns = {
        str(prop): (
            None
            if any(prop in row.truncated for row in rows)
            else [row.values[prop] for row in rows]
        )
        for prop in {prop for prop, _ in requests}
    }
    patterns = [(str(prop), p.expression, p.ignore_case) for prop, p in requests]
    payload = json.dumps((columns, patterns), separators=(",", ":")).encode("ascii")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-B",
        "-m",
        "ontology_platform.modules.metrics.rule_check",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={},
    )
    try:
        output, _ = await process.communicate(payload)
    finally:
        if process.returncode is None:
            # Both cancellation and the shared deadline must stop the native regex engine.
            with suppress(ProcessLookupError):
                process.kill()
            await process.communicate()
    if process.returncode:
        raise AppError(500, "internal.error", "The rule check process failed.")
    failures: list[list[int] | None] = json.loads(output)
    return dict(zip(requests, failures, strict=True))


def _indices(
    check: Check, prop: UUID, rows: Sequence[schemas.ObjectRow], patterns: PatternFailures
) -> list[int]:
    if isinstance(check.accepts, Pattern):
        failed = patterns[prop, check.accepts]
        if failed is None:
            raise ValueError("The pattern and property values could not be checked.")
        return failed
    indices = []
    for i, row in enumerate(rows):
        actual = row.values[prop]
        if check.name != "minCount" and prop in row.truncated:
            raise ValueError("The full property value is unavailable.")
        if actual is None:
            if check.name == "minCount":
                indices.append(i)
        elif not check.accepts(actual):
            indices.append(i)
    return indices


def _inspect(
    result: metrics.RuleResult,
    checks: list[Check],
    rows: Sequence[schemas.ObjectRow],
    limit: int,
    patterns: PatternFailures,
) -> None:
    prop = result.property_id
    if prop is None:
        return
    failed: dict[int, list[Check]] = {}
    for check in checks:
        try:
            indices = _indices(check, prop, rows, patterns)
        except (ValueError, InvalidOperation, OverflowError):
            result.unchecked.append(metrics.Unchecked(check=check.name, reason="value_mismatch"))
            continue
        # A late mismatch invalidates this component's earlier verdicts.
        result.checks.append(check.name)
        for i in indices:
            failed.setdefault(i, []).append(check)
    result.violations = len(failed)
    for i in sorted(failed)[:limit]:
        row = rows[i]
        result.samples.append(
            metrics.RuleSample(
                object=row,
                failed=[
                    metrics.FailedCheck(check=c.name, expected=c.expected, actual=row.values[prop])
                    for c in failed[i]
                ],
            )
        )


async def check_rules(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    *,
    within: schemas.KeySet | None = None,
    limit: int = 50,
    language: str = "zh",
) -> metrics.RuleReport:
    if not 1 <= limit <= schemas.PAGE_MAX:
        raise AppError(422, "validation.failed", "The sample limit is out of range.")
    async with query_budget() as budget:
        released = await bindings.released_ontology(db, ontology_id)
        if released is None:
            await ontology.get_ontology_summary(db, ontology_id)
            raise AppError(409, "query.no_release", "The ontology has no active release.")
        model = await bindings.bound_model(db, ontology_id)
        if model is None or model.release_id != released.release_id:
            raise AppError(409, "query.release_changed", "The active release has changed.")
        budget.pin(model)
        bound = planner.bound_type(model, type_id)
        if within is not None and within.type_id != type_id:
            raise AppError(422, "query.invalid_filter", "The keys belong to a different type.")
        bound_ids = {p.property_id for p in bound.properties}
        language = _language(language)
        active = {e.id: e for e in released.elements if e.status == "active"}
        plans = [
            _plan(element, rule, active.get(rule.path_id), bound_ids, language)
            for element in active.values()
            if element.kind == "constraint" and element.domain_id == type_id
            for rule in element.rules or ()
        ]
        properties = {r.property_id for r, checks in plans if checks and r.property_id is not None}
        release = schemas.ReleaseRef(id=model.release_id, version=model.version)
        rows: tuple[schemas.ObjectRow, ...] = ()
        steps: list[schemas.StepOut] = []
        if properties:
            scan = await query.scan(
                db,
                ontology_id,
                type_id,
                (),
                property_ids=tuple(properties),
                within=within,
                max_rows=sys.maxsize,
            )
            if scan.release != release:
                raise AppError(409, "query.release_changed", "The active release has changed.")
            rows = scan.rows
            steps = [schemas.StepOut.model_validate(s, from_attributes=True) for s in scan.steps]
        patterns = await _run_patterns(plans, rows)
        for result, checks in plans:
            _inspect(result, checks, rows, limit, patterns)
        results = [r for r, _ in plans]
        return metrics.RuleReport(
            release=release,
            type_id=type_id,
            scanned=len(rows),
            checked_rules=sum(bool(r.checks) for r in results),
            unchecked_rules=sum(bool(r.unchecked) or not r.checks for r in results),
            results=results,
            steps=steps,
        )


if __name__ == "__main__":
    columns, patterns = json.load(sys.stdin)
    failures = [
        _pattern_indices(expr, ignore_case, columns[prop]) for prop, expr, ignore_case in patterns
    ]
    json.dump(failures, sys.stdout)
