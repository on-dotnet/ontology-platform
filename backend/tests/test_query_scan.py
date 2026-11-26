import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.errors import AppError
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.statements import Rows, SelectQuery
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.query import cursor, schemas, service
from query_path_support import demo_path, qa_steel_fixture  # noqa: F401
from test_connectors_support import (
    admin_rows,
    cache_table,
    configure,
    scratch_fixture,  # noqa: F401
)
from test_query_paging import SteelObjects, steel_objects_fixture  # noqa: F401
from test_query_rows import published_table
from test_query_support import make_catalog, publish_bindings


async def test_scan_within_batches_pages_filters_and_projection(
    db: AsyncSession, qa_steel: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=3, metric_rows_max=8)
    path = demo_path(qa_steel)
    grade = UUID(qa_steel.ids["steelGrade"])
    numbers = [*range(101, 197), 1, 2, 3, 4, 5, 6, 7, 8, 20, 1]
    keys = tuple(cursor.encode_key([f"H2401{i:03}"]) for i in numbers)
    within = schemas.KeySet(path.type_id, keys)
    result = await service.scan(
        db,
        qa_steel.ontology.id,
        path.type_id,
        path.filters,
        property_ids=[grade],
        within=within,
        max_rows=8,
    )
    assert {row.key for row in result.rows} == {
        cursor.encode_key([f"H2401{i:03}"]) for i in range(1, 9)
    }
    assert len(result.rows) == 8
    assert all(row.values == {grade: "Q235B"} for row in result.rows)
    assert str(result.release.id) == qa_steel.release["id"]
    [step] = result.steps
    assert (step.statements, step.rows, step.truncated) == (4, 8, False)
    empty = await service.scan(
        db,
        qa_steel.ontology.id,
        path.type_id,
        [],
        property_ids=[],
        within=schemas.KeySet(path.type_id, ()),
        max_rows=1,
    )
    assert empty.rows == ()
    assert empty.steps[0].statements == 0


async def test_scan_exact_composite_within(
    db: AsyncSession, steel_objects: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=1)
    steel = steel_objects
    subject = UUID(steel.ids["Participation"])
    keys = [
        cursor.encode_key([slab, event])
        for slab, event in [
            ("S240100303", "R2401004"),
            ("S240100401", "R2401005"),
        ]
    ]
    result = await service.scan(
        db,
        steel.ontology.id,
        subject,
        [],
        property_ids=[],
        within=schemas.KeySet(subject, tuple(keys)),
        max_rows=2,
    )
    assert {row.key for row in result.rows} == set(keys)
    assert all(row.values == {} for row in result.rows)


async def test_scan_pages_have_independent_read_only_connections_and_timeout(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    scratch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = await make_catalog(client, db, external_source)
    admin_rows(
        external_source,
        f"""
        CREATE VIEW {scratch}.probe AS
          SELECT n::text AS coil_no, concat_ws('/', pg_backend_pid(),
                 current_setting('transaction_read_only'),
                 current_setting('statement_timeout')) AS status
          FROM generate_series(1, 3) n;
        GRANT SELECT ON {scratch}.probe TO "{external_source.reader}";
        """,  # noqa: S608
    )
    await cache_table(db, catalog.source.id, external_source, scratch, "probe")
    await publish_bindings(client, catalog, catalog.coil_bindings(scratch, "probe"))
    configure(monkeypatch, query_max_rows=1, query_timeout_seconds=2)
    result = await service.scan(
        db, catalog.ontology.id, catalog.coil.id, [], property_ids=[catalog.status.id], max_rows=3
    )
    pids = set()
    for row in result.rows:
        value = row.values[catalog.status.id]
        assert isinstance(value, str)
        pid, readonly, timeout = value.split("/")
        assert (readonly, timeout) == ("on", "2s")
        pids.add(pid)
    assert len(pids) == result.steps[0].statements == 3


async def test_scan_counts_rows_and_combines_metric_filter_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = published_table(monkeypatch)
    subject = model.types[0]
    note = subject.properties[0].property_id
    filters = [schemas.Filter(property_id=note, op="ne", value=str(i)) for i in range(20)]

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        assert [c.value for c in query.where] == [str(i) for i in range(20)]
        return Rows(((1,), (1,)), has_more=False)

    monkeypatch.setattr(connectors, "select", read)
    with pytest.raises(AppError) as caught:
        await service.scan(
            Mock(spec=AsyncSession),
            model.ontology_id,
            subject.type_id,
            filters,
            property_ids=[],
            max_rows=1,
        )
    assert caught.value.code == "query.too_many_rows"


@pytest.mark.parametrize(("cap", "requested"), [(17, 18), (18, 17)])
async def test_scan_row_caps(
    db: AsyncSession,
    qa_steel: SteelObjects,
    monkeypatch: pytest.MonkeyPatch,
    cap: int,
    requested: int,
) -> None:
    configure(monkeypatch, query_max_rows=4, metric_rows_max=cap)
    path = demo_path(qa_steel)
    with pytest.raises(AppError) as caught:
        await service.scan(
            db,
            qa_steel.ontology.id,
            path.type_id,
            path.filters,
            property_ids=[],
            max_rows=requested,
        )
    assert (caught.value.status, caught.value.code) == (422, "query.too_many_rows")


@pytest.mark.parametrize("scan", [False, True], ids=["traverse", "scan"])
async def test_release_changed_during_last_read(
    monkeypatch: pytest.MonkeyPatch, *, scan: bool
) -> None:
    model = published_table(monkeypatch)
    subject = model.types[0].type_id

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        updated = replace(model, release_id=uuid4(), version=model.version + 1)
        monkeypatch.setattr(bindings, "bound_model", AsyncMock(return_value=updated))
        return Rows((), has_more=False)

    monkeypatch.setattr(connectors, "select", read)
    db = Mock(spec=AsyncSession)
    call = (
        service.scan(db, model.ontology_id, subject, [], property_ids=[], max_rows=10)
        if scan
        else service.traverse(
            db, model.ontology_id, schemas.PathQuery(type_id=subject, filters=[], hops=[])
        )
    )
    with pytest.raises(AppError) as caught:
        await call
    assert (caught.value.status, caught.value.code) == (409, "query.release_changed")


async def test_question_budget_shared_by_traversal_and_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ontology_platform.modules.query.scan import query_budget

    model = published_table(monkeypatch)
    configure(monkeypatch, query_max_rows=1)
    calls = 0

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        nonlocal calls
        calls += 1
        row = tuple(calls if c.name == "id" else "note" for c in query.columns)
        return Rows((row,), has_more=calls < 199)

    monkeypatch.setattr(connectors, "select", read)
    db = Mock(spec=AsyncSession)
    subject = model.types[0].type_id
    path = schemas.PathQuery(type_id=subject, filters=[], hops=[])
    async with query_budget():
        assert len((await service.traverse_keys(db, model.ontology_id, path)).keys) == 199
        await service.scan(db, model.ontology_id, subject, [], property_ids=[], max_rows=1)
        with pytest.raises(AppError) as caught:
            await service.scan(db, model.ontology_id, subject, [], property_ids=[], max_rows=1)
        assert caught.value.code == "qa.too_many_queries"
    assert calls == 200
    await service.scan(db, model.ontology_id, subject, [], property_ids=[], max_rows=1)
    assert calls == 201


async def test_query_deadline_cancels_in_flight_read(monkeypatch: pytest.MonkeyPatch) -> None:
    from ontology_platform.modules.query import scan

    model = published_table(monkeypatch)
    assert scan.QUERY_SECONDS == 60
    monkeypatch.setattr(scan, "QUERY_SECONDS", 0.05)
    cancelled = asyncio.Event()

    async def read(db: AsyncSession, query: SelectQuery) -> Rows:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return Rows((), has_more=False)

    monkeypatch.setattr(connectors, "select", read)
    with pytest.raises(AppError) as caught:
        await service.scan(
            Mock(spec=AsyncSession),
            model.ontology_id,
            model.types[0].type_id,
            [],
            property_ids=[],
            max_rows=10,
        )
    assert (caught.value.status, caught.value.code) == (504, "query.timeout")
    assert cancelled.is_set()
