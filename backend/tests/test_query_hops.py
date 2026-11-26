"""Related-object pages, composite identity and provenance in the steel sample."""

import re
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_connectors_support import (
    add_source,
    admin_rows,
    cache_table,
    external_statements,
    scratch_fixture,  # noqa: F401
)
from test_ontology_bindings_support import relation_binding, save, table, type_binding
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in
from test_query_paging import SteelObjects, steel_objects_fixture, through_table  # noqa: F401


def _rows_by_key(response: Response) -> dict[tuple[str, ...], dict[str, Any]]:
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["nextCursor"] is None
    rows = {tuple(k["value"] for k in row["source"]["key"]): row for row in page["items"]}
    assert len(rows) == len(page["items"])
    return rows


@pytest.mark.parametrize(
    ("relation", "direction", "origin_type", "origin_key", "target_type", "key_column", "expected"),
    [
        ("inBatch", "out", "Heat", "H2401004", "Batch", "cast_no", ["C2401002"]),
        (
            "inBatch",
            "in",
            "Batch",
            "C2401002",
            "Heat",
            "heat_no",
            ["H2401003", "H2401004", "H2401005", "H2401006"],
        ),
        (
            "produces",
            "out",
            "Heat",
            "H2401003",
            "Slab",
            "slab_no",
            ["S240100301", "S240100302", "S240100303"],
        ),
        ("produces", "in", "Slab", "S240100303", "Heat", "heat_no", ["H2401003"]),
        (
            "rolledIn",
            "out",
            "Slab",
            "S240100303",
            "Rolling",
            "rolling_id",
            ["R2401004", "R2401005"],
        ),
        (
            "rolledIn",
            "in",
            "Rolling",
            "R2401004",
            "Slab",
            "slab_no",
            ["S240100301", "S240100302", "S240100303"],
        ),
    ],
)
async def test_each_hop_page_reads_the_sample_with_one_inner_join(
    client: AsyncClient,
    steel_objects: SteelObjects,
    relation: str,
    direction: str,
    origin_type: str,
    origin_key: str,
    target_type: str,
    key_column: str,
    expected: list[str],
) -> None:
    steel = steel_objects
    origins = _rows_by_key(await steel.search(client, origin_type, limit=200))
    key = origins[(origin_key,)]["key"]
    url = f"{steel.url}/{steel.ids[origin_type]}/{key}/related"
    params = {"relationId": steel.ids[relation], "direction": direction, "limit": "1"}
    for index, value in enumerate(expected):
        with external_statements() as statements:
            response = await client.get(url, params=params)
        assert response.status_code == 200, response.text
        # Connection setup also reads PostgreSQL metadata. Count every read of the sample schema.
        [sql] = [s for s, _ in statements if re.search(r'\bmes"?\s*\.', s, re.IGNORECASE)]
        words = sql.upper().split()
        assert words.count("SELECT") == 1
        assert words.count("JOIN") == 1
        assert {"LEFT", "RIGHT", "FULL", "CROSS"}.isdisjoint(words)
        page = response.json()
        assert page["release"] == steel.release
        assert page["typeId"] == steel.ids[target_type]
        [row] = page["items"]
        assert row["typeId"] == steel.ids[target_type]
        assert row["source"]["key"] == [{"column": key_column, "value": value}]
        if index + 1 < len(expected):
            cursor = page["nextCursor"]
            assert isinstance(cursor, str)
            assert cursor
            params["cursor"] = cursor
        else:
            assert page["nextCursor"] is None


async def test_composite_keys_page_and_round_trip_to_detail(
    client: AsyncClient, steel_objects: SteelObjects, external_source: ExternalSource
) -> None:
    steel = steel_objects
    expected = admin_rows(
        external_source,
        "SELECT slab_no, rolling_id FROM mes.slab_rolling ORDER BY slab_no, rolling_id",
    )
    # Start the next page inside a group with the same first key column.
    split = expected.index(("S240100303", "R2401005"))
    assert expected[split - 1] == ("S240100303", "R2401004")
    cursor = None
    by_pair = {}
    for start in range(0, len(expected), split):
        response = await steel.search(client, "Participation", limit=split, cursor=cursor)
        assert response.status_code == 200, response.text
        page = response.json()
        pairs = expected[start : start + split]
        for row, (slab, rolling) in zip(page["items"], pairs, strict=True):
            assert row["typeId"] == steel.ids["Participation"]
            assert row["values"] == {steel.ids["rollingNo"]: rolling}
            assert row["source"] == {
                "dataSourceId": steel.source_id,
                "dataSourceName": steel.source_name,
                "schema": "mes",
                "table": "slab_rolling",
                "key": [
                    {"column": "slab_no", "value": slab},
                    {"column": "rolling_id", "value": rolling},
                ],
            }
            by_pair[slab, rolling] = row
        cursor = page["nextCursor"]
        if start + split < len(expected):
            assert isinstance(cursor, str)
            assert cursor
        else:
            assert cursor is None
    assert len({row["key"] for row in by_pair.values()}) == len(expected)

    types = await client.get(f"{steel.url}/types")
    assert types.status_code == 200, types.text
    [info] = [t for t in types.json()["items"] if t["typeId"] == steel.ids["Participation"]]
    assert info["keyColumns"] == ["slab_no", "rolling_id"]
    assert info["relations"] == [
        {
            "relationId": steel.ids["event"],
            "label": "对应事件",
            "direction": "out",
            "otherTypeId": steel.ids["Rolling"],
            "otherTypeLabel": "轧制事件",
        }
    ]
    for pair in [
        ("S240100303", "R2401004"),
        ("S240100303", "R2401005"),
        ("S240100401", "R2401005"),
    ]:
        item = by_pair[pair]
        path = f"{steel.url}/{steel.ids['Participation']}/{item['key']}"
        detail = await client.get(path)
        assert detail.status_code == 200, detail.text
        assert detail.json() == {**item, "release": steel.release, "relations": info["relations"]}
        related = await client.get(f"{path}/related", params={"relationId": steel.ids["event"]})
        assert related.status_code == 200, related.text
        [event] = related.json()["items"]
        assert event["source"]["key"] == [{"column": "rolling_id", "value": pair[1]}]


async def test_hop_cursor_binds_origin_relation_and_direction_independently(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    # Both directions and both relations are legal for exactly the same type and starting object.
    admin_rows(
        external_source,
        f"CREATE TABLE {scratch}.edges (a text, b text, PRIMARY KEY (a, b)); "
        f'GRANT SELECT ON {scratch}.edges TO "{external_source.reader}"',
    )
    admin_rows(
        external_source,
        f"INSERT INTO {scratch}.edges VALUES ('H2401001', 'H2401002'), "  # noqa: S608
        "('H2401001', 'H2401003'), ('H2401002', 'H2401001')",
    )
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    next_heat = element(
        ontology, "relation_type", "nextHeat", "后续炉次", domain_id=heat.id, range_id=heat.id
    )
    prev_heat = element(
        ontology, "relation_type", "prevHeat", "先前炉次", domain_id=heat.id, range_id=heat.id
    )
    await add_elements(db, heat, next_heat, prev_heat)
    source = await add_source(db, external_source)
    await cache_table(db, source.id, external_source, "mes", "heat")
    await cache_table(db, source.id, external_source, scratch, "edges")
    items = [type_binding(heat, table(source), "heat")]
    for relation, left, right in [(next_heat, "a", "b"), (prev_heat, "b", "a")]:
        items.append(
            relation_binding(
                relation,
                "heat",
                "heat",
                through_table(scratch, "edges", left, right),
            )
        )
    await sign_in(client, db, Role.ADMIN)
    saved = await save(client, ontology, items)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"] is True
    release = await publish(client, ontology)
    assert release.status_code == 201, release.text
    objects_url = f"/api/ontologies/{ontology.id}/objects"
    heats = _rows_by_key(
        await client.post(
            f"{objects_url}/search",
            json={"typeId": str(heat.id), "limit": 200},
            headers=csrf_headers(client),
        )
    )
    base = f"{objects_url}/{heat.id}"
    first_url = f"{base}/{heats[('H2401001',)]['key']}/related"
    second_url = f"{base}/{heats[('H2401002',)]['key']}/related"
    params = {"relationId": str(next_heat.id), "direction": "out", "limit": "1"}
    first = await client.get(first_url, params=params)
    assert first.status_code == 200, first.text
    [item] = first.json()["items"]
    assert item["source"]["key"] == [{"column": "heat_no", "value": "H2401002"}]
    cursor = first.json()["nextCursor"]
    assert isinstance(cursor, str)
    assert cursor
    for url, change in [
        (second_url, {}),
        (first_url, {"direction": "in"}),
        (first_url, {"relationId": str(prev_heat.id)}),
    ]:
        response = await client.get(url, params={**params, **change, "cursor": cursor})
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "query.invalid_cursor"
    second = await client.get(first_url, params={**params, "cursor": cursor})
    assert second.status_code == 200, second.text
    [item] = second.json()["items"]
    assert item["source"]["key"] == [{"column": "heat_no", "value": "H2401003"}]
    assert second.json()["nextCursor"] is None

    as_search = await client.post(
        f"{objects_url}/search",
        json={"typeId": str(heat.id), "limit": 1, "cursor": cursor},
        headers=csrf_headers(client),
    )
    assert as_search.status_code == 422, as_search.text
    assert as_search.json()["code"] == "query.invalid_cursor"
    published = await publish(client, ontology, "第二版")
    assert published.status_code == 201, published.text
    stale = await client.get(first_url, params={**params, "cursor": cursor})
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "query.release_changed"


async def test_link_table_rejects_an_origin_key_that_would_be_truncated(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    admin_rows(
        external_source,
        f"""
        SET search_path TO {scratch};
        CREATE TABLE origins (code text PRIMARY KEY);
        CREATE TABLE targets (code text PRIMARY KEY);
        CREATE TABLE edges (origin_code character(4), target_code text,
                            PRIMARY KEY (origin_code, target_code));
        INSERT INTO origins VALUES ('ABCD'), ('ABCDE');
        INSERT INTO targets VALUES ('T1');
        INSERT INTO edges VALUES ('ABCD', 'T1');
        GRANT SELECT ON origins, targets, edges TO "{external_source.reader}";
        """,  # noqa: S608 (identifiers come from the scratch fixtures)
    )
    source = await add_source(db, external_source)
    for name in ("origins", "targets", "edges"):
        await cache_table(db, source.id, external_source, scratch, name)
    ontology = await add_ontology(db)
    origin = element(ontology, "entity_type", "Origin", "起点")
    target = element(ontology, "entity_type", "Target", "终点")
    relation = element(
        ontology, "relation_type", "leadsTo", "指向", domain_id=origin.id, range_id=target.id
    )
    await add_elements(db, origin, target, relation)
    await sign_in(client, db, Role.ADMIN)
    saved = await save(
        client,
        ontology,
        [
            type_binding(origin, {**table(source, "origins", ["code"]), "schema": scratch}, "src"),
            type_binding(target, {**table(source, "targets", ["code"]), "schema": scratch}, "dst"),
            relation_binding(
                relation,
                "src",
                "dst",
                through_table(scratch, "edges", "origin_code", "target_code"),
            ),
        ],
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"] is True
    released = await publish(client, ontology)
    assert released.status_code == 201, released.text

    url = f"/api/ontologies/{ontology.id}/objects"
    origins = _rows_by_key(
        await client.post(
            f"{url}/search", json={"typeId": str(origin.id)}, headers=csrf_headers(client)
        )
    )
    short_key = origins[("ABCD",)]["key"]
    long_key = origins[("ABCDE",)]["key"]
    assert short_key != long_key
    params = {"relationId": str(relation.id), "direction": "out"}
    matched = await client.get(f"{url}/{origin.id}/{short_key}/related", params=params)
    assert matched.status_code == 200, matched.text
    [row] = matched.json()["items"]
    assert row["typeId"] == str(target.id)
    assert row["source"]["key"] == [{"column": "code", "value": "T1"}]

    rejected = await client.get(f"{url}/{origin.id}/{long_key}/related", params=params)
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["code"] == "query.source_mismatch"
    assert "items" not in rejected.json()
