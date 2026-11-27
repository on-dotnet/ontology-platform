"""Review memory collection and merge persistence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import ChangeItem, ReviewMemoryRow
from ontology_platform.modules.ontology.review_memory import (
    DecidedItem,
    MemoryEntry,
    ReviewMemory,
    apply_delta,
    collect,
)
from support import csrf_headers
from test_ontology_support import (
    add_elements,
    add_ontology,
    change_set_items,
    decide,
    element,
    merge,
    open_change_set,
    proposal,
    sign_in,
)


def _item(**changes: object) -> DecidedItem:
    values = {
        "item_id": uuid4(),
        "kind": "entity_type",
        "op": "create",
        "decision": "rejected",
        "reject_reason": None,
        "proposed_label_zh": "炉次",
        "proposed_label_en": None,
        "final_label_zh": "炉次",
        "final_label_en": None,
        "domain_label": None,
        "range_label": None,
        "created_element_id": None,
        "renamed_element_id": None,
        "match_kind": None,
        "match_decision": None,
        "match_other_label": None,
        "match_other_element_id": None,
    }
    values.update(changes)
    return DecidedItem(**values)  # type: ignore[arg-type]


def test_collect_rejections_and_exclusions() -> None:
    rejected = _item()
    delta = collect(
        "ai_extraction", [rejected, _item(match_kind="possible"), _item(reject_reason="duplicate")]
    )
    assert len(delta.upserts) == 1
    assert (delta.upserts[0].kind, delta.upserts[0].key) == ("rejected", "t:炉次")
    assert collect("manual", [rejected]).upserts == ()
    assert collect("ai_extraction", [_item(op="update")]).upserts == ()


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (None, True),
        ("out_of_scope", True),
        ("incorrect", True),
        ("duplicate", False),
        ("keep_open", False),
    ],
)
def test_collect_reject_reasons(reason: str | None, expected: bool) -> None:
    assert bool(collect("ai_extraction", [_item(reject_reason=reason)]).upserts) is expected


def test_rejected_different_collects_kept_apart_only() -> None:
    item = _item(match_kind="possible", match_decision="different", match_other_label="钢卷")
    delta = collect("ai_extraction", [item])
    assert [entry.kind for entry in delta.upserts] == ["kept_apart"]


def test_empty_names_and_into_do_not_create_memory() -> None:
    assert (
        collect("ai_extraction", [_item(proposed_label_zh=" ", final_label_zh=" ")]).upserts == ()
    )
    into = _item(decision="accepted", final_label_zh="新炉次")
    assert collect("ai_extraction", [into]).upserts == ()


def test_collect_same_key_keeps_last_item() -> None:
    first = _item(reject_reason="out_of_scope")
    last = _item(reject_reason="incorrect")
    delta = collect("ai_extraction", [first, last])
    assert len(delta.upserts) == 1
    assert delta.upserts[0].source_item_id == last.item_id
    assert delta.upserts[0].detail["reason"] == "incorrect"


def test_collect_rename_kept_apart_and_supersession() -> None:
    element_id = uuid4()
    renamed = _item(decision="accepted", final_label_zh="新炉次", created_element_id=element_id)
    apart = _item(
        decision="accepted",
        created_element_id=element_id,
        match_kind="possible",
        match_decision="different",
        match_other_label="钢卷",
    )
    delta = collect("ai_extraction", [renamed, apart])
    assert {entry.kind for entry in delta.upserts} == {"renamed", "kept_apart"}
    assert ("entity_type", "t:新炉次") in delta.superseded_keys
    assert collect("manual", [renamed]).superseded_keys


def test_apply_delta_supersedes_then_revives_and_evicts() -> None:
    ontology_id = uuid4()
    old = MemoryEntry(
        id=uuid4(),
        kind="rejected",
        element_kind="entity_type",
        key="t:炉次",
        label="炉次",
        reason=None,
        label_en=None,
        domain=None,
        range=None,
        to_label_zh=None,
        to_label_en=None,
        element_id=None,
        other_label=None,
        created_at=datetime.now(UTC) - timedelta(days=2),
        last_hit_at=None,
    )
    new = _item(proposed_label_zh="钢卷", final_label_zh="钢卷")
    delta = collect("ai_extraction", [_item(decision="accepted", created_element_id=uuid4()), new])
    result = apply_delta(
        ReviewMemory(ontology_id, (old,)), delta, now=datetime.now(UTC), max_entries=2
    )
    assert result.find("rejected", "t:钢卷") is not None
    assert result.find("rejected", "t:炉次") is None
    revived = apply_delta(
        ReviewMemory(ontology_id, (old,)),
        collect("ai_extraction", [_item()]),
        now=datetime.now(UTC),
        max_entries=1,
    )
    assert revived.entries[0].id == old.id
    assert revived.entries[0].created_at > old.created_at


def test_apply_delta_keeps_id_after_supersede_and_recollect() -> None:
    old_delta = collect("ai_extraction", [_item()])
    empty = ReviewMemory(uuid4(), ())
    first = apply_delta(empty, old_delta, now=datetime.now(UTC), max_entries=2)
    delta = collect(
        "ai_extraction", [_item(decision="accepted", created_element_id=uuid4()), _item()]
    )
    second = apply_delta(first, delta, now=datetime.now(UTC), max_entries=2)
    before = first.find("rejected", "t:炉次")
    after = second.find("rejected", "t:炉次")
    assert before is not None
    assert after is not None
    assert after.id == before.id


async def test_merge_collects_and_audits(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    actor_id = await db.scalar(select(User.id).where(User.username == "reviewer-user"))
    item_id = (await change_set_items(client, change_set))[0]["id"]
    assert (await decide(client, change_set, [item_id], "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    rows = (
        await db.scalars(select(ReviewMemoryRow).where(ReviewMemoryRow.ontology_id == ontology.id))
    ).all()
    assert len(rows) == 1
    assert (rows[0].kind, rows[0].key, rows[0].deleted_at) == ("rejected", "t:炉次", None)
    assert rows[0].source_change_set_id == change_set
    assert rows[0].decided_by == actor_id
    assert rows[0].created_at is not None
    events = (
        await db.scalars(select(AuditEvent).where(AuditEvent.action == "review_memory.collected"))
    ).all()
    assert len(events) == 1
    assert events[0].detail["count"] == 1


async def test_merge_collects_bulk_reject_reason(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    item_id = (await change_set_items(client, change_set))[0]["id"]
    response = await client.post(
        f"/api/change-sets/{change_set}/decisions",
        json={"itemIds": [item_id], "decision": "rejected", "rejectReason": "out_of_scope"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    memory = await db.scalar(
        select(ReviewMemoryRow).where(ReviewMemoryRow.ontology_id == ontology.id)
    )
    assert memory is not None
    assert memory.detail["reason"] == "out_of_scope"


async def test_merge_supersedes_and_revives(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    row = ReviewMemoryRow(
        id=uuid4(),
        ontology_id=ontology.id,
        kind="rejected",
        element_kind="entity_type",
        key="t:炉次",
        label="炉次",
        detail={"reason": None, "labelEn": None, "domain": None, "range": None},
        created_at=datetime.now(UTC),
        hits=3,
    )
    db.add(row)
    await db.commit()
    await sign_in(client, db, Role.REVIEWER)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    item_id = (await change_set_items(client, change_set))[0]["id"]
    assert (await decide(client, change_set, [item_id], "accepted")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    await db.refresh(row)
    assert (row.deleted_reason, row.hits) == ("superseded", 3)
    previous_created_at = row.created_at
    await db.execute(
        update(ReviewMemoryRow)
        .where(ReviewMemoryRow.id == row.id)
        .values(
            last_hit_at=datetime(2000, 1, 1, tzinfo=UTC),
            deleted_by=await db.scalar(select(User.id).where(User.username == "reviewer-user")),
            label="旧名称",
            detail={"reason": "incorrect", "labelEn": "old", "domain": None, "range": None},
        )
    )
    await db.commit()
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat2", label_zh="炉次")]
    )
    item_id = (await change_set_items(client, change_set))[0]["id"]
    assert (await decide(client, change_set, [item_id], "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    await db.refresh(row)
    assert (row.deleted_at, row.hits) == (None, 0)
    assert row.source_item_id == UUID(item_id)
    assert row.source_change_set_id == change_set
    assert row.decided_by is not None
    assert row.created_at > previous_created_at
    assert row.last_hit_at is None
    assert (row.deleted_reason, row.deleted_by) == (None, None)
    assert row.label == "炉次"
    assert row.detail["labelEn"] is None


async def test_whole_rejection_collects_nothing(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    response = await client.post(
        f"/api/change-sets/{change_set}/reject", headers=csrf_headers(client)
    )
    assert response.status_code == 200
    assert (await db.scalars(select(ReviewMemoryRow))).all() == []


async def test_manual_merge_supersedes_without_collecting(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    row = ReviewMemoryRow(
        id=uuid4(),
        ontology_id=ontology.id,
        kind="rejected",
        element_kind="entity_type",
        key="t:炉次",
        label="炉次",
        detail={"reason": None, "labelEn": None, "domain": None, "range": None},
        created_at=datetime.now(UTC),
        hits=0,
    )
    db.add(row)
    await db.commit()
    change_set = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title="手工录入",
        source="manual",
        document_id=None,
        created_by=None,
        items=[
            proposal("create", "entity_type", local_name="Heat", label_zh="炉次"),
            proposal("create", "entity_type", local_name="Coil", label_zh="钢卷"),
        ],
    )
    await db.commit()
    await sign_in(client, db, Role.REVIEWER)
    item_ids = [item["id"] for item in await change_set_items(client, change_set)]
    item_id = item_ids[0]
    assert (await decide(client, change_set, [item_id], "accepted")).status_code == 200
    assert (await decide(client, change_set, [item_ids[1]], "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    await db.refresh(row)
    assert row.deleted_reason == "superseded"
    assert (await db.scalars(select(ReviewMemoryRow))).all() == [row]


async def test_eviction_uses_last_hit_before_creation(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_REVIEW_MEMORY_MAX", "2")
    ontology = await add_ontology(db)
    old = ReviewMemoryRow(
        id=uuid4(),
        ontology_id=ontology.id,
        kind="rejected",
        element_kind="entity_type",
        key="t:旧",
        label="旧",
        detail={"reason": None, "labelEn": None, "domain": None, "range": None},
        created_at=datetime.now(UTC) - timedelta(days=20),
        last_hit_at=datetime.now(UTC) - timedelta(days=1),
        hits=1,
    )
    newer = ReviewMemoryRow(
        id=uuid4(),
        ontology_id=ontology.id,
        kind="rejected",
        element_kind="entity_type",
        key="t:较新",
        label="较新",
        detail={"reason": None, "labelEn": None, "domain": None, "range": None},
        created_at=datetime.now(UTC) - timedelta(days=2),
        hits=0,
    )
    db.add_all([old, newer])
    await db.commit()
    old_entry = MemoryEntry(
        id=old.id,
        kind="rejected",
        element_kind="entity_type",
        key=old.key,
        label=old.label,
        reason=None,
        label_en=None,
        domain=None,
        range=None,
        to_label_zh=None,
        to_label_en=None,
        element_id=None,
        other_label=None,
        created_at=old.created_at,
        last_hit_at=old.last_hit_at,
    )
    newer_entry = replace(
        old_entry,
        id=newer.id,
        key=newer.key,
        label=newer.label,
        created_at=newer.created_at,
        last_hit_at=None,
    )
    new_item = _item(proposed_label_zh="最新", final_label_zh="最新")
    expected = apply_delta(
        ReviewMemory(ontology.id, (old_entry, newer_entry)),
        collect("ai_extraction", [new_item]),
        now=datetime.now(UTC),
        max_entries=2,
    )
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Fresh", label_zh="最新")]
    )
    await sign_in(client, db, Role.REVIEWER)
    item_id = (await change_set_items(client, change_set))[0]["id"]
    assert (await decide(client, change_set, [item_id], "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    await db.refresh(old)
    await db.refresh(newer)
    assert old.deleted_at is None
    assert newer.deleted_reason == "evicted"
    active_keys = set(
        await db.scalars(
            select(ReviewMemoryRow.key).where(
                ReviewMemoryRow.ontology_id == ontology.id,
                ReviewMemoryRow.deleted_at.is_(None),
            )
        )
    )
    assert {entry.key for entry in expected.entries} == active_keys


async def test_merge_collects_rename_and_kept_apart(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    other = element(ontology, "entity_type", "Coil", "钢卷")
    await add_elements(db, other)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    item_id = (await change_set_items(client, change_set))[0]["id"]
    row = await db.get(ChangeItem, UUID(item_id))
    assert row is not None
    row.match_kind = "possible"
    row.match_decision = "different"
    row.match_element_id = other.id
    await db.commit()
    patched = await client.patch(
        f"/api/change-sets/{change_set}/items/{item_id}",
        json={"edited": {"labelZh": "新炉次"}, "decision": "accepted"},
        headers=csrf_headers(client),
    )
    assert patched.status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    rows = (
        await db.scalars(select(ReviewMemoryRow).where(ReviewMemoryRow.ontology_id == ontology.id))
    ).all()
    assert {row.kind for row in rows} == {"renamed", "kept_apart"}
    assert next(row for row in rows if row.kind == "kept_apart").detail["otherLabel"] == "钢卷"


async def test_merge_keeps_last_duplicate_and_evicts(
    client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_REVIEW_MEMORY_MAX", "1")
    ontology = await add_ontology(db)
    change_set = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name="Heat1", label_zh="炉次"),
            proposal("create", "entity_type", local_name="Heat2", label_zh="炉次"),
            proposal("create", "entity_type", local_name="Coil", label_zh="钢卷"),
        ],
    )
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set)]
    assert (await decide(client, change_set, ids, "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    rows = (
        await db.scalars(select(ReviewMemoryRow).where(ReviewMemoryRow.ontology_id == ontology.id))
    ).all()
    assert len(rows) == 2
    duplicate = next(row for row in rows if row.key == "t:炉次")
    assert duplicate.source_item_id == UUID(ids[1])
    assert sum(row.deleted_at is None for row in rows) == 1
    assert {row.deleted_reason for row in rows} == {"evicted", None}


async def test_rejected_relation_and_property_are_collected(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    coil = element(ontology, "entity_type", "Coil", "钢卷")
    await add_elements(db, heat, coil)
    change_set = await open_change_set(
        db,
        ontology,
        [
            proposal(
                "create",
                "relation_type",
                local_name="Produces",
                label_zh="产出",
                domain_ref=str(heat.id),
                range_ref=str(coil.id),
            ),
            proposal(
                "create",
                "property",
                local_name="heatNo",
                label_zh="编号",
                domain_ref=str(heat.id),
                datatype="integer",
            ),
        ],
    )
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set)]
    assert (await decide(client, change_set, ids, "rejected")).status_code == 200
    assert (await merge(client, change_set)).status_code == 200
    rows = (await db.scalars(select(ReviewMemoryRow))).all()
    assert {(row.element_kind, row.key) for row in rows} == {
        ("relation_type", "r:炉次|产出|钢卷"),
        ("property", "p:炉次|编号"),
    }


async def test_alignment_rejection_and_dependency_skip_are_not_collected(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    other = element(ontology, "entity_type", "Coil", "钢卷")
    await add_elements(db, other)
    change_set = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set)]
    aligned = await db.get(ChangeItem, UUID(ids[0]))
    assert aligned is not None
    aligned.match_kind = "possible"
    aligned.match_element_id = other.id
    await db.commit()
    assert (await decide(client, change_set, [ids[0]], "rejected")).status_code == 200
    result = await merge(client, change_set)
    assert result.status_code == 200
    assert (await db.scalars(select(ReviewMemoryRow))).all() == []

    change_set = await open_change_set(
        db,
        ontology,
        [
            proposal(
                "create", "entity_type", temp_ref="new:Heat", local_name="Heat2", label_zh="炉次"
            ),
            proposal(
                "create",
                "property",
                local_name="heatNo",
                label_zh="编号",
                domain_ref="new:Heat",
                datatype="integer",
            ),
        ],
    )
    ids = [item["id"] for item in await change_set_items(client, change_set)]
    assert (await decide(client, change_set, [ids[0]], "rejected")).status_code == 200
    assert (await decide(client, change_set, [ids[1]], "accepted")).status_code == 200
    result = await merge(client, change_set)
    assert result.status_code == 200
    assert result.json()["skipped"][0]["code"] == "changeset.dependency_skipped"
    collected = (await db.scalars(select(ReviewMemoryRow))).all()
    assert {(row.kind, row.element_kind) for row in collected} == {("rejected", "entity_type")}
