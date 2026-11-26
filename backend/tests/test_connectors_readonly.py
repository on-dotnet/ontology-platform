"""The read-only red line at the connection layer (spec 003, 5.3 and section 15).

Two independent barriers: the platform only sends SELECTs it renders itself, and every
connection is read-only (the session default and an explicit READ ONLY transaction), with
timeouts, a row limit and cancellation.
"""

import asyncio
import dataclasses
import inspect
import time
from typing import Any, get_type_hints

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors import connection, service, statements
from ontology_platform.modules.connectors.connection import APPLICATION_NAME, connect
from ontology_platform.modules.connectors.errors import (
    ConnectorError,
    QueryTimeoutError,
    SourceBusyError,
)
from ontology_platform.modules.connectors.statements import (
    ColumnRef,
    Condition,
    Join,
    SelectQuery,
    SortKey,
    TableRef,
)
from test_connectors_support import (
    add_source,
    admin_rows,
    cache_table,
    configure,
    external_statements,
    reader_params,
    scratch_fixture,  # noqa: F401  (registers the fixture)
    writer_params,
)

WRITES = [
    "INSERT INTO mes.casting_sequence (cast_no) VALUES ('OP-TEST')",
    "UPDATE mes.heat SET site_id = site_id",
    "DELETE FROM mes.surface_defect",
    "TRUNCATE mes.surface_defect",
    "CREATE TABLE mes.op_intruder (id int)",
    "DROP TABLE mes.surface_defect",
    "ALTER TABLE mes.heat ADD COLUMN op_intruder int",
    "CREATE SCHEMA op_intruder",
]


def _counts(source: ExternalSource) -> dict[str, int]:
    tables = admin_rows(
        source,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'mes' AND c.relkind = 'r' ORDER BY 1",
    )
    counts = {}
    for (name,) in tables:
        [(count,)] = admin_rows(source, f'SELECT count(*) FROM mes."{name}"')  # noqa: S608
        counts[name] = count
    return counts


# ---------- ① no way in for SQL text ----------


def test_the_public_interface_takes_no_sql_text() -> None:
    suspicious = {"sql", "statement", "raw", "text", "clause", "fragment", "expression"}
    for module in (service, connection):
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or function.__module__ != module.__name__:
                continue
            hints = get_type_hints(function)
            for parameter in inspect.signature(function).parameters:
                assert parameter not in suspicious, f"{module.__name__}.{name}({parameter})"
                if parameter == "query":
                    assert hints[parameter] is SelectQuery


def test_select_query_has_only_structured_fields() -> None:
    fields = {
        cls.__name__: {f.name for f in dataclasses.fields(cls)}
        for cls in (SelectQuery, TableRef, ColumnRef, Condition, SortKey, Join)
    }
    assert fields == {
        "SelectQuery": {
            "data_source_id",
            "table",
            "columns",
            "join",
            "where",
            "order_by",
            "after",
            "limit",
        },
        "TableRef": {"schema", "name"},
        "ColumnRef": {"name", "side"},
        "Condition": {"column", "operator", "value"},
        "SortKey": {"column", "descending"},
        "Join": {"table", "on"},
    }
    for cls in (SelectQuery, TableRef, ColumnRef, Condition, SortKey, Join):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]
    assert statements.Operator.__args__ == (  # type: ignore[attr-defined]
        "eq",
        "ne",
        "lt",
        "le",
        "gt",
        "ge",
        "contains",
        "starts_with",
        "in",
        "is_null",
        "not_null",
    )


# ---------- ② even an account that may write cannot ----------


@pytest.mark.parametrize("statement", WRITES)
async def test_writes_fail_on_a_connector_connection(
    db: AsyncSession, external_source: ExternalSource, statement: str
) -> None:
    before = _counts(external_source)

    with pytest.raises(ConnectorError) as raised:
        async with connect(db, writer_params(external_source)) as conn:
            await conn.execute(text(statement))

    assert raised.value.sqlstate == "25006"  # read_only_sql_transaction
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__
    assert _counts(external_source) == before
    assert admin_rows(
        external_source, "SELECT count(*) FROM pg_namespace WHERE nspname = 'op_intruder'"
    ) == [(0,)]


async def test_both_barriers_are_in_place(
    db: AsyncSession, external_source: ExternalSource
) -> None:
    async with connect(db, writer_params(external_source)) as conn:
        default = (await conn.execute(text("SHOW default_transaction_read_only"))).scalar()
        current = (await conn.execute(text("SHOW transaction_read_only"))).scalar()
        driver = (await conn.get_raw_connection()).driver_connection
        assert isinstance(driver, psycopg.AsyncConnection)
        read_only = driver.read_only

    assert default == "on"  # barrier one: the session default
    assert current == "on"
    assert read_only is True  # barrier two: every transaction is BEGIN READ ONLY


async def _delete_with(db: AsyncSession, source: ExternalSource) -> ConnectorError:
    with pytest.raises(ConnectorError) as raised:
        async with connect(db, writer_params(source)) as conn:
            await conn.execute(text("DELETE FROM mes.surface_defect"))
    return raised.value


async def test_the_read_only_transaction_holds_without_the_session_default(
    db: AsyncSession, external_source: ExternalSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    options = connection._options
    monkeypatch.setattr(
        connection,
        "_options",
        lambda settings: options(settings).replace(
            "default_transaction_read_only=on", "default_transaction_read_only=off"
        ),
    )
    before = _counts(external_source)

    assert (await _delete_with(db, external_source)).sqlstate == "25006"
    assert _counts(external_source) == before


async def test_the_session_default_holds_without_the_read_only_transaction(
    db: AsyncSession, external_source: ExternalSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def keep_default(self: psycopg.AsyncConnection[Any], value: bool | None) -> None:
        return None

    monkeypatch.setattr(psycopg.AsyncConnection, "set_read_only", keep_default)
    before = _counts(external_source)

    assert (await _delete_with(db, external_source)).sqlstate == "25006"
    assert _counts(external_source) == before


# ---------- ③ a whole flow sends nothing but SELECTs ----------


async def test_a_flow_sends_only_selects(db: AsyncSession, external_source: ExternalSource) -> None:
    row = await add_source(db, external_source, allow_samples=True)
    for table in ("heat", "casting_sequence"):
        await cache_table(db, row.id, external_source, "mes", table)

    with external_statements() as seen:
        assert (await connection.test_connection(db, reader_params(external_source))).ok
        tables = await connection.read_catalog(db, reader_params(external_source), ["mes"])
        await service.sample_values(db, row.id, TableRef("mes", "heat"), ("heat_no", "site_id"))
        listed = await service.select(
            db,
            SelectQuery(
                row.id,
                TableRef("mes", "heat"),
                (ColumnRef("heat_no"), ColumnRef("site_id")),
                where=(Condition(ColumnRef("site_id"), "not_null"),),
                order_by=(SortKey(ColumnRef("heat_no")),),
                limit=5,
            ),
        )
        first = listed.rows[0][0]
        await service.select(
            db,
            SelectQuery(
                row.id,
                TableRef("mes", "heat"),
                (ColumnRef("heat_no"),),
                where=(Condition(ColumnRef("heat_no"), "eq", first),),
            ),
        )
        await service.select(
            db,
            SelectQuery(
                row.id,
                TableRef("mes", "heat"),
                (ColumnRef("cast_no", "joined"),),
                join=Join(TableRef("mes", "casting_sequence"), (("cast_no", "cast_no"),)),
                where=(Condition(ColumnRef("heat_no"), "eq", first),),
            ),
        )

    assert tables
    assert len(seen) > 6
    kinds = {statement.split(None, 1)[0].upper() for statement, _ in seen}
    assert kinds <= {"SELECT", "SHOW"}, [
        s for s, _ in seen if not s.lstrip().upper().startswith(("SELECT", "SHOW"))
    ]


# ---------- ④ filter values are values ----------


@pytest.mark.parametrize(
    ("operator", "value"),
    [
        ("eq", "x'; DROP TABLE mes.surface_defect; --"),
        ("eq", "' OR '1'='1"),
        ("contains", "%"),
        ("contains", "_"),
        ("starts_with", "' OR 1=1 /*"),
        ("in", ("a'); DELETE FROM mes.heat; --", "/* */")),
    ],
)
async def test_sql_in_filter_values_is_compared_literally(
    db: AsyncSession, external_source: ExternalSource, operator: str, value: Any
) -> None:
    row = await add_source(db, external_source)
    await cache_table(db, row.id, external_source, "mes", "heat")
    before = _counts(external_source)

    result = await service.select(
        db,
        SelectQuery(
            row.id,
            TableRef("mes", "heat"),
            (ColumnRef("heat_no"),),
            where=(Condition(ColumnRef("heat_no"), operator, value),),  # type: ignore[arg-type]
        ),
    )

    assert result.rows == ()
    assert _counts(external_source) == before


# ---------- ⑥ timeouts and cancelling ----------


@pytest.fixture
def slow_view(external_source: ExternalSource, scratch: str) -> str:
    """The schema of a view whose every read takes 30 seconds."""
    admin_rows(
        external_source,
        f"CREATE VIEW {scratch}.slow AS SELECT 1 AS x FROM pg_sleep(30);"  # noqa: S608
        f'GRANT SELECT ON {scratch}.slow TO "{external_source.reader}"',
    )
    return scratch


async def _active(source: ExternalSource) -> list[tuple[Any, ...]]:
    return admin_rows(
        source,
        "SELECT pid FROM pg_stat_activity WHERE application_name = %s AND state = 'active' "
        "AND datname = current_database() AND query LIKE '%%op_test_%%'",
        APPLICATION_NAME,
    )


async def test_a_statement_past_the_timeout_is_cancelled(
    db: AsyncSession,
    external_source: ExternalSource,
    slow_view: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch, query_timeout_seconds=1)
    row = await add_source(db, external_source)
    await cache_table(db, row.id, external_source, slow_view, "slow")
    started = time.monotonic()

    with pytest.raises(QueryTimeoutError):
        await service.select(
            db, SelectQuery(row.id, TableRef(slow_view, "slow"), (ColumnRef("x"),))
        )

    assert time.monotonic() - started < 10
    assert await _active(external_source) == []


async def test_cancelling_the_call_cancels_the_statement(
    db: AsyncSession, external_source: ExternalSource, slow_view: str
) -> None:
    row = await add_source(db, external_source)
    await cache_table(db, row.id, external_source, slow_view, "slow")
    query = SelectQuery(row.id, TableRef(slow_view, "slow"), (ColumnRef("x"),))
    task = asyncio.create_task(service.select(db, query))
    for _ in range(100):
        if await _active(external_source):
            break
        await asyncio.sleep(0.1)
    assert await _active(external_source), "the statement never started"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    for _ in range(50):
        if not await _active(external_source):
            break
        await asyncio.sleep(0.1)
    assert await _active(external_source) == []


async def test_more_than_four_statements_per_source_wait_then_get_busy(
    app: Any, external_source: ExternalSource, slow_view: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(connection, "QUEUE_SECONDS", 0.5)
    factory = app.state.session_factory
    async with factory() as setup:
        row = await add_source(setup, external_source)
        await cache_table(setup, row.id, external_source, slow_view, "slow")
    query = SelectQuery(row.id, TableRef(slow_view, "slow"), (ColumnRef("x"),))

    async def run() -> Any:
        async with factory() as db:
            return await service.select(db, query)

    running = [asyncio.create_task(run()) for _ in range(connection.MAX_CONCURRENT)]
    try:
        for _ in range(100):
            if len(await _active(external_source)) == connection.MAX_CONCURRENT:
                break
            await asyncio.sleep(0.1)
        with pytest.raises(SourceBusyError):
            await run()
    finally:
        for task in running:
            task.cancel()
        await asyncio.gather(*running, return_exceptions=True)


# ---------- ⑦ the row limit ----------


async def test_results_stop_at_the_row_limit(
    db: AsyncSession, external_source: ExternalSource, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=5)
    row = await add_source(db, external_source)
    await cache_table(db, row.id, external_source, "mes", "slab")
    [(total,)] = admin_rows(external_source, "SELECT count(*) FROM mes.slab")
    assert total > 5

    with external_statements() as seen:
        result = await service.select(
            db, SelectQuery(row.id, TableRef("mes", "slab"), (ColumnRef("slab_no"),), limit=50)
        )

    assert len(result.rows) == 5
    assert result.has_more
    [(statement, parameters)] = [item for item in seen if "slab" in item[0]]
    assert "LIMIT" in statement.upper()
    assert 6 in dict(parameters).values()


async def test_long_text_is_cut_and_marked(
    db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    admin_rows(
        external_source,
        f"CREATE TABLE {scratch}.long (id int PRIMARY KEY, body text);"  # noqa: S608
        f"INSERT INTO {scratch}.long VALUES (1, repeat('炉', 2500)), (2, 'short');"
        f'GRANT SELECT ON {scratch}.long TO "{external_source.reader}"',
    )
    row = await add_source(db, external_source)
    await cache_table(db, row.id, external_source, scratch, "long")

    result = await service.select(
        db,
        SelectQuery(
            row.id,
            TableRef(scratch, "long"),
            (ColumnRef("id"), ColumnRef("body")),
            order_by=(SortKey(ColumnRef("id")),),
        ),
    )

    assert result.rows == (
        (1, "炉" * connection.TEXT_LIMIT),
        (2, "short"),
    )
    assert result.truncated == frozenset({(0, 1)})
