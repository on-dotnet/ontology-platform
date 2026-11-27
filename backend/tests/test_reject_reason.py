"""Reject reasons persist only for rejected decisions."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_support import add_ontology, change_set_items, open_change_set, proposal, sign_in


async def test_single_item_reason_and_reset(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    [item] = await change_set_items(client, change_set_id)
    url = f"/api/change-sets/{change_set_id}/items/{item['id']}"
    headers = csrf_headers(client)

    invalid = await client.patch(
        url, json={"decision": "accepted", "rejectReason": "incorrect"}, headers=headers
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "changeset.invalid_reason"
    rejected = await client.patch(
        url, json={"decision": "rejected", "rejectReason": "incorrect"}, headers=headers
    )
    assert rejected.status_code == 200
    assert rejected.json()["rejectReason"] == "incorrect"
    assert (await change_set_items(client, change_set_id))[0]["rejectReason"] == "incorrect"
    # An item that is already rejected takes a reason on its own.
    changed = await client.patch(url, json={"rejectReason": "out_of_scope"}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["rejectReason"] == "out_of_scope"
    cleared = await client.patch(url, json={"decision": "pending"}, headers=headers)
    assert cleared.status_code == 200
    assert cleared.json()["rejectReason"] is None
    pending = await client.patch(url, json={"rejectReason": "incorrect"}, headers=headers)
    assert pending.status_code == 422
    assert pending.json()["code"] == "changeset.invalid_reason"


async def test_bulk_reason_and_acceptance(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    items = [
        proposal("create", "entity_type", local_name="Heat", label_zh="炉次"),
        proposal("create", "entity_type", local_name="Coil", label_zh="钢卷"),
    ]
    change_set_id = await open_change_set(db, ontology, items)
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set_id)]
    url = f"/api/change-sets/{change_set_id}/decisions"
    headers = csrf_headers(client)
    invalid = await client.post(
        url,
        json={"itemIds": ids, "decision": "pending", "rejectReason": "incorrect"},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "changeset.invalid_reason"
    rejected = await client.post(
        url,
        json={"itemIds": ids, "decision": "rejected", "rejectReason": "out_of_scope"},
        headers=headers,
    )
    assert rejected.status_code == 200
    assert [item["rejectReason"] for item in rejected.json()["items"]] == ["out_of_scope"] * 2
    accepted = await client.post(
        url, json={"itemIds": ids, "decision": "accepted"}, headers=headers
    )
    assert accepted.status_code == 200
    assert [item["rejectReason"] for item in accepted.json()["items"]] == [None, None]
