"""Reject reasons persist only for rejected decisions."""

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_review_mode import change_set_by, first_item, user_id
from test_ontology_support import add_ontology, change_set_items, open_change_set, proposal, sign_in


async def test_a_reason_on_ones_own_change_set_is_a_self_review(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.settings.review_mode = "separate"
    ontology = await add_ontology(db)
    await sign_in(client, db, Role.REVIEWER)
    change_set_id = await change_set_by(db, ontology, await user_id(db, Role.REVIEWER))
    item_id = await first_item(client, change_set_id)
    url = f"/api/change-sets/{change_set_id}/items/{item_id}"
    # Someone else rejects the item; its creator may not then give or clear the reason.
    await sign_in(client, db, Role.ADMIN)
    rejected = await client.patch(url, json={"decision": "rejected"}, headers=csrf_headers(client))
    assert rejected.status_code == 200
    await sign_in(client, db, Role.REVIEWER)
    for reason in ("incorrect", None):
        response = await client.patch(
            url, json={"rejectReason": reason}, headers=csrf_headers(client)
        )
        assert (response.status_code, response.json()["code"]) == (403, "changeset.self_review")


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
    # null clears the reason and keeps the rejection.
    unset = await client.patch(url, json={"rejectReason": None}, headers=headers)
    assert unset.status_code == 200
    assert (unset.json()["decision"], unset.json()["rejectReason"]) == ("rejected", None)
    await client.patch(url, json={"rejectReason": "incorrect"}, headers=headers)
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
    # Rejecting again without a reason keeps the reasons already given.
    again = await client.post(url, json={"itemIds": ids, "decision": "rejected"}, headers=headers)
    assert [item["rejectReason"] for item in again.json()["items"]] == ["out_of_scope"] * 2
    accepted = await client.post(
        url, json={"itemIds": ids, "decision": "accepted"}, headers=headers
    )
    assert accepted.status_code == 200
    assert [item["rejectReason"] for item in accepted.json()["items"]] == [None, None]
