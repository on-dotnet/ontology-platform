"""Access to the four object routes with anonymous requests and signed-in sessions."""

import base64
import json
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors.models import CatalogTable
from ontology_platform.modules.identity.models import Role
from test_connectors_support import (
    admin_rows,
    cache_table,
    external_statements,
    scratch_fixture,  # noqa: F401  (registers the fixture)
)
from test_ontology_bindings_support import foreign_key, link_table, relation_binding
from test_ontology_support import sign_in
from test_query_support import assert_problem, make_catalog, publish_bindings, search


async def test_all_object_routes_require_authentication(client: AsyncClient) -> None:
    type_id = str(uuid4())
    url = f"/api/ontologies/{uuid4()}/objects"
    obj = f"{url}/{type_id}/example"
    for response in [
        await client.get(f"{url}/types"),
        await client.post(f"{url}/search", json={"typeId": type_id}),
        await client.get(obj),
        await client.get(f"{obj}/related", params={"relationId": str(uuid4())}),
    ]:
        assert_problem(response, 401, "auth.not_authenticated")


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_can_query_and_follow_the_displayed_inverse(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, role: Role
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    await sign_in(client, db, role)
    listed = await client.get(f"{catalog.url}/types")
    assert listed.status_code == 200, listed.json()
    types = {item["typeId"]: item for item in listed.json()["items"]}
    [inverse] = types[str(catalog.coil.id)]["relations"]
    assert inverse == {
        "relationId": str(catalog.inspected_coil.id),
        "label": catalog.inspections.label_zh,
        "direction": "in",
        "otherTypeId": str(catalog.inspection.id),
        "otherTypeLabel": catalog.inspection.label_zh,
    }
    first = await search(client, catalog, catalog.inspection, limit=1)
    assert first.status_code == 200, first.json()
    [inspection] = first.json()["items"]
    outward = await client.get(
        f"{catalog.url}/{catalog.inspection.id}/{inspection['key']}/related",
        params={"relationId": str(catalog.inspected_coil.id), "direction": "out"},
    )
    assert outward.status_code == 200, outward.json()
    [coil] = outward.json()["items"]
    obj = f"{catalog.url}/{catalog.coil.id}/{coil['key']}"
    detail = await client.get(obj)
    assert detail.status_code == 200, detail.json()
    assert detail.json() == {**coil, "relations": [inverse], "release": listed.json()["release"]}
    related = await client.get(
        f"{obj}/related",
        params={"relationId": inverse["relationId"], "direction": inverse["direction"]},
    )
    assert related.status_code == 200, related.json()
    assert related.json()["typeId"] == str(catalog.inspection.id)
    assert related.json()["nextCursor"] is None
    expected = admin_rows(
        external_source,
        "SELECT inspection_id::text FROM mes.quality_inspection WHERE coil_no = %s "
        "ORDER BY inspection_id",
        coil["source"]["key"][0]["value"],
    )
    assert inspection["source"]["key"][0]["value"] in {key for (key,) in expected}
    assert [row["source"]["key"][0]["value"] for row in related.json()["items"]] == [
        key for (key,) in expected
    ]


async def test_inverse_alias_returns_the_same_objects_in_the_opposite_direction(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    for origin, direction, alias_direction in [
        (catalog.coil, "in", "out"),
        (catalog.inspection, "out", "in"),
    ]:
        first = await search(client, catalog, origin, limit=1)
        assert first.status_code == 200, first.text
        [row] = first.json()["items"]
        url = f"{catalog.url}/{origin.id}/{row['key']}/related"
        bound = await client.get(
            url, params={"relationId": str(catalog.inspected_coil.id), "direction": direction}
        )
        alias = await client.get(
            url, params={"relationId": str(catalog.inspections.id), "direction": alias_direction}
        )
        assert bound.status_code == 200, bound.text
        assert bound.json()["items"]
        assert bound.json()["nextCursor"] is None
        assert alias.status_code == 200, alias.text
        assert alias.json() == bound.json()


async def test_bound_inverse_pair_lists_only_outgoing_relations(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    reverse = relation_binding(
        catalog.inspections,
        "coil",
        "inspection",
        foreign_key(["coil_no"], ["coil_no"], side="target"),
    )
    await publish_bindings(client, catalog, [*catalog.bindings(), reverse])
    listed = await client.get(f"{catalog.url}/types")
    assert listed.status_code == 200, listed.text
    types = {item["typeId"]: item for item in listed.json()["items"]}
    for origin, relation, target in [
        (catalog.coil, catalog.inspections, catalog.inspection),
        (catalog.inspection, catalog.inspected_coil, catalog.coil),
    ]:
        expected = [
            {
                "relationId": str(relation.id),
                "direction": "out",
                "label": relation.label_zh,
                "otherTypeId": str(target.id),
                "otherTypeLabel": target.label_zh,
            }
        ]
        assert types[str(origin.id)]["relations"] == expected
        first = await search(client, catalog, origin, limit=1)
        assert first.status_code == 200, first.text
        [row] = first.json()["items"]
        detail = await client.get(f"{catalog.url}/{origin.id}/{row['key']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["relations"] == expected


@pytest.mark.parametrize("missing", ["column", "link_table"])
async def test_an_unusable_bound_inverse_keeps_the_other_relations_reverse_entry(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    scratch: str,
    missing: str,
) -> None:
    catalog = await make_catalog(client, db, external_source)
    # Only the join of the declared inverse uses what disappears; both types stay available.
    if missing == "column":
        key = (catalog.source.id, "mes", "quality_inspection")
        join = foreign_key(["lot_no"], ["coil_no"], side="target")
    else:
        key = (catalog.source.id, scratch, "coil_inspection")
        links = f'"{scratch}".coil_inspection'
        admin_rows(
            external_source,
            f"CREATE TABLE {links} (coil_no varchar(16), inspection_id uuid)",
        )
        await cache_table(db, catalog.source.id, external_source, scratch, "coil_inspection")
        join = link_table(["coil_no"], ["inspection_id"])
        join["join"] |= {"schema": scratch, "table": "coil_inspection"}
    reverse = relation_binding(catalog.inspections, "coil", "inspection", join)
    await publish_bindings(client, catalog, [*catalog.bindings(), reverse])
    cached = await db.get(CatalogTable, key)
    assert cached is not None
    if missing == "column":
        assert "lot_no" in {column["name"] for column in cached.columns}
        cached.columns = [column for column in cached.columns if column["name"] != "lot_no"]
    else:
        await db.delete(cached)
    await db.commit()

    listed = await client.get(f"{catalog.url}/types")
    assert listed.status_code == 200, listed.text
    types = {item["typeId"]: item for item in listed.json()["items"]}
    assert [item["problem"] for item in types.values()] == [None, None]

    def entries(relations: list[dict[str, str]]) -> set[tuple[str, str]]:
        return {(item["relationId"], item["direction"]) for item in relations}

    # The coil still reaches its inspections through the working relation, read backwards.
    working = (str(catalog.inspected_coil.id), "in")
    broken = (str(catalog.inspections.id), "out")
    assert entries(types[str(catalog.coil.id)]["relations"]) == {working, broken}
    first = await search(client, catalog, catalog.coil, limit=1)
    assert first.status_code == 200, first.text
    [row] = first.json()["items"]
    obj = f"{catalog.url}/{catalog.coil.id}/{row['key']}"
    detail = await client.get(obj)
    assert detail.status_code == 200, detail.text
    assert entries(detail.json()["relations"]) == {working, broken}
    related = await client.get(
        f"{obj}/related", params={"relationId": working[0], "direction": working[1]}
    )
    assert related.status_code == 200, related.text
    # From the inspection side the working relation already covers the broken one read backwards.
    assert entries(types[str(catalog.inspection.id)]["relations"]) == {
        (str(catalog.inspected_coil.id), "out")
    }


async def test_a_usable_link_table_inverse_still_replaces_the_reverse_entry(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    links = f'"{scratch}".coil_inspection'
    admin_rows(external_source, f"CREATE TABLE {links} (coil_no varchar(16), inspection_id uuid)")
    await cache_table(db, catalog.source.id, external_source, scratch, "coil_inspection")
    join = link_table(["coil_no"], ["inspection_id"])
    join["join"] |= {"schema": scratch, "table": "coil_inspection"}
    reverse = relation_binding(catalog.inspections, "coil", "inspection", join)
    await publish_bindings(client, catalog, [*catalog.bindings(), reverse])

    listed = await client.get(f"{catalog.url}/types")
    assert listed.status_code == 200, listed.text
    types = {item["typeId"]: item for item in listed.json()["items"]}
    for origin, relation in [
        (catalog.coil, catalog.inspections),
        (catalog.inspection, catalog.inspected_coil),
    ]:
        entries = [(r["relationId"], r["direction"]) for r in types[str(origin.id)]["relations"]]
        assert entries == [(str(relation.id), "out")]


async def test_a_hop_from_a_missing_object_over_a_foreign_key_is_an_empty_page(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    key = base64.urlsafe_b64encode(json.dumps(["NO-SUCH-COIL"]).encode()).decode().rstrip("=")
    related = await client.get(
        f"{catalog.url}/{catalog.coil.id}/{key}/related",
        params={"relationId": str(catalog.inspected_coil.id), "direction": "in"},
    )
    assert related.status_code == 200, related.text
    assert related.json()["items"] == []
    assert related.json()["nextCursor"] is None


async def test_cookie_search_requires_the_matching_csrf_header(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    await sign_in(client, db, Role.VIEWER)
    with external_statements() as statements:
        for headers in ({}, {"X-CSRF-Token": "wrong-token"}):
            denied = await client.post(
                f"{catalog.url}/search", json={"typeId": str(catalog.coil.id)}, headers=headers
            )
            assert_problem(denied, 403, "auth.csrf_failed")
    assert statements == []
    allowed = await search(client, catalog, catalog.coil, limit=1)
    assert allowed.status_code == 200, allowed.json()
    assert len(allowed.json()["items"]) == 1
