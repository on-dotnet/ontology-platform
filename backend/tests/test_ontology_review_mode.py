"""Review modes (spec 002, section 8): who may decide and merge whose change sets."""

from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import Ontology
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem
from support import csrf_headers
from test_ontology_support import add_ontology, sign_in


async def user_id(db: AsyncSession, role: Role) -> UUID:
    username = "admin" if role is Role.ADMIN else f"{role.value}-user"
    found = await db.scalar(select(User.id).where(User.username == username))
    assert found is not None
    return found


async def change_set_by(db: AsyncSession, ontology: Ontology, creator: UUID) -> UUID:
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title="手工修改",
        source="manual",
        document_id=None,
        created_by=creator,
        items=[
            ProposedItem(
                op="create",
                kind="entity_type",
                temp_ref="new:Ladle",
                proposed=ElementFields(local_name="Ladle", label_zh="钢包"),
            ),
        ],
    )
    await db.commit()
    return change_set_id


async def first_item(client: AsyncClient, change_set_id: UUID) -> str:
    response = await client.get(f"/api/change-sets/{change_set_id}")
    item_id: str = response.json()["items"][0]["id"]
    return item_id


async def test_platform_settings_report_the_review_mode(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)

    assert (await client.get("/api/settings/platform")).json() == {"reviewMode": "single"}
    app.state.settings.review_mode = "separate"
    assert (await client.get("/api/settings/platform")).json() == {"reviewMode": "separate"}


async def test_separate_mode_keeps_reviewers_off_their_own_change_sets(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.settings.review_mode = "separate"
    await sign_in(client, db, Role.REVIEWER)
    ontology = await add_ontology(db)
    change_set_id = await change_set_by(db, ontology, await user_id(db, Role.REVIEWER))
    item_id = await first_item(client, change_set_id)
    headers = csrf_headers(client)

    for response in (
        await client.patch(
            f"/api/change-sets/{change_set_id}/items/{item_id}",
            json={"decision": "accepted"},
            headers=headers,
        ),
        await client.patch(
            f"/api/change-sets/{change_set_id}/items/{item_id}",
            json={"edited": {"labelZh": "钢水包"}},
            headers=headers,
        ),
        await client.post(
            f"/api/change-sets/{change_set_id}/decisions",
            json={"itemIds": [item_id], "decision": "accepted"},
            headers=headers,
        ),
        await client.post(f"/api/change-sets/{change_set_id}/merge", headers=headers),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "changeset.self_review"
    # A note is not a decision.
    noted = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item_id}",
        json={"note": "请别人看看"},
        headers=headers,
    )
    assert noted.status_code == 200

    # Somebody else reviews it.
    await sign_in(client, db, Role.ADMIN)
    headers = csrf_headers(client)
    decided = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item_id}",
        json={"decision": "accepted"},
        headers=headers,
    )
    assert decided.status_code == 200
    merged = await client.post(f"/api/change-sets/{change_set_id}/merge", headers=headers)
    assert merged.status_code == 200
    assert merged.json()["applied"] == 1


async def test_single_mode_lets_reviewers_merge_their_own(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.REVIEWER)
    ontology = await add_ontology(db)
    change_set_id = await change_set_by(db, ontology, await user_id(db, Role.REVIEWER))
    item_id = await first_item(client, change_set_id)
    headers = csrf_headers(client)

    decided = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item_id}",
        json={"decision": "accepted"},
        headers=headers,
    )
    assert decided.status_code == 200
    merged = await client.post(f"/api/change-sets/{change_set_id}/merge", headers=headers)
    assert merged.status_code == 200


async def test_creators_withdraw_their_own_change_sets_only(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.settings.review_mode = "separate"
    await sign_in(client, db, Role.EDITOR)
    ontology = await add_ontology(db)
    own = await change_set_by(db, ontology, await user_id(db, Role.EDITOR))
    others = await change_set_by(db, ontology, await user_id(db, Role.ADMIN))
    headers = csrf_headers(client)

    withdrawn = await client.post(f"/api/change-sets/{own}/reject", headers=headers)
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "rejected"
    refused = await client.post(f"/api/change-sets/{others}/reject", headers=headers)
    assert refused.status_code == 403
    assert refused.json()["code"] == "auth.forbidden"
    # Deciding stays a reviewer's job.
    item_id = await first_item(client, others)
    decided = await client.patch(
        f"/api/change-sets/{others}/items/{item_id}",
        json={"decision": "accepted"},
        headers=headers,
    )
    assert decided.status_code == 403
    assert decided.json()["code"] == "auth.forbidden"
