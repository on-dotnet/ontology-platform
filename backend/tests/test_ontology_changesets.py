"""Change sets: proposals from other modules, review and edit checks, merge and rejection."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Element, Ontology
from ontology_platform.modules.ontology.schemas import ProposedItem
from support import PROBLEM_JSON, csrf_headers
from test_ontology_support import (
    CHUNK_ID,
    DOCUMENT_ID,
    accept_and_merge,
    add_elements,
    add_ontology,
    change_set_items,
    decide,
    decide_by_seq,
    element,
    elements_by_name,
    merge,
    open_change_set,
    proposal,
    sign_in,
)

ITEM_FIELDS = {
    "id",
    "seq",
    "op",
    "kind",
    "targetElementId",
    "tempRef",
    "proposed",
    "edited",
    "before",
    "decision",
    "confidence",
    "rationale",
    "flags",
    "note",
    "decidedBy",
    "decidedAt",
    "appliedElementId",
    "evidence",
}


def slab(**fields: Any) -> ProposedItem:
    return proposal(
        "create",
        "entity_type",
        temp_ref="new:Slab",
        local_name="Slab",
        label_zh="板坯",
        **fields,
    )


async def patch_item(
    client: AsyncClient,
    change_set_id: UUID,
    item_id: str,
    body: dict[str, Any],
) -> Response:
    return await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item_id}",
        json=body,
        headers=csrf_headers(client),
    )


async def count_rows(db: AsyncSession, model: type[ChangeSet | ChangeItem | Element]) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


# ---------- create_change_set ----------


async def test_create_change_set_stores_items_in_order(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次", revision=3)
    await add_elements(db, heat)
    thickness = proposal(
        "create",
        "property",
        temp_ref="new:thickness",
        local_name="thickness",
        label_zh="厚度",
        domain_ref="new:Slab",
        datatype="decimal",
        unit="mm",
        flags=["evidence_not_found"],
        confidence=0.45,
    )
    synonyms = [{"lang": "zh", "text": "熔炼号"}]
    update = proposal("update", "entity_type", target=heat.id, synonyms=synonyms, label_en=None)

    change_set_id = await open_change_set(db, steel, [slab(), thickness, update])

    stored = await db.scalar(
        select(ChangeItem).where(ChangeItem.change_set_id == change_set_id, ChangeItem.seq == 3),
    )
    assert stored is not None
    assert stored.target_revision == 3
    await sign_in(client, db, Role.VIEWER)
    response = await client.get(f"/api/change-sets/{change_set_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["title"] == "识别：工艺规程.docx"
    assert detail["source"] == "ai_extraction"
    assert detail["status"] == "open"
    assert detail["documentId"] == str(DOCUMENT_ID)
    assert detail["mergedAt"] is None
    assert detail["counts"] == {"total": 3, "pending": 3, "accepted": 0, "rejected": 0}
    first, second, third = detail["items"]
    assert set(first) == ITEM_FIELDS
    assert [item["seq"] for item in detail["items"]] == [1, 2, 3]
    # Only the keys that were proposed come back; an explicit null is kept.
    assert first["proposed"] == {"localName": "Slab", "labelZh": "板坯"}
    assert first["tempRef"] == "new:Slab"
    assert first["targetElementId"] is None
    assert first["before"] is None
    assert first["edited"] is None
    assert first["decision"] == "pending"
    assert first["rationale"] == "原文直接给出了定义。"
    assert first["evidence"] == [
        {
            "id": first["evidence"][0]["id"],
            "documentId": str(DOCUMENT_ID),
            "chunkId": str(CHUNK_ID),
            "quote": "原文引语",
            "charStart": 0,
            "charEnd": 4,
        },
    ]
    assert second["proposed"]["domainRef"] == "new:Slab"
    assert second["flags"] == ["evidence_not_found"]
    assert second["confidence"] == 0.45
    assert third["op"] == "update"
    assert third["targetElementId"] == str(heat.id)
    assert third["tempRef"] is None
    assert third["proposed"] == {"labelEn": None, "synonyms": synonyms}
    assert third["before"] == {
        "localName": "Heat",
        "labelZh": "炉次",
        "labelEn": None,
        "definitionZh": None,
        "definitionEn": None,
        "synonyms": [],
        "parentRef": None,
        "autoShape": True,
    }


async def test_create_change_set_only_adds_to_the_callers_transaction(
    app: FastAPI,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)

    change_set_id = await service.create_change_set(
        db,
        ontology_id=steel.id,
        title="识别：草稿.md",
        source="ai_extraction",
        document_id=None,
        created_by=None,
        items=[slab()],
    )

    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as other:
        assert await other.get(ChangeSet, change_set_id) is None
    await db.rollback()
    assert await count_rows(db, ChangeSet) == 0
    assert await count_rows(db, ChangeItem) == 0


@dataclass
class Fixture:
    steel: Ontology
    heat: Element
    relation: Element
    foreign: Element


def _cases() -> dict[str, Callable[[Fixture], list[ProposedItem]]]:
    def property_on(domain: str) -> ProposedItem:
        return proposal(
            "create",
            "property",
            local_name="weight",
            label_zh="重量",
            domain_ref=domain,
            datatype="decimal",
        )

    return {
        "unknown temp_ref": lambda f: [property_on("new:Missing")],
        "duplicate temp_ref": lambda f: [slab(), slab()],
        "element of another ontology": lambda f: [property_on(str(f.foreign.id))],
        "unknown element id": lambda f: [property_on(str(uuid4()))],
        "reference to a relation": lambda f: [property_on(str(f.relation.id))],
        "reference to a created property": lambda f: [
            proposal("create", "property", temp_ref="new:p", local_name="p", label_zh="属性"),
            property_on("new:p"),
        ],
        "parent is itself": lambda f: [slab(parent_ref="new:Slab")],
        "update parent is itself": lambda f: [
            proposal("update", "entity_type", target=f.heat.id, parent_ref=str(f.heat.id)),
        ],
        "update without target": lambda f: [proposal("update", "entity_type", label_zh="炉")],
        "update of another ontology": lambda f: [
            proposal("update", "entity_type", target=f.foreign.id, label_zh="炉"),
        ],
        "update with another kind": lambda f: [
            proposal("update", "property", target=f.heat.id, label_zh="炉"),
        ],
        "update with temp_ref": lambda f: [
            proposal("update", "entity_type", target=f.heat.id, temp_ref="new:Heat"),
        ],
        "create with target": lambda f: [
            proposal("create", "entity_type", target=f.heat.id, local_name="Heat2", label_zh="炉"),
        ],
        "unknown flag": lambda f: [slab(flags=["looks_odd"])],
        "temp_ref looks like an id": lambda f: [
            proposal("create", "entity_type", temp_ref=str(uuid4()), local_name="A"),
        ],
    }


@pytest.mark.parametrize("case", sorted(_cases()))
async def test_create_change_set_rejects_inconsistent_items(db: AsyncSession, case: str) -> None:
    steel = await add_ontology(db)
    other = await add_ontology(db, key="other")
    heat = element(steel, "entity_type", "Heat", "炉次")
    relation = element(steel, "relation_type", "near", "邻近", domain_id=heat.id, range_id=heat.id)
    foreign = element(other, "entity_type", "Coil", "钢卷")
    await add_elements(db, heat, relation, foreign)
    items = _cases()[case](Fixture(steel=steel, heat=heat, relation=relation, foreign=foreign))

    with pytest.raises(service.InvalidProposalError) as raised:
        await service.create_change_set(
            db,
            ontology_id=steel.id,
            title="识别：样例.docx",
            source="ai_extraction",
            document_id=None,
            created_by=None,
            items=items,
        )

    assert raised.value.status == 422
    assert raised.value.code == "changeset.invalid_item"
    await db.rollback()
    assert await count_rows(db, ChangeSet) == 0


async def test_create_change_set_needs_an_existing_ontology(db: AsyncSession) -> None:
    with pytest.raises(AppError) as raised:
        await service.create_change_set(
            db,
            ontology_id=uuid4(),
            title="识别：样例.docx",
            source="ai_extraction",
            document_id=None,
            created_by=None,
            items=[slab()],
        )

    assert raised.value.code == "ontology.not_found"


# ---------- review ----------


async def test_patch_sets_decision_and_note(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    change_set_id = await open_change_set(db, steel, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    [item] = await change_set_items(client, change_set_id)

    accepted = await patch_item(
        client,
        change_set_id,
        item["id"],
        {"decision": "accepted", "note": "  定义准确  "},
    )
    reset = await patch_item(client, change_set_id, item["id"], {"decision": "pending"})

    assert accepted.status_code == 200
    body = accepted.json()
    assert set(body) == ITEM_FIELDS
    assert body["decision"] == "accepted"
    assert body["decidedBy"] is not None
    assert body["decidedAt"] is not None
    assert body["note"] == "定义准确"
    assert reset.json()["decision"] == "pending"
    assert reset.json()["decidedBy"] is None
    assert reset.json()["decidedAt"] is None
    assert reset.json()["note"] == "定义准确"


async def test_patch_edit_is_kept_and_wins_at_merge(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    change_set_id = await open_change_set(db, steel, [slab(label_en="Slab")])
    await sign_in(client, db, Role.REVIEWER)
    [item] = await change_set_items(client, change_set_id)
    edited = {"labelZh": "连铸坯", "labelEn": None, "synonyms": [{"lang": "zh", "text": "板坯"}]}

    response = await patch_item(
        client,
        change_set_id,
        item["id"],
        {"edited": edited, "decision": "accepted"},
    )
    result = await merge(client, change_set_id)

    assert response.status_code == 200
    assert response.json()["edited"] == edited
    proposed = {"localName": "Slab", "labelZh": "板坯", "labelEn": "Slab"}
    assert response.json()["proposed"] == proposed
    assert result.json() == {"applied": 1, "skipped": []}
    created = (await elements_by_name(db, steel))["Slab"]
    assert created.label_zh == "连铸坯"
    assert created.label_en is None
    assert created.synonyms == [{"lang": "zh", "text": "板坯"}]


async def test_patch_can_drop_the_edit(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    change_set_id = await open_change_set(db, steel, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    [item] = await change_set_items(client, change_set_id)
    await patch_item(client, change_set_id, item["id"], {"edited": {"labelZh": "连铸坯"}})

    response = await patch_item(client, change_set_id, item["id"], {"edited": None})

    assert response.status_code == 200
    assert response.json()["edited"] is None


@dataclass
class ReviewFixture:
    plant: Element
    site: Element
    relation: Element


EDIT_CASES: list[tuple[str, int, Callable[[ReviewFixture], dict[str, Any]]]] = [
    ("object type not PascalCase", 1, lambda f: {"localName": "slab"}),
    ("characters outside the rule", 1, lambda f: {"localName": "Slab_1"}),
    ("blank labelZh", 1, lambda f: {"labelZh": "   "}),
    ("datatype on an object type", 1, lambda f: {"datatype": "string"}),
    ("unit on an object type", 1, lambda f: {"unit": "mm"}),
    ("domain on an object type", 1, lambda f: {"domainRef": str(f.plant.id)}),
    ("parent is itself", 1, lambda f: {"parentRef": "new:Slab"}),
    ("parent is a relation", 1, lambda f: {"parentRef": str(f.relation.id)}),
    ("unknown parent", 1, lambda f: {"parentRef": "new:Nothing"}),
    ("relation not camelCase", 2, lambda f: {"localName": "CastFrom"}),
    ("relation without domain", 2, lambda f: {"domainRef": None}),
    ("relation range unknown", 2, lambda f: {"rangeRef": str(uuid4())}),
    ("relation with datatype", 2, lambda f: {"datatype": "decimal"}),
    ("relation with parent", 2, lambda f: {"parentRef": str(f.plant.id)}),
    ("property without datatype", 3, lambda f: {"datatype": None}),
    ("property with range", 3, lambda f: {"rangeRef": str(f.plant.id)}),
    ("property domain is a property", 3, lambda f: {"domainRef": "new:width"}),
    ("update renames", 4, lambda f: {"localName": "Factory"}),
    ("update clears labelZh", 4, lambda f: {"labelZh": None}),
    ("update makes a cycle", 4, lambda f: {"parentRef": str(f.site.id)}),
    ("update parent through new type", 4, lambda f: {"parentRef": "new:Slab"}),
]


@pytest.mark.parametrize(("case", "seq", "build"), EDIT_CASES, ids=[c[0] for c in EDIT_CASES])
async def test_invalid_edits_are_rejected(
    client: AsyncClient,
    db: AsyncSession,
    case: str,
    seq: int,
    build: Callable[[ReviewFixture], dict[str, Any]],
) -> None:
    steel = await add_ontology(db)
    plant = element(steel, "entity_type", "Plant", "工厂")
    site = element(steel, "entity_type", "Site", "厂区", parent_id=plant.id)
    near = element(steel, "relation_type", "near", "邻近", domain_id=plant.id, range_id=site.id)
    await add_elements(db, plant, site, near)
    items = [
        # The new Slab sits below Plant, so making Plant a child of Slab closes a loop.
        slab(parent_ref=str(plant.id)),
        proposal(
            "create",
            "relation_type",
            local_name="castFrom",
            label_zh="浇铸自",
            domain_ref="new:Slab",
            range_ref=str(plant.id),
        ),
        proposal(
            "create",
            "property",
            temp_ref="new:width",
            local_name="width",
            label_zh="宽度",
            domain_ref="new:Slab",
            datatype="decimal",
        ),
        proposal("update", "entity_type", target=plant.id, label_en="Plant"),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    item = (await change_set_items(client, change_set_id))[seq - 1]
    edit = build(ReviewFixture(plant=plant, site=site, relation=near))

    response = await patch_item(client, change_set_id, item["id"], {"edited": edit})

    assert response.status_code == 422, case
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "changeset.invalid_edit"
    stored = await db.get(ChangeItem, UUID(item["id"]), populate_existing=True)
    assert stored is not None
    assert stored.edited is None


async def test_valid_edits_of_each_kind_are_accepted(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    plant = element(steel, "entity_type", "Plant", "工厂")
    await add_elements(db, plant)
    items = [
        slab(),
        proposal(
            "create",
            "relation_type",
            local_name="castFrom",
            label_zh="浇铸自",
            domain_ref="new:Slab",
            range_ref=str(plant.id),
        ),
        proposal("update", "entity_type", target=plant.id, label_en="Plant"),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    first, second, third = await change_set_items(client, change_set_id)
    edits = [
        (first, {"localName": "CastSlab", "definitionEn": "A cast slab."}),
        (second, {"rangeRef": "new:Slab", "required": True, "multiple": True}),
        (third, {"localName": "Plant", "definitionZh": "生产单位。", "parentRef": "new:Slab"}),
    ]

    responses = [
        await patch_item(client, change_set_id, item["id"], {"edited": edit})
        for item, edit in edits
    ]

    assert [response.status_code for response in responses] == [200, 200, 200]


async def test_invalid_datatype_value_fails_request_validation(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    change_set_id = await open_change_set(db, steel, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    [item] = await change_set_items(client, change_set_id)

    response = await patch_item(client, change_set_id, item["id"], {"edited": {"datatype": "x"}})

    assert response.status_code == 422
    assert response.json()["code"] == "validation.failed"


async def test_bulk_decisions(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    heat = proposal("create", "entity_type", local_name="Heat", label_zh="炉次")
    change_set_id = await open_change_set(db, steel, [slab(), heat])
    other_id = await open_change_set(db, steel, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    first, second = await change_set_items(client, change_set_id)
    [foreign] = await change_set_items(client, other_id)

    unknown = await decide(client, change_set_id, [first["id"], str(uuid4())], "accepted")
    elsewhere = await decide(client, change_set_id, [foreign["id"]], "accepted")
    accepted = await decide(client, change_set_id, [first["id"], second["id"]], "accepted")
    rejected = await decide(client, change_set_id, [second["id"]], "rejected")

    for response in (unknown, elsewhere):
        assert response.status_code == 404
        assert response.json()["code"] == "changeset.not_found"
    assert accepted.status_code == 200
    assert accepted.json()["counts"] == {"total": 2, "pending": 0, "accepted": 2, "rejected": 0}
    detail = rejected.json()
    assert detail["counts"] == {"total": 2, "pending": 0, "accepted": 1, "rejected": 1}
    assert [item["decision"] for item in detail["items"]] == ["accepted", "rejected"]
    assert detail["items"][0]["proposed"] == {"localName": "Slab", "labelZh": "板坯"}
    [still_pending] = await change_set_items(client, other_id)
    assert still_pending["decision"] == "pending"


async def test_list_change_sets_with_counts_and_filters(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    other = await add_ontology(db, key="other")
    merged_id = await open_change_set(db, steel, [slab()])
    coil = proposal("create", "entity_type", local_name="Coil", label_zh="钢卷")
    open_id = await open_change_set(db, steel, [slab(), coil])
    foreign_id = await open_change_set(db, other, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    await accept_and_merge(client, merged_id)

    everything = (await client.get("/api/change-sets")).json()
    by_ontology = {"ontologyId": str(steel.id)}
    for_steel = (await client.get("/api/change-sets", params=by_ontology)).json()
    open_only = (await client.get("/api/change-sets", params={"status": "open"})).json()

    assert {item["id"] for item in everything} == {str(merged_id), str(open_id), str(foreign_id)}
    assert {item["id"] for item in for_steel} == {str(merged_id), str(open_id)}
    assert {item["id"] for item in open_only} == {str(open_id), str(foreign_id)}
    summary = next(item for item in everything if item["id"] == str(open_id))
    assert set(summary) == {
        "id",
        "ontologyId",
        "title",
        "source",
        "documentId",
        "status",
        "counts",
        "createdBy",
        "createdAt",
        "mergedAt",
    }
    assert summary["createdBy"] is None  # open_change_set names no creator
    assert summary["counts"] == {"total": 2, "pending": 2, "accepted": 0, "rejected": 0}
    merged = next(item for item in everything if item["id"] == str(merged_id))
    assert merged["status"] == "merged"
    assert merged["mergedAt"] is not None


async def test_reject_closes_the_change_set(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    heat = proposal("create", "entity_type", local_name="Heat", label_zh="炉次")
    change_set_id = await open_change_set(db, steel, [slab(), heat])
    await sign_in(client, db, Role.REVIEWER)
    await decide_by_seq(client, change_set_id, {1: "accepted"})

    response = await client.post(
        f"/api/change-sets/{change_set_id}/reject",
        headers=csrf_headers(client),
    )

    assert response.status_code == 200
    summary = response.json()
    assert summary["status"] == "rejected"
    assert summary["counts"] == {"total": 2, "pending": 0, "accepted": 1, "rejected": 1}
    assert await count_rows(db, Element) == 0
    statement = (
        select(AuditEvent.action)
        .where(AuditEvent.target_id == str(change_set_id))
        .order_by(AuditEvent.id)
    )
    assert (await db.scalars(statement)).all() == ["changeset.created", "changeset.rejected"]


async def test_closed_change_sets_cannot_change(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    merged_id = await open_change_set(db, steel, [slab()])
    rejected_id = await open_change_set(db, steel, [slab()])
    await sign_in(client, db, Role.REVIEWER)
    await accept_and_merge(client, merged_id)
    await client.post(f"/api/change-sets/{rejected_id}/reject", headers=csrf_headers(client))

    for change_set_id in (merged_id, rejected_id):
        [item] = await change_set_items(client, change_set_id)
        attempts = [
            await patch_item(client, change_set_id, item["id"], {"decision": "rejected"}),
            await decide(client, change_set_id, [item["id"]], "pending"),
            await merge(client, change_set_id),
            await client.post(
                f"/api/change-sets/{change_set_id}/reject",
                headers=csrf_headers(client),
            ),
        ]
        for response in attempts:
            assert response.status_code == 409
            assert response.json()["code"] == "changeset.closed"


# ---------- merge ----------


async def test_merge_needs_every_item_decided(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    heat = proposal("create", "entity_type", local_name="Heat", label_zh="炉次")
    change_set_id = await open_change_set(db, steel, [slab(), heat])
    await sign_in(client, db, Role.REVIEWER)
    await decide_by_seq(client, change_set_id, {1: "accepted"})

    response = await merge(client, change_set_id)

    assert response.status_code == 409
    assert response.json()["code"] == "changeset.pending_items"
    assert await count_rows(db, Element) == 0
    change_set = await db.get(ChangeSet, change_set_id, populate_existing=True)
    assert change_set is not None
    assert change_set.status == "open"


async def test_merge_resolves_temp_refs_in_any_order(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    items = [
        proposal(
            "create",
            "relation_type",
            local_name="producedIn",
            label_zh="冶炼于",
            domain_ref="new:Heat",
            range_ref="new:Converter",
            required=True,
        ),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:Converter",
            local_name="Converter",
            label_zh="转炉",
            parent_ref="new:Equipment",
        ),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:Equipment",
            local_name="Equipment",
            label_zh="装备",
        ),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:Heat",
            local_name="Heat",
            label_zh="炉次",
            synonyms=[{"lang": "zh", "text": "熔次"}, {"lang": "zh", "text": " 熔次 "}],
        ),
        proposal(
            "create",
            "property",
            local_name="heatNumber",
            label_zh="炉号",
            domain_ref="new:Heat",
            datatype="string",
            unit="  ",
        ),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)

    result = await accept_and_merge(client, change_set_id)

    assert result == {"applied": 5, "skipped": []}
    created = await elements_by_name(db, steel)
    assert set(created) == {"producedIn", "Converter", "Equipment", "Heat", "heatNumber"}
    assert created["Converter"].parent_id == created["Equipment"].id
    assert created["producedIn"].domain_id == created["Heat"].id
    assert created["producedIn"].range_id == created["Converter"].id
    assert created["producedIn"].required is True
    assert created["heatNumber"].domain_id == created["Heat"].id
    assert created["heatNumber"].unit is None
    assert created["Heat"].synonyms == [{"lang": "zh", "text": "熔次"}]
    assert {row.origin for row in created.values()} == {"ai"}
    assert {row.revision for row in created.values()} == {1}
    merged_items = await change_set_items(client, change_set_id)
    applied = {item["seq"]: item["appliedElementId"] for item in merged_items}
    assert applied[2] == str(created["Converter"].id)
    assert applied[1] == str(created["producedIn"].id)
    detail = (await client.get(f"/api/change-sets/{change_set_id}")).json()
    assert detail["status"] == "merged"
    assert detail["mergedAt"] is not None
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "changeset.merged"))
    assert event is not None
    assert event.target_id == str(change_set_id)
    assert event.detail == {"ontologyId": str(steel.id), "applied": 5, "skipped": 0}


async def test_merge_skips_dependents_of_rejected_items(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    items = [
        proposal("create", "entity_type", temp_ref="new:A", local_name="Alpha", label_zh="甲"),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:B",
            local_name="Beta",
            label_zh="乙",
            parent_ref="new:A",
        ),
        proposal(
            "create",
            "property",
            local_name="gamma",
            label_zh="丙",
            domain_ref="new:B",
            datatype="integer",
        ),
        proposal("create", "entity_type", local_name="Delta", label_zh="丁"),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    await decide_by_seq(client, change_set_id, {1: "rejected", 2: "accepted", 3: "accepted"})
    await decide_by_seq(client, change_set_id, {4: "accepted"})
    ids = {item["seq"]: item["id"] for item in await change_set_items(client, change_set_id)}

    response = await merge(client, change_set_id)

    assert response.status_code == 200
    assert response.json() == {
        "applied": 1,
        "skipped": [
            {"itemId": ids[2], "code": "changeset.dependency_skipped"},
            {"itemId": ids[3], "code": "changeset.dependency_skipped"},
        ],
    }
    assert set(await elements_by_name(db, steel)) == {"Delta"}


async def test_merge_skips_stale_updates(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)
    first = await open_change_set(
        db,
        steel,
        [proposal("update", "entity_type", target=heat.id, definition_zh="一次冶炼。")],
    )
    second = await open_change_set(
        db,
        steel,
        [proposal("update", "entity_type", target=heat.id, label_en="Heat")],
    )
    await sign_in(client, db, Role.REVIEWER)
    assert await accept_and_merge(client, second) == {"applied": 1, "skipped": []}
    [item] = await change_set_items(client, first)

    result = await accept_and_merge(client, first)

    stale = {"itemId": item["id"], "code": "changeset.stale_target"}
    assert result == {"applied": 0, "skipped": [stale]}
    current = (await elements_by_name(db, steel))["Heat"]
    assert current.revision == 2
    assert current.label_en == "Heat"
    assert current.definition_zh is None


async def test_merge_skips_invalid_items(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    gone = element(steel, "entity_type", "Gone", "废弃", status="deprecated")
    await add_elements(db, heat, gone)
    items = [
        proposal("create", "entity_type", local_name="slab", label_zh="板坯"),
        proposal("create", "entity_type", local_name="Heat", label_zh="重复的炉次"),
        proposal(
            "create",
            "relation_type",
            local_name="goesTo",
            label_zh="去往",
            domain_ref=str(heat.id),
            range_ref=str(gone.id),
        ),
        proposal("create", "property", local_name="weight", label_zh="重", domain_ref=str(heat.id)),
        proposal("create", "entity_type", local_name="Coil"),
        proposal("create", "entity_type", local_name="Ladle", label_zh="钢包"),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set_id)]

    result = await accept_and_merge(client, change_set_id)

    assert result == {
        "applied": 1,
        "skipped": [{"itemId": item_id, "code": "changeset.invalid_item"} for item_id in ids[:5]],
    }
    assert set(await elements_by_name(db, steel)) == {"Heat", "Gone", "Ladle"}


async def test_merge_rejects_cycles_in_the_type_hierarchy(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    plant = element(steel, "entity_type", "Plant", "工厂")
    await add_elements(db, plant)
    items = [
        # Plant would move below the new Site, which itself sits below Plant.
        proposal("update", "entity_type", target=plant.id, parent_ref="new:Site"),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:Site",
            local_name="Site",
            label_zh="厂区",
            parent_ref=str(plant.id),
        ),
        # Two new types that are each other's parent.
        proposal(
            "create",
            "entity_type",
            temp_ref="new:A",
            local_name="Alpha",
            label_zh="甲",
            parent_ref="new:B",
        ),
        proposal(
            "create",
            "entity_type",
            temp_ref="new:B",
            local_name="Beta",
            label_zh="乙",
            parent_ref="new:A",
        ),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    ids = [item["id"] for item in await change_set_items(client, change_set_id)]

    result = await accept_and_merge(client, change_set_id)

    assert result == {
        "applied": 1,
        "skipped": [
            {"itemId": ids[0], "code": "changeset.invalid_item"},
            {"itemId": ids[2], "code": "changeset.dependency_skipped"},
            {"itemId": ids[3], "code": "changeset.invalid_item"},
        ],
    }
    created = await elements_by_name(db, steel)
    assert set(created) == {"Plant", "Site"}
    assert created["Plant"].parent_id is None
    assert created["Plant"].revision == 1
    assert created["Site"].parent_id == plant.id


async def test_merge_update_merges_synonyms(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    ladle = element(
        steel,
        "entity_type",
        "Ladle",
        "钢包",
        synonyms=[{"lang": "zh", "text": "钢包"}],
    )
    weight = element(steel, "property", "weight", "重量", domain_id=ladle.id, datatype="decimal")
    await add_elements(db, ladle, weight)
    items = [
        proposal(
            "update",
            "entity_type",
            target=ladle.id,
            definition_zh="盛放钢水的容器。",
            synonyms=[
                {"lang": "zh", "text": "钢包"},
                {"lang": "zh", "text": "盛钢桶"},
                {"lang": "en", "text": "Ladle"},
            ],
        ),
        proposal("update", "property", target=weight.id, unit="t", required=True),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    first, second = await change_set_items(client, change_set_id)

    result = await accept_and_merge(client, change_set_id)

    assert result == {"applied": 2, "skipped": []}
    updated = await elements_by_name(db, steel)
    assert updated["Ladle"].synonyms == [
        {"lang": "zh", "text": "钢包"},
        {"lang": "zh", "text": "盛钢桶"},
        {"lang": "en", "text": "Ladle"},
    ]
    assert updated["Ladle"].definition_zh == "盛放钢水的容器。"
    assert updated["Ladle"].label_zh == "钢包"
    assert updated["Ladle"].revision == 2
    assert updated["weight"].unit == "t"
    assert updated["weight"].required is True
    assert updated["weight"].datatype == "decimal"
    assert first["before"]["synonyms"] == [{"lang": "zh", "text": "钢包"}]
    assert second["before"]["datatype"] == "decimal"
    merged = await change_set_items(client, change_set_id)
    assert [item["appliedElementId"] for item in merged] == [str(ladle.id), str(weight.id)]
