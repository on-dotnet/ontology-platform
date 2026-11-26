"""Rendering and running `SelectQuery` (spec 003, 5.1, 5.5 and section 7, connector side)."""

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors import service
from ontology_platform.modules.connectors.errors import (
    InvalidValueError,
    SourceDisabledError,
    SourceMismatchError,
)
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.connectors.statements import (
    ColumnRef,
    Condition,
    Join,
    SelectQuery,
    SortKey,
    TableRef,
    Value,
)
from test_connectors_support import add_source, admin_rows, cache_table


async def _source(db: AsyncSession, source: ExternalSource, *tables: str, **kw: Any) -> DataSource:
    row = await add_source(db, source, **kw)
    for name in tables:
        await cache_table(db, row.id, source, "mes", name)
    return row


async def test_uuid_keys_bind_as_uuid(db: AsyncSession, external_source: ExternalSource) -> None:
    row = await _source(db, external_source, "quality_inspection")
    [(wanted,)] = admin_rows(
        external_source, "SELECT inspection_id FROM mes.quality_inspection ORDER BY 1 LIMIT 1"
    )
    assert isinstance(wanted, UUID)

    def by_key(value: Value) -> SelectQuery:
        return SelectQuery(
            row.id,
            TableRef("mes", "quality_inspection"),
            (ColumnRef("inspection_id"),),
            where=(Condition(ColumnRef("inspection_id"), "eq", value),),
        )

    found = await service.select(db, by_key(str(wanted)))
    with pytest.raises(InvalidValueError) as raised:
        await service.select(db, by_key("not-a-uuid"))

    assert found.rows == ((str(wanted),),)
    assert raised.value.sqlstate == "22P02"


async def test_enum_columns_bind_as_their_enum(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    row = await _source(db, external_source, "coil")
    expected = dict(
        admin_rows(external_source, "SELECT status::text, count(*) FROM mes.coil GROUP BY 1")
    )
    status = next(iter(expected))

    def where(*conditions: Condition) -> SelectQuery:
        return SelectQuery(
            row.id, TableRef("mes", "coil"), (ColumnRef("coil_no"), ColumnRef("status")),
            where=conditions, limit=1000,
        )

    equal = await service.select(db, where(Condition(ColumnRef("status"), "eq", status)))
    among = await service.select(
        db, where(Condition(ColumnRef("status"), "in", tuple(expected)))
    )
    other = await service.select(db, where(Condition(ColumnRef("status"), "ne", status)))
    with pytest.raises(InvalidValueError) as raised:
        await service.select(db, where(Condition(ColumnRef("status"), "eq", "no-such-status")))

    assert len(equal.rows) == expected[status]
    assert {value for _, value in equal.rows} == {status}
    assert len(among.rows) == sum(expected.values())
    assert len(other.rows) == sum(expected.values()) - expected[status]
    assert raised.value.sqlstate == "22P02"
    assert raised.value.sqlstate.startswith("22")


async def test_values_of_the_wrong_shape_are_invalid_values(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    row = await _source(db, external_source, "slab")

    with pytest.raises(InvalidValueError) as raised:
        await service.select(
            db,
            SelectQuery(
                row.id,
                TableRef("mes", "slab"),
                (ColumnRef("slab_no"),),
                where=(Condition(ColumnRef("weight_t"), "gt", "heavy"),),
            ),
        )

    assert raised.value.sqlstate is not None
    assert raised.value.sqlstate.startswith("22")


@pytest.mark.parametrize("descending", [False, True])
async def test_keyset_pages_cover_every_row_once_with_nulls(
    db: AsyncSession, external_source: ExternalSource, descending: bool
) -> None:
    row = await _source(db, external_source, "coil")
    direction = "DESC NULLS FIRST" if descending else "ASC NULLS LAST"
    expected = admin_rows(
        external_source,
        f"SELECT weight_t, coil_no FROM mes.coil ORDER BY weight_t {direction}, coil_no",
    )
    assert any(weight is None for weight, _ in expected), "the sample needs a NULL weight"
    order = (SortKey(ColumnRef("weight_t"), descending), SortKey(ColumnRef("coil_no")))
    seen: list[tuple[Value, ...]] = []
    after: tuple[Value, ...] | None = None
    while True:
        page = await service.select(
            db,
            SelectQuery(
                row.id,
                TableRef("mes", "coil"),
                (ColumnRef("weight_t"), ColumnRef("coil_no")),
                order_by=order,
                after=after,
                limit=7,
            ),
        )
        seen.extend(page.rows)
        if not page.has_more:
            break
        after = page.rows[-1]

    assert seen == [(weight, coil) for weight, coil in expected]
    assert all(isinstance(weight, Decimal) for weight, _ in seen if weight is not None)


async def test_a_join_reads_the_other_table_once(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    row = await _source(db, external_source, "heat", "casting_sequence")
    expected = admin_rows(
        external_source,
        "SELECT h.heat_no, c.cast_no, c.site_id FROM mes.heat h "
        "JOIN mes.casting_sequence c ON c.cast_no = h.cast_no ORDER BY h.heat_no",
    )

    result = await service.select(
        db,
        SelectQuery(
            row.id,
            TableRef("mes", "heat"),
            (ColumnRef("heat_no"), ColumnRef("cast_no", "joined"), ColumnRef("site_id", "joined")),
            join=Join(TableRef("mes", "casting_sequence"), (("cast_no", "cast_no"),)),
            order_by=(SortKey(ColumnRef("heat_no")),),
            limit=1000,
        ),
    )

    assert list(result.rows) == expected


@pytest.mark.parametrize(
    ("operator", "value"),
    [("starts_with", "H"), ("contains", "0"), ("is_null", None), ("not_null", None)],
)
async def test_text_and_null_operators_match_the_database(
    db: AsyncSession, external_source: ExternalSource, operator: str, value: Value
) -> None:
    row = await _source(db, external_source, "heat")
    predicate = {
        "starts_with": "heat_no LIKE 'H%%'",
        "contains": "heat_no LIKE '%%0%%'",
        "is_null": "cast_no IS NULL",
        "not_null": "cast_no IS NOT NULL",
    }[operator]
    column = "heat_no" if operator in ("starts_with", "contains") else "cast_no"
    expected = admin_rows(
        external_source, f"SELECT heat_no FROM mes.heat WHERE {predicate} ORDER BY 1"
    )

    result = await service.select(
        db,
        SelectQuery(
            row.id,
            TableRef("mes", "heat"),
            (ColumnRef("heat_no"),),
            where=(Condition(ColumnRef(column), operator, value),),  # type: ignore[arg-type]
            order_by=(SortKey(ColumnRef("heat_no")),),
            limit=1000,
        ),
    )

    assert list(result.rows) == expected


async def test_columns_missing_from_the_cache_or_the_source_are_a_mismatch(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    row = await _source(db, external_source, "heat")
    uncached = SelectQuery(row.id, TableRef("mes", "coil"), (ColumnRef("coil_no"),))
    unknown_column = SelectQuery(row.id, TableRef("mes", "heat"), (ColumnRef("no_such"),))
    # The cache says the table is there, the database no longer has it.
    admin_rows(
        external_source,
        "CREATE TABLE IF NOT EXISTS mes.op_test_gone (id int);"
        f'GRANT SELECT ON mes.op_test_gone TO "{external_source.reader}"',
    )
    await cache_table(db, row.id, external_source, "mes", "op_test_gone")
    admin_rows(external_source, "DROP TABLE mes.op_test_gone")
    dropped = SelectQuery(row.id, TableRef("mes", "op_test_gone"), (ColumnRef("id"),))

    for query in (uncached, unknown_column, dropped):
        with pytest.raises(SourceMismatchError):
            await service.select(db, query)


async def test_samples_need_the_switch_and_are_few_and_short(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    closed = await _source(db, external_source, "heat")
    opened = await _source(db, external_source, "heat", allow_samples=True)

    with pytest.raises(SourceDisabledError):
        await service.sample_values(db, closed.id, TableRef("mes", "heat"), ("heat_no",))
    samples = await service.sample_values(
        db, opened.id, TableRef("mes", "heat"), ("heat_no", "site_id")
    )

    assert set(samples) == {"heat_no", "site_id"}
    assert len(samples["heat_no"]) == 5
    assert len(set(samples["heat_no"])) == 5
    sites = {site for (site,) in admin_rows(external_source, "SELECT site_id FROM mes.heat")}
    assert set(samples["site_id"]) <= sites
    assert 1 <= len(samples["site_id"]) <= 5


async def test_archived_sources_are_disabled(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    row = await _source(db, external_source, "heat")
    row.status, row.secret = "archived", None
    await db.commit()

    with pytest.raises(SourceDisabledError):
        await service.select(db, SelectQuery(row.id, TableRef("mes", "heat"), (ColumnRef("heat_no"),)))
