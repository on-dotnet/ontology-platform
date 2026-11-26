"""Object browsing against a published model and the real steel sample."""

from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Ontology
from support import csrf_headers
from test_connectors_support import add_source, admin_rows, cache_table
from test_ontology_bindings_support import (
    foreign_key,
    property_binding,
    relation_binding,
    save,
    table,
    type_binding,
)
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in


@dataclass
class SteelObjects:
    ontology: Ontology
    ids: dict[str, str]
    release: dict[str, Any]
    source_id: str
    source_name: str

    @property
    def url(self) -> str:
        return f"/api/ontologies/{self.ontology.id}/objects"

    async def search(self, client: AsyncClient, name: str, **fields: Any) -> Response:
        return await client.post(
            f"{self.url}/search",
            json={"typeId": self.ids[name], **fields},
            headers=csrf_headers(client),
        )


def through_table(schema: str, name: str, source_column: str, target_column: str) -> dict[str, Any]:
    return {
        "target": "join",
        "join": {
            "kind": "link_table",
            "schema": schema,
            "table": name,
            "sourceColumns": [source_column],
            "targetColumns": [target_column],
        },
    }


@pytest.fixture(name="steel_objects")
async def steel_objects_fixture(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> SteelObjects:
    source = await add_source(db, external_source)
    ontology = await add_ontology(db)
    batch = element(ontology, "entity_type", "Batch", "批次")
    heat = element(ontology, "entity_type", "Heat", "炉次", parent_id=batch.id)
    slab = element(ontology, "entity_type", "Slab", "板坯")
    rolling = element(ontology, "entity_type", "Rolling", "轧制事件")
    participation = element(ontology, "entity_type", "Participation", "板坯轧制记录")
    temp = element(ontology, "property", "temp", "出钢温度", domain_id=heat.id, datatype="integer")
    site = element(ontology, "property", "site", "厂区", domain_id=heat.id, datatype="string")
    number = element(
        ontology, "property", "rollingNo", "轧制编号", domain_id=participation.id, datatype="string"
    )
    in_batch = element(
        ontology, "relation_type", "inBatch", "所属批次", domain_id=heat.id, range_id=batch.id
    )
    produces = element(
        ontology, "relation_type", "produces", "产出板坯", domain_id=heat.id, range_id=slab.id
    )
    rolled_in = element(
        ontology, "relation_type", "rolledIn", "参与轧制", domain_id=slab.id, range_id=rolling.id
    )
    event = element(
        ontology,
        "relation_type",
        "event",
        "对应事件",
        domain_id=participation.id,
        range_id=rolling.id,
    )
    elements = [batch, heat, slab, rolling, participation, temp, site, number]
    elements.extend([in_batch, produces, rolled_in, event])
    await add_elements(db, *elements)
    items = []
    for subject, name, keys in [
        (batch, "casting_sequence", ["cast_no"]),
        (heat, "heat", ["heat_no"]),
        (slab, "slab", ["slab_no"]),
        (rolling, "rolling_event", ["rolling_id"]),
        (participation, "slab_rolling", ["slab_no", "rolling_id"]),
    ]:
        await cache_table(db, source.id, external_source, "mes", name)
        items.append(type_binding(subject, table(source, name, keys), name))
    items.extend(
        [
            property_binding(temp, "heat", "tap_temp_c"),
            property_binding(site, "heat", "site_id"),
            property_binding(number, "slab_rolling", "rolling_id"),
            relation_binding(in_batch, "heat", "casting_sequence"),
            relation_binding(
                produces, "heat", "slab", foreign_key(["heat_no"], ["heat_no"], side="target")
            ),
            relation_binding(
                rolled_in,
                "slab",
                "rolling_event",
                through_table("mes", "slab_rolling", "slab_no", "rolling_id"),
            ),
            relation_binding(
                event, "slab_rolling", "rolling_event", foreign_key(["rolling_id"], ["rolling_id"])
            ),
        ]
    )
    await sign_in(client, db, Role.ADMIN)
    saved = await save(client, ontology, items)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"] is True
    released = await publish(client, ontology)
    assert released.status_code == 201, released.text
    release = released.json()
    assert release["bindingCount"] == len(items)
    return SteelObjects(
        ontology,
        {e.local_name: str(e.id) for e in elements if e.local_name is not None},
        {"id": release["id"], "version": release["version"]},
        str(source.id),
        source.name,
    )


@pytest.mark.parametrize("nulls_first", [True, False], ids=["descending", "ascending"])
async def test_two_sort_keys_page_through_nulls_and_ties(
    client: AsyncClient,
    steel_objects: SteelObjects,
    external_source: ExternalSource,
    nulls_first: bool,
) -> None:
    steel = steel_objects
    if nulls_first:
        sql = (
            "SELECT heat_no, site_id, tap_temp_c FROM mes.heat "
            "ORDER BY tap_temp_c DESC NULLS FIRST, site_id ASC, heat_no"
        )
        order = [("temp", "desc"), ("site", "asc")]
        limit = 2
    else:
        sql = (
            "SELECT heat_no, site_id, tap_temp_c FROM mes.heat "
            "ORDER BY site_id DESC, tap_temp_c ASC NULLS LAST, heat_no"
        )
        order = [("site", "desc"), ("temp", "asc")]
        limit = 5
    expected = admin_rows(external_source, sql)
    assert any(expected[i][2] is None for i in range(limit - 1, len(expected) - 1, limit))
    assert len({(site, temp) for _, site, temp in expected}) < len(expected)
    sort = [{"propertyId": steel.ids[prop], "direction": direction} for prop, direction in order]
    cursor = None
    for offset in range(0, len(expected), limit):
        response = await steel.search(client, "Heat", sort=sort, limit=limit, cursor=cursor)
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["release"] == steel.release
        assert page["typeId"] == steel.ids["Heat"]
        assert [(row["source"]["key"], row["values"]) for row in page["items"]] == [
            (
                [{"column": "heat_no", "value": key}],
                {steel.ids["site"]: site, steel.ids["temp"]: temp},
            )
            for key, site, temp in expected[offset : offset + limit]
        ]
        cursor = page["nextCursor"]
        if offset + limit < len(expected):
            assert isinstance(cursor, str)
            assert cursor
        else:
            assert cursor is None


async def test_cursor_is_bound_to_type_filter_sort_and_release(
    client: AsyncClient, steel_objects: SteelObjects
) -> None:
    steel = steel_objects
    first = await steel.search(client, "Heat", limit=1)
    assert first.status_code == 200, first.text
    cursor = first.json()["nextCursor"]
    assert isinstance(cursor, str)
    assert cursor
    for response in [
        await steel.search(client, "Batch", limit=1, cursor=cursor),
        await steel.search(
            client, "Heat", limit=1, cursor=cursor, sort=[{"propertyId": steel.ids["site"]}]
        ),
        await steel.search(client, "Heat", cursor="!"),
    ]:
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "query.invalid_cursor"

    site = {"propertyId": steel.ids["site"], "op": "eq", "value": "S1"}
    sort = {"propertyId": steel.ids["temp"], "direction": "asc"}
    filtered = await steel.search(client, "Heat", filters=[site], sort=[sort], limit=1)
    assert filtered.status_code == 200, filtered.text
    filtered_cursor = filtered.json()["nextCursor"]
    assert isinstance(filtered_cursor, str)
    assert filtered_cursor
    continued = await steel.search(
        client, "Heat", filters=[site], sort=[sort], limit=1, cursor=filtered_cursor
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["items"][0]["key"] != filtered.json()["items"][0]["key"]
    for criterion, order in [
        ({**site, "value": "S2"}, sort),
        (site, {**sort, "direction": "desc"}),
    ]:
        changed = await steel.search(
            client, "Heat", filters=[criterion], sort=[order], limit=1, cursor=filtered_cursor
        )
        assert changed.status_code == 422, changed.text
        assert changed.json()["code"] == "query.invalid_cursor"

    published = await publish(client, steel.ontology, "第二版")
    assert published.status_code == 201, published.text
    assert published.json()["version"] > steel.release["version"]
    stale = await steel.search(client, "Heat", limit=1, cursor=cursor)
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "query.release_changed"
    fresh = await steel.search(client, "Heat", limit=1)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["release"] == {
        "id": published.json()["id"],
        "version": published.json()["version"],
    }


async def test_parent_search_only_lists_rows_of_its_bound_table(
    client: AsyncClient, steel_objects: SteelObjects, external_source: ExternalSource
) -> None:
    steel = steel_objects
    for name, column, sql in [
        ("Batch", "cast_no", "SELECT cast_no FROM mes.casting_sequence ORDER BY cast_no"),
        ("Heat", "heat_no", "SELECT heat_no FROM mes.heat ORDER BY heat_no"),
    ]:
        expected = admin_rows(external_source, sql)
        assert expected
        response = await steel.search(client, name, limit=200)
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["nextCursor"] is None
        assert [(row["typeId"], row["source"]["key"]) for row in page["items"]] == [
            (steel.ids[name], [{"column": column, "value": value}]) for (value,) in expected
        ]


async def test_default_page_size_and_limit_ceiling(
    client: AsyncClient, steel_objects: SteelObjects, external_source: ExternalSource
) -> None:
    steel = steel_objects
    expected = admin_rows(external_source, "SELECT slab_no FROM mes.slab ORDER BY slab_no")
    assert 50 < len(expected) < 200
    first = await steel.search(client, "Slab")
    assert first.status_code == 200, first.text
    page = first.json()
    keys = [row["source"]["key"][0]["value"] for row in page["items"]]
    assert keys == [slab for (slab,) in expected[:50]]
    assert page["nextCursor"]
    rest = await steel.search(client, "Slab", limit=200, cursor=page["nextCursor"])
    assert rest.status_code == 200, rest.text
    assert rest.json()["nextCursor"] is None
    assert [row["source"]["key"][0]["value"] for row in rest.json()["items"]] == [
        slab for (slab,) in expected[50:]
    ]
    too_many = await steel.search(client, "Slab", limit=201)
    assert too_many.status_code == 422
