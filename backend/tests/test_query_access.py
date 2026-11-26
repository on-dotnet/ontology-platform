"""Access to the four object routes with anonymous requests and signed-in sessions."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.identity.models import Role
from test_connectors_support import admin_rows, external_statements
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
        "relationId": str(catalog.inspections.id),
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
