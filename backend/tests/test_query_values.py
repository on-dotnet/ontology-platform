from datetime import UTC, date, datetime
from decimal import Decimal
from typing import get_args
from uuid import UUID

import pytest

from ontology_platform.errors import AppError
from ontology_platform.modules.connectors.models import ColumnFamily
from ontology_platform.modules.connectors.schemas import CatalogColumn
from ontology_platform.modules.connectors.statements import ColumnRef, Condition, Operator, Value
from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.modules.query import schemas, values


def column(family: ColumnFamily, source: str) -> CatalogColumn:
    return CatalogColumn(
        name="batch_value", family=family, type=source, nullable=True, position=1, comment=None
    )


TEXT = column("string", "character varying(80)")
FIXED = column("string", "character(2)")
INTEGER = column("integer", "bigint")
NUMERIC = column("decimal", "numeric")
BOOLEAN = column("boolean", "boolean")
DATE = column("date", "date")
TIMESTAMP = column("dateTime", "timestamp with time zone")
IDENTIFIER = column("opaque", "UUID")
ENUM = column("opaque", "mes.grade")
PROPERTY = UUID(int=13)
EQUALITY = {"eq", "ne", "isNull", "notNull"}
ORDERED = EQUALITY | {"in", "lt", "le", "gt", "ge"}
LITERAL = "炉次 '%_/;"
PRECISE = "12345678901234567890.00100"
LOCAL_TIME = "2024-02-29T01:02:03"
OFFSET_TIME = "2024-02-29T01:02:03.010200+05:30"
COMPATIBLE: dict[tuple[Datatype, ColumnFamily], set[str]] = {
    ("string", "string"): ORDERED | {"contains", "startsWith"},
    ("string", "opaque"): EQUALITY | {"in"},
    ("integer", "integer"): ORDERED,
    ("decimal", "decimal"): ORDERED,
    ("decimal", "integer"): ORDERED,
    ("boolean", "boolean"): EQUALITY,
    ("date", "date"): ORDERED,
    ("dateTime", "dateTime"): ORDERED,
    ("dateTime", "date"): ORDERED,
}


@pytest.mark.parametrize("datatype", get_args(Datatype))
@pytest.mark.parametrize("family", get_args(ColumnFamily))
def test_ops_follow_property_and_column(datatype: Datatype, family: ColumnFamily) -> None:
    expected = COMPATIBLE.get((datatype, family), set())
    actual = values.ops(datatype, family)
    assert set(actual) == expected
    assert len(actual) == len(expected)


@pytest.mark.parametrize(
    ("op", "raw", "operator", "parameter"),
    [
        ("eq", "", "eq", ""),
        ("ne", LITERAL, "ne", LITERAL),
        ("lt", "B", "lt", "B"),
        ("le", "C", "le", "C"),
        ("gt", "D", "gt", "D"),
        ("ge", "E", "ge", "E"),
        ("contains", LITERAL, "contains", LITERAL),
        ("startsWith", LITERAL, "starts_with", LITERAL),
        ("in", ["A", "B"], "in", ("A", "B")),
        ("isNull", None, "is_null", None),
        ("notNull", None, "not_null", None),
    ],
)
def test_condition_targets_catalog_column_with_bound_value(
    op: schemas.FilterOp,
    raw: schemas.FilterValue | list[schemas.FilterValue] | None,
    operator: Operator,
    parameter: Value | tuple[Value, ...],
) -> None:
    item = schemas.Filter(property_id=PROPERTY, op=op, value=raw)
    assert values.condition(item, TEXT, "string") == Condition(
        ColumnRef(TEXT.name), operator, parameter
    )


@pytest.mark.parametrize("size", [0, 100])
def test_in_converts_every_value_at_both_limits(size: int) -> None:
    item = schemas.Filter(property_id=PROPERTY, op="in", value=[str(i) for i in range(size)])
    assert values.condition(item, INTEGER, "decimal") == Condition(
        ColumnRef(INTEGER.name), "in", tuple(range(size))
    )


@pytest.mark.parametrize(
    ("col", "datatype", "raw", "parameter"),
    [
        (INTEGER, "decimal", "-17", -17),
        (NUMERIC, "decimal", "0.1234567890123456789", Decimal("0.1234567890123456789")),
        (DATE, "dateTime", "2024-02-29", date(2024, 2, 29)),
        (TIMESTAMP, "dateTime", OFFSET_TIME, datetime.fromisoformat(OFFSET_TIME)),
        (BOOLEAN, "boolean", "false", False),
        (ENUM, "string", "uncached label", "uncached label"),
    ],
)
def test_scalar_condition_binds_the_column_type(
    col: CatalogColumn, datatype: Datatype, raw: str, parameter: Value
) -> None:
    item = schemas.Filter(property_id=PROPERTY, op="eq", value=raw)
    predicate = values.condition(item, col, datatype)
    assert predicate == Condition(ColumnRef(col.name), "eq", parameter)
    assert type(predicate.value) is type(parameter)


@pytest.mark.parametrize(
    ("op", "raw", "col", "datatype"),
    [
        ("eq", None, TEXT, "string"),
        ("le", ["A"], TEXT, "string"),
        ("in", "A", TEXT, "string"),
        ("in", ["A"] * 101, TEXT, "string"),
        ("in", ["42", "bad"], INTEGER, "integer"),
        ("eq", "ABX", FIXED, "string"),
        ("in", ["AB", "AB "], FIXED, "string"),
        ("ge", 32768, column("integer", "smallint"), "decimal"),
        ("notNull", [], TEXT, "string"),
        ("isNull", False, BOOLEAN, "boolean"),
        ("in", [True], BOOLEAN, "boolean"),
        ("gt", "A", ENUM, "string"),
        ("startsWith", "ab", IDENTIFIER, "string"),
        ("contains", "2", NUMERIC, "decimal"),
        ("eq", "2024-02-30", DATE, "dateTime"),
        ("eq", "bad-uuid", IDENTIFIER, "string"),
        ("isNull", None, INTEGER, "string"),
    ],
)
def test_invalid_condition_raises_query_error(
    op: schemas.FilterOp,
    raw: schemas.FilterValue | list[schemas.FilterValue] | None,
    col: CatalogColumn,
    datatype: Datatype,
) -> None:
    item = schemas.Filter(property_id=PROPERTY, op=op, value=raw)
    with pytest.raises(AppError) as exc:
        values.condition(item, col, datatype)
    assert (exc.value.status, exc.value.code, exc.value.detail) == (
        422,
        "query.invalid_filter",
        "The filter is invalid.",
    )


@pytest.mark.parametrize(
    ("col", "raw", "expected"),
    [
        (TEXT, LITERAL, LITERAL),
        (FIXED, "炉🏭", "炉🏭"),
        (FIXED, "炉\ud83c\udfed", "炉🏭"),
        (FIXED, "A ", "A "),
        (column("string", "character varying(2)"), "ABX", "ABX"),
        (ENUM, "an uncached label", "an uncached label"),
        (
            IDENTIFIER,
            "A0B1C2D3-0000-0000-0000-000000000001",
            "a0b1c2d3-0000-0000-0000-000000000001",
        ),
        (INTEGER, "-42", -42),
        (INTEGER, 0, 0),
        (NUMERIC, 12, Decimal("12")),
        (NUMERIC, 0.1, Decimal("0.1")),
        (NUMERIC, "-1.200e-7", Decimal("-1.200e-7")),
        (BOOLEAN, True, True),
        (BOOLEAN, "false", False),
        (DATE, "2024-02-29", date(2024, 2, 29)),
        (TIMESTAMP, "2024-02-29T01:02:03Z", datetime(2024, 2, 29, 1, 2, 3, tzinfo=UTC)),
        (TIMESTAMP, "2024-02-29 01:02", datetime.fromisoformat("2024-02-29T01:02:00")),
        (TIMESTAMP, "20240229T010203+0530", datetime.fromisoformat("2024-02-29T01:02:03+05:30")),
    ],
)
def test_parse_produces_connector_parameter(
    col: CatalogColumn, raw: schemas.FilterValue, expected: Value
) -> None:
    actual = values.parse_value(raw, col)
    assert actual == expected
    assert type(actual) is type(expected)


@pytest.mark.parametrize(
    ("col", "raw"),
    [
        (TEXT, 5),
        (TEXT, "embedded\x00nul"),
        (TEXT, "prefix\ud800suffix"),
        (ENUM, "label\udfff"),
        (FIXED, "炉🏭次"),
        (FIXED, "AB "),
        (ENUM, False),
        (IDENTIFIER, "wrong"),
        (IDENTIFIER, "a0b1c2d3--0000-0000-0000-000000000001"),
        (INTEGER, True),
        (INTEGER, 3.5),
        (INTEGER, "3.5"),
        (INTEGER, "1_000"),
        (NUMERIC, False),
        (NUMERIC, ""),
        (NUMERIC, "1.2.3"),
        (BOOLEAN, 1),
        (BOOLEAN, "sometimes"),
        (DATE, "20240229"),
        (DATE, "2023-02-29"),
        (DATE, "2024-02-29T00:00:00"),
        (TIMESTAMP, "2024-02-29"),
        (TIMESTAMP, "2024-02-29x12:34:56"),
        (TIMESTAMP, "2024-02-29T25:00:00"),
        (TIMESTAMP, "2024-02-29T01:02:03+00:60"),
        (TIMESTAMP, "2024-02-29T01:02:03-00:00:60"),
        (TIMESTAMP, "2024-02-29T01:02:03.1234567Z"),
        (TEXT, None),
        (column("other", "jsonb"), "{}"),
    ],
)
def test_invalid_key_or_cursor_value_raises_value_error(col: CatalogColumn, raw: object) -> None:
    with pytest.raises(ValueError, match=r".+"):
        values.parse_value(raw, col)


@pytest.mark.parametrize(
    ("source", "minimum", "maximum"),
    [
        ("smallint", -32768, 32767),
        ("integer", -2147483648, 2147483647),
        ("bigint", -9223372036854775808, 9223372036854775807),
    ],
)
@pytest.mark.parametrize("as_string", [False, True])
def test_integer_parameters_respect_source_range(
    source: str, minimum: int, maximum: int, as_string: bool
) -> None:
    col = column("integer", source)
    for endpoint in (minimum, maximum):
        assert values.parse_value(str(endpoint) if as_string else endpoint, col) == endpoint
    for outside in (minimum - 1, maximum + 1):
        with pytest.raises(ValueError, match=r".+"):
            values.parse_value(str(outside) if as_string else outside, col)


@pytest.mark.parametrize(
    ("col", "scalar", "wire", "result"),
    [
        (TEXT, "  热  ", "  热  ", "  热  "),
        (ENUM, "A", "A", "A"),
        (IDENTIFIER, str(PROPERTY), str(PROPERTY), str(PROPERTY)),
        (BOOLEAN, True, "true", True),
        (BOOLEAN, False, "false", False),
        (INTEGER, 2**53, "9007199254740992", 2**53),
        (INTEGER, -(2**53), "-9007199254740992", -(2**53)),
        (INTEGER, 2**53 + 1, "9007199254740993", "9007199254740993"),
        (INTEGER, -(2**53) - 1, "-9007199254740993", "-9007199254740993"),
        (NUMERIC, Decimal(PRECISE), PRECISE, PRECISE),
        (DATE, date(2024, 2, 29), "2024-02-29", "2024-02-29"),
        (TIMESTAMP, datetime.fromisoformat(OFFSET_TIME), OFFSET_TIME, OFFSET_TIME),
        (TIMESTAMP, datetime.fromisoformat(LOCAL_TIME), LOCAL_TIME, LOCAL_TIME),
    ],
)
def test_result_and_key_round_trip(
    col: CatalogColumn, scalar: str | int | Decimal | date, wire: str, result: schemas.Scalar
) -> None:
    encoded = values.string_value(scalar)
    assert encoded == wire
    decoded = values.parse_value(encoded, col)
    assert decoded == scalar
    assert type(decoded) is type(scalar)
    actual = values.result_value(scalar)
    assert actual == result
    assert type(actual) is type(result)


def test_null_result_stays_null() -> None:
    assert values.result_value(None) is None


@pytest.mark.parametrize("wire", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_decimal_cursor_round_trip(wire: str) -> None:
    encoded = values.string_value(Decimal(wire))
    assert encoded == wire
    decoded = values.parse_value(encoded, NUMERIC)
    assert isinstance(decoded, Decimal)
    assert decoded.as_tuple() == Decimal(wire).as_tuple()
