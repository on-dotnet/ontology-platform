"""Translate query filters and scalar values at the connector boundary."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors.models import ColumnFamily
from ontology_platform.modules.connectors.schemas import CatalogColumn
from ontology_platform.modules.connectors.statements import ColumnRef, Condition, Operator, Value
from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.modules.query import schemas

_ORDERED: tuple[schemas.FilterOp, ...] = ("eq", "ne", "lt", "le", "gt", "ge")
_NULL_OPS: tuple[schemas.FilterOp, ...] = ("isNull", "notNull")
_INTEGER_LIMIT = {"smallint": 2**15, "integer": 2**31, "bigint": 2**63}
_SURROGATE = re.compile(r"[\ud800-\udfff]")
# fromisoformat normalizes overflowing offset minutes and drops sub-microsecond digits.
_CLOCK = r"(?:[01][0-9]|2[0-3])(?::?[0-5][0-9](?::?[0-5][0-9](?:[.,][0-9]{1,6}0*)?)?)?"
_TIMESTAMP = re.compile(rf"[^T ]+[T ]{_CLOCK}(?:Z|[+-]{_CLOCK})?")


def ops(datatype: Datatype, family: ColumnFamily) -> list[schemas.FilterOp]:
    match datatype, family:
        case "string", "string":
            return [*_ORDERED, "contains", "startsWith", "in", *_NULL_OPS]
        case "string", "opaque":
            return ["eq", "ne", "in", *_NULL_OPS]
        case "boolean", "boolean":
            return ["eq", "ne", *_NULL_OPS]
        case ("integer" | "decimal", "integer") | ("decimal", "decimal"):
            return [*_ORDERED, "in", *_NULL_OPS]
        case ("date" | "dateTime", "date") | ("dateTime", "dateTime"):
            return [*_ORDERED, "in", *_NULL_OPS]
        case _:
            return []


def _text_value(value: str, column: CatalogColumn) -> str:
    if "\x00" in value:
        raise ValueError("Invalid text value.")
    if _SURROGATE.search(value):
        # Decode intact UTF-16 pairs to scalar values; the decoder rejects unpaired halves.
        value = value.encode("utf-16-le", errors="surrogatepass").decode("utf-16-le")
    source = column.type.lower()
    if column.family == "string":
        width = re.fullmatch(r"character\(([0-9]+)\)", source)
        if width and len(value) > int(width[1]):
            raise ValueError("Text exceeds the column width.")
    elif source == "uuid":
        token = value[1:-1] if value.startswith("{") and value.endswith("}") else value
        if not re.fullmatch(r"[0-9a-fA-F]{4}(?:-?[0-9a-fA-F]{4}){7}", token):
            raise ValueError("Invalid UUID value.")
        return str(UUID(token))
    return value


def _integer_value(value: object, source: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value):
        number = int(value)
    else:
        raise ValueError("Invalid integer value.")
    limit = _INTEGER_LIMIT.get(source.lower())
    if limit is None or not -limit <= number < limit:
        raise ValueError("Integer outside the column range.")
    return number


def parse_value(value: object, column: CatalogColumn) -> str | int | Decimal | date:
    """Parse a non-null filter, key or cursor component using its physical column type."""
    match column.family:
        case "string" | "opaque":
            if isinstance(value, str):
                return _text_value(value, column)
        case "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                return value.lower() == "true"
        case "integer":
            return _integer_value(value, column.type)
        case "decimal":
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                number = str(value)
                # PostgreSQL can also return these three non-finite values as cursor components.
                if number in {"NaN", "Infinity", "-Infinity"} or re.fullmatch(
                    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?", number
                ):
                    try:
                        return Decimal(number)
                    except InvalidOperation as exc:
                        raise ValueError("Invalid decimal value.") from exc
        case "date":
            if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                return date.fromisoformat(value)
        case "dateTime":
            if isinstance(value, str) and _TIMESTAMP.fullmatch(value):
                return datetime.fromisoformat(value)
    raise ValueError("Invalid value for the column type.")


def _condition_value(value: object, column: CatalogColumn, datatype: Datatype) -> Value:
    if (
        datatype == "dateTime"
        and column.family == "date"
        and isinstance(value, str)
        and _TIMESTAMP.fullmatch(value)
    ):
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None:
            return instant
        try:
            return instant.astimezone(UTC).replace(tzinfo=None)
        except OverflowError as exc:
            # 0001-01-01T00:00:00+05:00 has no UTC time within the supported years.
            raise ValueError("The time is out of range.") from exc
    return parse_value(value, column)


def condition(item: schemas.Filter, column: CatalogColumn, datatype: Datatype) -> Condition:
    invalid = AppError(422, "query.invalid_filter", "The filter is invalid.")
    op = item.op
    if op not in ops(datatype, column.family):
        raise invalid
    ref = ColumnRef(column.name)
    value = item.value
    try:
        match op:
            case "isNull" | "notNull":
                if value is None:
                    return Condition(ref, "is_null" if op == "isNull" else "not_null")
            case "in":
                if isinstance(value, list) and len(value) <= schemas.IN_VALUES_MAX:
                    return Condition(
                        ref, "in", tuple(_condition_value(v, column, datatype) for v in value)
                    )
            case _:
                operator: Operator = "starts_with" if op == "startsWith" else op
                return Condition(ref, operator, _condition_value(value, column, datatype))
    except ValueError:
        raise invalid from None
    raise invalid


def string_value(value: Value) -> str:
    """Encode a non-null key or cursor component without losing type-specific precision."""
    if value is None:
        raise ValueError("A null value has no key representation.")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def result_value(value: Value) -> schemas.Scalar | None:
    if isinstance(value, (date, Decimal)) or (isinstance(value, int) and abs(value) > 2**53):
        return string_value(value)
    return value
