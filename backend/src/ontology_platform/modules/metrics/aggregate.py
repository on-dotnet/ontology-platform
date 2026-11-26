"""Evaluate a released definition over bounded, primary-key ordered scans."""

import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.metrics.schemas import MetricValue
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.schemas import MetricAggregate, MetricFilter
from ontology_platform.modules.query import schemas, service


def _filters(conditions: list[MetricFilter]) -> list[schemas.Filter]:
    return [schemas.Filter.model_validate(f, from_attributes=True) for f in conditions]


def _utc(value: schemas.Scalar) -> datetime:
    instant = datetime.fromisoformat(str(value))
    return (instant if instant.tzinfo else instant.replace(tzinfo=UTC)).astimezone(UTC)


def _aggregate(
    operation: MetricAggregate, datatype: str | None, values: Sequence[schemas.Scalar]
) -> Decimal | str | None:
    if not values:
        return None
    extreme = min if operation == "min" else max
    try:
        if datatype == "date":
            return extreme(date.fromisoformat(str(v)) for v in values).isoformat()
        if datatype == "dateTime":
            return extreme(_utc(v) for v in values).isoformat()
        numbers = [Decimal(str(v)) for v in values]
        if any(not n.is_finite() for n in numbers):
            raise ValueError("Non-finite measurement")
        if operation in ("min", "max"):
            return extreme(numbers)
        # Keep all decimal places when large and small measurements are added together.
        with localcontext() as context:
            highest = max(n.adjusted() for n in numbers)
            lowest = min(n.adjusted() - len(n.as_tuple().digits) + 1 for n in numbers)
            fractional_precision = context.prec
            context.prec = max(context.prec, highest - lowest + 1 + len(str(len(numbers))))
            total = sum(numbers, Decimal(0))
            if operation == "avg":
                context.prec = max(context.prec, total.adjusted() + 1 + fractional_precision)
                return total / len(numbers)
            return total
    except (ValueError, InvalidOperation, OverflowError) as exc:
        raise AppError(409, "query.source_mismatch", "A value cannot be aggregated.") from exc


async def evaluate(
    db: AsyncSession,
    ontology_id: UUID,
    metric: bindings.MetricCopy,
    subject: bindings.BoundType,
    within: schemas.KeySet | None,
) -> MetricValue:
    definition = metric.metric
    operation = definition.aggregate
    prop = definition.property_id
    filters = _filters(definition.filters)
    # scan applies the configured metric_rows_max; this caller imposes no narrower limit.
    scan = await service.scan(
        db,
        ontology_id,
        subject.type_id,
        filters,
        within=within,
        property_ids=[prop] if prop is not None and operation not in ("count", "ratio") else [],
        max_rows=sys.maxsize,
    )
    population = len(scan.rows)
    steps = scan.steps
    matched = None
    nulls = 0
    value: Decimal | str | None
    if operation == "ratio":
        numerator = await service.scan(
            db,
            ontology_id,
            subject.type_id,
            filters + _filters(definition.numerator),
            within=within,
            property_ids=[],
            max_rows=sys.maxsize,
        )
        # Separate source reads can see newly inserted rows. Keep the original population.
        population_keys = {row.key for row in scan.rows}
        matched = len(population_keys.intersection(row.key for row in numerator.rows))
        steps += numerator.steps
        value = Decimal(matched) / population if population else None
    elif operation == "count":
        value = Decimal(population)
    else:
        if prop is None:
            raise AppError(422, "metric.invalid", "The aggregate needs a property.")
        datatype = next(p.datatype for p in subject.properties if p.property_id == prop)
        values = [v for row in scan.rows if (v := row.values[prop]) is not None]
        nulls = population - len(values)
        value = _aggregate(operation, datatype, values)

    display = None if value is None else str(value)
    if isinstance(value, Decimal):
        unit = "%" if operation == "ratio" and definition.percent else "f"
        display = format(value, f".{definition.decimals}{unit}")
    return MetricValue(
        release=scan.release,
        metric_id=metric.id,
        label=metric.label_zh,
        unit=metric.unit,
        aggregate=operation,
        value=format(value, "f") if isinstance(value, Decimal) else value,
        display=display,
        population=population,
        matched=matched,
        nulls=nulls,
        reason="empty_population" if value is None and not population else None,
        steps=[schemas.StepOut.model_validate(step, from_attributes=True) for step in steps],
    )
