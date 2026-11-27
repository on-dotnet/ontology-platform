"""Review memory management and access."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import ReviewMemoryRow
from support import csrf_headers
from test_ontology_support import add_ontology, sign_in
from test_route_protection import token_holder


async def _entry(db: AsyncSession, ontology_id: UUID, label: str = "炉次") -> ReviewMemoryRow:
    row = ReviewMemoryRow(
        id=uuid4(),
        ontology_id=ontology_id,
        kind="rejected",
        element_kind="entity_type",
        key=f"t:{label}",
        label=label,
        detail={"reason": None, "labelEn": None, "domain": None, "range": None},
        created_at=datetime.now(UTC),
        hits=0,
    )
    db.add(row)
    await db.commit()
    return row


async def test_memory_list_delete_restore_clear(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    row = await _entry(db, ontology.id)
    await _entry(db, ontology.id, "钢卷")
    base = f"/api/ontologies/{ontology.id}/review-memory"
    for role in (Role.VIEWER, Role.EDITOR, Role.REVIEWER, Role.ADMIN):
        await sign_in(client, db, role)
        response = await client.get(base, params={"q": "炉", "kind": "rejected", "limit": 1})
        assert response.status_code == 200
        assert (response.json()["total"], len(response.json()["items"])) == (2, 1)
        if role in (Role.VIEWER, Role.EDITOR):
            forbidden = await client.delete(f"{base}/{row.id}", headers=csrf_headers(client))
            assert (forbidden.status_code, forbidden.json()["code"]) == (403, "auth.forbidden")
    deleted = await client.delete(f"{base}/{row.id}", headers=csrf_headers(client))
    assert deleted.status_code == 204
    assert await service.review_memory_for(db, ontology.id) == await service.review_memory_for(
        db, ontology.id
    )
    assert all(e.id != row.id for e in (await service.review_memory_for(db, ontology.id)).entries)
    missing = await client.delete(f"{base}/{row.id}", headers=csrf_headers(client))
    assert (missing.status_code, missing.json()["code"]) == (404, "review_memory.not_found")
    restored = await client.post(f"{base}/{row.id}/restore", headers=csrf_headers(client))
    assert (restored.status_code, restored.json()["id"]) == (200, str(row.id))
    cleared = await client.post(f"{base}/clear", headers=csrf_headers(client))
    assert (cleared.status_code, cleared.json()["cleared"]) == (200, 2)
    denied = await client.post(f"{base}/{row.id}/restore", headers=csrf_headers(client))
    assert (denied.status_code, denied.json()["code"]) == (409, "review_memory.not_restorable")
    events = (
        await db.scalars(
            select(AuditEvent).where(
                AuditEvent.action.in_(
                    ["review_memory.deleted", "review_memory.restored", "review_memory.cleared"]
                )
            )
        )
    ).all()
    assert {event.action for event in events} == {
        "review_memory.deleted",
        "review_memory.restored",
        "review_memory.cleared",
    }


async def test_hits_ignore_deleted(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    row = await _entry(db, ontology.id)
    await service.record_memory_hits(db, ontology.id, [row.id])
    await db.commit()
    await db.refresh(row)
    assert row.hits == 1
    await sign_in(client, db, Role.REVIEWER)
    assert (
        await client.delete(
            f"/api/ontologies/{ontology.id}/review-memory/{row.id}", headers=csrf_headers(client)
        )
    ).status_code == 204
    await service.record_memory_hits(db, ontology.id, [row.id, uuid4()])
    await db.commit()
    await db.refresh(row)
    assert row.hits == 1


async def test_memory_pagination_and_token(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    for label in ("炉次", "钢卷", "钢包"):
        await _entry(db, ontology.id, label)
    base = f"/api/ontologies/{ontology.id}/review-memory"
    await sign_in(client, db, Role.VIEWER)
    first = await client.get(base, params={"limit": 1})
    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert first.json()["max"] >= 3
    assert first.json()["nextCursor"] is not None
    second = await client.get(base, params={"limit": 1, "cursor": first.json()["nextCursor"]})
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
    token = await token_holder(client)
    refused = await client.get(base, headers=token)
    assert (refused.status_code, refused.json()["code"]) == (403, "auth.token_not_allowed")


async def test_restore_uses_fresh_time_for_eviction(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Settings reads this only when the service performs the eviction.
    monkeypatch.setenv("OP_REVIEW_MEMORY_MAX", "1")
    ontology = await add_ontology(db)
    old = await _entry(db, ontology.id)
    old.hits = 7
    old.last_hit_at = datetime(2000, 1, 1, tzinfo=UTC)
    old.deleted_at = datetime.now(UTC)
    old.deleted_reason = "deleted"
    await db.commit()
    newer = await _entry(db, ontology.id, "钢卷")
    await sign_in(client, db, Role.REVIEWER)
    base = f"/api/ontologies/{ontology.id}/review-memory"
    response = await client.post(f"{base}/{old.id}/restore", headers=csrf_headers(client))
    assert response.status_code == 200
    await db.refresh(old)
    await db.refresh(newer)
    assert (response.json()["hits"], response.json()["lastHitAt"]) == (7, None)
    assert (
        await db.scalar(
            select(ReviewMemoryRow.id).where(
                ReviewMemoryRow.id == old.id, ReviewMemoryRow.deleted_at.is_(None)
            )
        )
        == old.id
    )
    assert newer.deleted_reason == "evicted"
