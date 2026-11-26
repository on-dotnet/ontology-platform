from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.errors import AppError
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.query import cursor, schemas, service
from query_path_support import demo_path, qa_steel_fixture  # noqa: F401
from support import csrf_headers
from test_connectors_support import (
    add_source,
    admin_rows,
    cache_table,
    configure,
    scratch_fixture,  # noqa: F401
)
from test_ontology_bindings_support import relation_binding, save, table, type_binding
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in
from test_query_paging import SteelObjects, steel_objects_fixture, through_table  # noqa: F401
from test_query_support import assert_problem


async def test_zero_hop_total_objects_and_all_keys(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=4)
    path = demo_path(qa_steel)
    path.hops = []
    path.limit = 2
    response = await client.post(
        f"{qa_steel.url}/traverse",
        json=path.model_dump(mode="json", by_alias=True),
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    result = schemas.PathResult.model_validate(response.json())
    expected = [cursor.encode_key([f"H2401{i:03}"]) for i in range(1, 19)]
    assert (result.total, result.truncated) == (18, True)
    assert [row.via for row in result.items] == [[key] for key in expected[:2]]
    assert (result.tail_type_id, result.tail_total, result.tail) == (None, 0, [])
    [step] = result.steps
    assert (step.rows, step.statements, step.type_label) == (18, 5, "炉次")
    assert step.conditions == ["钢种 = Q235B"]
    keys = await service.traverse_keys(db, qa_steel.ontology.id, path)
    assert keys == schemas.KeySet(path.type_id, tuple(expected))


async def test_five_hops_page_every_step_and_prune_uninspected_coils(
    db: AsyncSession, qa_steel: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=4)
    path = demo_path(qa_steel)
    walk = await service.traverse(db, qa_steel.ontology.id, path)
    assert walk.total == len(walk.items) == 39
    assert all(step.statements > 1 for step in walk.steps)
    assert len(walk.steps) == 6
    passed = UUID(qa_steel.ids["passed"])
    assert sum(row.values[passed] is False for row in walk.items) == 3
    uninspected = cursor.encode_key(["W240100102"])
    prefix = path.model_copy(update={"hops": path.hops[:-1]})
    assert uninspected in (await service.traverse_keys(db, qa_steel.ontology.id, prefix)).keys
    path.target = 4
    keys = await service.traverse_keys(db, qa_steel.ontology.id, path)
    assert set(keys.keys) == {row.via[4] for row in walk.items}
    assert uninspected not in keys.keys


async def test_filtered_middle_answers_tail_and_reverse(
    db: AsyncSession, qa_steel: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=3)
    steel = qa_steel
    path = demo_path(steel, failed=True)
    path.target = 4
    result = await service.traverse(db, steel.ontology.id, path)
    coils = {cursor.encode_key([v]) for v in ("W240101201", "W240101503")}
    assert result.type_id == UUID(steel.ids["Coil"])
    assert result.tail_type_id == UUID(steel.ids["QualityInspection"])
    assert (result.total, result.tail_total) == (2, 3)
    assert {r.key for r in result.items} == coils
    records = {
        cursor.encode_key([f"24010000-0000-4000-8000-000000000{suffix}"])
        for suffix in ("341", "342", "451")
    }
    assert {r.key for r in result.tail} == records
    for row in result.items + result.tail:
        assert len(row.via) == 6
        assert row.via[4] in coils
        assert row.via[5] in records
    for row in result.items:
        assert row.via == next(r.via for r in result.tail if r.via[4] == row.key)
    reverse = demo_path(steel, failed=True, reverse=True)
    reverse.target = 1
    backward = await service.traverse(db, steel.ontology.id, reverse)
    assert {r.key for r in backward.items} == coils
    assert all(r.via[1] == r.key and r.via[0] in records for r in backward.items)
    limited = await service.traverse(db, steel.ontology.id, path, limit=1)
    assert (len(limited.items), len(limited.tail), limited.total, limited.tail_total) == (
        1,
        1,
        2,
        3,
    )


@pytest.mark.parametrize("reverse", [False, True], ids=["slabs", "events"])
async def test_rolled_in_keeps_every_source_across_page_boundaries(
    db: AsyncSession,
    qa_steel: SteelObjects,
    external_source: ExternalSource,
    monkeypatch: pytest.MonkeyPatch,
    reverse: bool,
) -> None:
    configure(monkeypatch, query_max_rows=2)
    origin, target = ("RollingEvent", "Slab") if reverse else ("Slab", "RollingEvent")
    path = schemas.PathQuery(
        type_id=UUID(qa_steel.ids[origin]),
        filters=[],
        target=0,
        hops=[
            schemas.PathHop(
                relation_id=UUID(qa_steel.ids["rolledIn"]), direction="in" if reverse else "out"
            )
        ],
    )
    expected = admin_rows(external_source, "SELECT slab_no, rolling_id FROM mes.slab_rolling")
    pairs = {
        (cursor.encode_key([b]), cursor.encode_key([a]))
        if reverse
        else (cursor.encode_key([a]), cursor.encode_key([b]))
        for a, b in expected
    }
    result = await service.traverse(db, qa_steel.ontology.id, path, limit=200)
    assert result.tail_type_id == UUID(qa_steel.ids[target])
    assert {row.key for row in result.items} == {src for src, _ in pairs}
    assert {row.key for row in result.tail} == {dst for _, dst in pairs}
    assert all(tuple(row.via) in pairs for row in result.items + result.tail)


async def test_composite_origin_keys(
    db: AsyncSession, steel_objects: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, query_max_rows=1)
    steel = steel_objects
    rolling = "R2401005"
    path = schemas.PathQuery(
        type_id=UUID(steel.ids["Participation"]),
        target=0,
        filters=[schemas.Filter(property_id=UUID(steel.ids["rollingNo"]), op="eq", value=rolling)],
        hops=[schemas.PathHop(relation_id=UUID(steel.ids["event"]), direction="out")],
    )
    result = await service.traverse(db, steel.ontology.id, path)
    assert {row.key for row in result.items} == {
        cursor.encode_key([slab, rolling]) for slab in ("S240100303", "S240100401")
    }
    [event] = result.tail
    assert event.key == cursor.encode_key([rolling])
    assert all(r.via == [r.key, event.key] for r in result.items)


async def test_batch_join_same_column_names_pair_cap_and_lossy_key(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    scratch: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_rows(
        external_source,
        f"""
        SET search_path TO {scratch};
        CREATE TABLE nodes (id text PRIMARY KEY);
        CREATE TABLE links (id integer, dst text, PRIMARY KEY (id, dst));
        INSERT INTO nodes SELECT i::text FROM generate_series(1, 101) i;
        INSERT INTO links SELECT i, '1' FROM generate_series(1, 101) i;
        INSERT INTO links VALUES (1, '2');
        GRANT SELECT ON nodes, links TO "{external_source.reader}";
        """,  # noqa: S608
    )
    source = await add_source(db, external_source)
    for name in ("nodes", "links"):
        await cache_table(db, source.id, external_source, scratch, name)
    ontology = await add_ontology(db)
    node = element(ontology, "entity_type", "Node", "节点")
    rel = element(ontology, "relation_type", "next", "后继", domain_id=node.id, range_id=node.id)
    await add_elements(db, node, rel)
    await sign_in(client, db, Role.ADMIN)
    saved = await save(
        client,
        ontology,
        [
            type_binding(node, {**table(source, "nodes", ["id"]), "schema": scratch}, "nodes"),
            relation_binding(rel, "nodes", "nodes", through_table(scratch, "links", "id", "dst")),
        ],
    )
    assert saved.status_code == 200, saved.text
    assert (await publish(client, ontology)).status_code == 201
    path = schemas.PathQuery(
        type_id=node.id,
        filters=[],
        hops=[schemas.PathHop(relation_id=rel.id, direction="out")],
        target=0,
    )
    config = configure(monkeypatch, query_max_rows=7, metric_rows_max=102)
    result = await service.traverse(db, ontology.id, path, limit=200)
    assert result.total == 101
    assert result.tail_total == 2
    assert result.steps[1].statements == 16  # Fifteen pages of the first batch, one of the second.
    first = cursor.encode_key(["1"])
    assert {tuple(r.via) for r in result.items} == {
        (cursor.encode_key([str(i)]), first) for i in range(1, 102)
    }
    config.metric_rows_max = 101
    with pytest.raises(AppError) as caught:
        await service.traverse_keys(db, ontology.id, path)
    assert caught.value.code == "query.too_many_rows"
    config.metric_rows_max = 103
    admin_rows(external_source, f"INSERT INTO {scratch}.nodes VALUES ('001')")  # noqa: S608
    response = await client.post(
        f"/api/ontologies/{ontology.id}/objects/traverse",
        json=path.model_dump(mode="json", by_alias=True),
        headers=csrf_headers(client),
    )
    assert_problem(response, 409, "query.source_mismatch")


@pytest.mark.parametrize(("limit", "depth"), [(17, 0), (20, 2)], ids=["start", "hop"])
async def test_distinct_object_cap(
    client: AsyncClient,
    qa_steel: SteelObjects,
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    depth: int,
) -> None:
    configure(monkeypatch, query_max_rows=5, metric_rows_max=limit)
    path = demo_path(qa_steel)
    path.hops = path.hops[:depth]
    response = await client.post(
        f"{qa_steel.url}/traverse",
        json=path.model_dump(mode="json", by_alias=True),
        headers=csrf_headers(client),
    )
    assert_problem(response, 422, "query.too_many_rows")
