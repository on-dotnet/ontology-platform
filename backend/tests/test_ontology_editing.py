"""Manual saves, their review boundary, and impact on the working ontology."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.editing import cascade_items
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology
from support import csrf_headers
from test_ontology_expert import small_ontology
from test_ontology_support import add_elements, add_ontology, element, elements_by_name, sign_in


async def save(
    client: AsyncClient, ontology: Ontology, *items: dict[str, Any], apply: bool = True
) -> Response:
    return await client.post(
        f"/api/ontologies/{ontology.id}/edits",
        json={"items": items, "apply": apply},
        headers=csrf_headers(client),
    )


def create(kind: str, local_name: str, label: str, **fields: Any) -> dict[str, Any]:
    return {
        "op": "create",
        "kind": kind,
        "tempRef": f"new:{local_name}",
        "fields": {"localName": local_name, "labelZh": label, **fields},
    }


def edit(op: str, target: Element, **fields: Any) -> dict[str, Any]:
    return {
        "op": op,
        "kind": target.kind,
        "targetElementId": str(target.id),
        "targetRevision": target.revision,
        "fields": fields,
    }


async def test_stale_batch_leaves_no_change_set(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次", revision=2)
    await add_elements(db, heat)
    stale = edit("update", heat, labelZh="新名称") | {"targetRevision": 1}

    response = await save(client, ontology, create("entity_type", "Slab", "板坯"), stale)

    assert response.status_code == 409
    assert response.json()["code"] == "element.stale"
    assert await db.scalar(select(ChangeSet.id).where(ChangeSet.ontology_id == ontology.id)) is None
    rows = await elements_by_name(db, ontology)
    assert set(rows) == {"Heat"}
    assert rows["Heat"].label_zh == "炉次"


async def test_admin_applies_four_linked_creates(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    entity = "new:Heat"
    items = [
        create("entity_type", "Heat", "炉次"),
        create("relation_type", "follows", "接续", domainRef=entity, rangeRef=entity),
        create("property", "weight", "重量", domainRef=entity, datatype="decimal"),
        create(
            "constraint",
            "MeasuredHeat",
            "炉次称重",
            domainRef=entity,
            rules=[{"pathRef": "new:weight", "minCount": 1}],
        ),
    ]

    response = await save(client, ontology, *items)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["merged"] is True
    assert result["merge"] == {"applied": 4, "skipped": []}
    change_set = await db.get(ChangeSet, UUID(result["changeSetId"]))
    assert change_set is not None
    assert (change_set.source, change_set.status, change_set.title) == (
        "manual",
        "merged",
        "手工修改：炉次 等 4 项",
    )
    detail = await client.get(f"/api/change-sets/{change_set.id}")
    assert detail.status_code == 200
    for item in detail.json()["items"]:
        assert item["confidence"] is None
        assert item["evidence"] == []
        assert item["decision"] == "accepted"
    rows = await elements_by_name(db, ontology)
    assert set(rows) == {"Heat", "follows", "weight", "MeasuredHeat"}
    assert rows["follows"].domain_id == rows["follows"].range_id == rows["Heat"].id
    assert rows["weight"].domain_id == rows["Heat"].id
    constraint = rows["MeasuredHeat"]
    assert constraint.domain_id == rows["Heat"].id
    assert constraint.rules is not None
    assert constraint.rules[0]["pathId"] == str(rows["weight"].id)


@pytest.mark.parametrize(
    ("role", "mode", "apply"),
    [
        (Role.EDITOR, "single", True),
        (Role.REVIEWER, "separate", True),
        (Role.ADMIN, "single", False),
    ],
)
async def test_save_for_review(
    app: FastAPI, client: AsyncClient, db: AsyncSession, role: Role, mode: str, apply: bool
) -> None:
    app.state.settings.review_mode = mode
    await sign_in(client, db, role)
    ontology = await add_ontology(db)

    response = await save(client, ontology, create("entity_type", "Heat", "炉次"), apply=apply)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["merged"] is False
    assert result["merge"] is None
    detail = await client.get(f"/api/change-sets/{result['changeSetId']}")
    assert detail.status_code == 200
    change_set = detail.json()
    assert (change_set["status"], change_set["title"]) == ("open", "手工修改：炉次")
    assert [item["decision"] for item in change_set["items"]] == ["pending"]
    assert await elements_by_name(db, ontology) == {}


async def test_name_collisions_include_retired_and_batch_iris(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    retired = element(ontology, "entity_type", "Heat", "炉次", status="deprecated")
    # Imported: its explicit IRI is what a hand-made "Mill" would get.
    imported = element(ontology, "entity_type", "Mill2", "轧机", iri=ontology.base_iri + "Mill")
    await add_elements(db, retired, imported)
    first = create("entity_type", "Slab", "板坯")
    for items in (
        [create("entity_type", "Heat", "新炉次")],
        [create("entity_type", "Mill", "轧机")],
        [first, first | {"tempRef": "new:second"}],
    ):
        response = await save(client, ontology, *items, apply=False)
        assert response.status_code == 409
        assert response.json()["code"] == "element.name_taken"
    # Only imports bring their own IRI: it would skip the naming rules.
    own_iri = await save(
        client,
        ontology,
        create("entity_type", "Other", "其他", iri="urn:x:Other"),
        apply=False,
    )
    assert own_iri.status_code == 422
    assert own_iri.json()["detail"] == "Item 1: iri is set by imports only."
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_invalid_edit_reports_the_item_and_field(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    response = await save(
        client,
        ontology,
        create("entity_type", "Slab", "板坯"),
        create("entity_type", "Heat", "炉次", datatype="decimal"),
        apply=False,
    )
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "changeset.invalid_edit"
    assert problem["detail"].startswith("Item 2:")
    assert "datatype" in problem["detail"]
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_target_scope_kind_and_status(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    other = await add_ontology(db, "other")
    active = element(ontology, "entity_type", "Heat", "炉次")
    retired = element(ontology, "entity_type", "Slab", "板坯", status="deprecated")
    foreign = element(other, "entity_type", "Heat", "炉次")
    await add_elements(db, active, retired, foreign)
    for item, status, code in (
        (edit("delete", foreign), 404, "element.not_found"),
        (edit("delete", active) | {"kind": "property"}, 404, "element.not_found"),
        (edit("update", retired, labelZh="新名"), 409, "element.stale"),
        (edit("delete", retired), 409, "element.stale"),
        (edit("restore", active), 409, "element.stale"),
    ):
        response = await save(client, ontology, item)
        assert response.status_code == status
        assert response.json()["code"] == code
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_restoring_and_editing_together(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次", status="deprecated", revision=4)
    await add_elements(db, heat)

    response = await save(client, ontology, edit("restore", heat, labelZh="熔炼炉次"))

    assert response.status_code == 200, response.text
    assert response.json()["merge"] == {"applied": 1, "skipped": []}
    await db.refresh(heat)
    assert (heat.status, heat.revision, heat.label_zh) == ("active", 5, "熔炼炉次")


async def test_skip_rolls_back_an_otherwise_valid_create(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)

    retired = element(ontology, "entity_type", "Old", "旧", status="deprecated")
    await add_elements(db, retired)

    # Referring to what the same save deletes is refused before anything is written.
    conflict = await save(
        client,
        ontology,
        create("entity_type", "Child", "子类型", parentRef=str(heat.id)),
        edit("delete", heat),
    )
    assert conflict.status_code == 422
    assert conflict.json()["detail"] == "Item 1: it refers to an element this save deletes."
    # A reference the merge refuses (a deleted type) rolls the whole save back.
    response = await save(
        client,
        ontology,
        create("entity_type", "Slab", "板坯"),
        create("property", "weight", "重量", domainRef=str(retired.id), datatype="decimal"),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "changeset.invalid_item"
    assert response.json()["detail"].startswith("Item 2 ")
    assert await db.scalar(select(ChangeSet.id)) is None
    rows = await elements_by_name(db, ontology)
    assert set(rows) == {"Heat", "Old"}
    assert (rows["Heat"].revision, rows["Heat"].status) == (1, "active")


async def test_axiom_save_checks_representation_and_normalizes_proposal(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await small_ontology(client, db)

    def axiom(turtle: str) -> dict[str, Any]:
        return {"kind": "axiom", "op": "create", "fields": {"turtle": turtle}}

    invalid = await save(client, ontology, axiom("ex:A rdfs:subClassOf ex:B ."))
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "axiom.maps_to_element"
    normalized = "ex:A owl:disjointWith ex:B ."
    created = await save(client, ontology, axiom("ex:A    owl:disjointWith ex:B ."))
    assert created.status_code == 200, created.text
    assert created.json()["merge"] == {"applied": 1, "skipped": []}
    stored = await db.scalar(select(Element).where(Element.turtle == normalized))
    assert stored is not None
    rewritten = await save(client, ontology, edit("update", stored, turtle=normalized + "   "))
    assert rewritten.status_code == 200, rewritten.text
    assert rewritten.json()["merge"] == {"applied": 1, "skipped": []}
    detail = await client.get(f"/api/change-sets/{rewritten.json()['changeSetId']}")
    assert detail.json()["items"][0]["proposed"] == {"turtle": normalized}
    await db.refresh(stored)
    assert (stored.turtle, stored.revision) == (normalized, 2)


@pytest.fixture
async def linked_ontology(db: AsyncSession) -> tuple[Ontology, dict[str, Element]]:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    slab = element(ontology, "entity_type", "Slab", "板坯", parent_id=heat.id)
    retired = element(ontology, "entity_type", "Old", "旧", parent_id=heat.id, status="deprecated")
    weight = element(ontology, "property", "weight", "重量", domain_id=heat.id, datatype="decimal")
    width = element(ontology, "property", "width", "宽度", domain_id=slab.id, datatype="decimal")
    casts = element(ontology, "relation_type", "casts", "浇铸", domain_id=heat.id, range_id=slab.id)
    inverse = element(
        ontology,
        "relation_type",
        "castBy",
        "来源",
        domain_id=slab.id,
        range_id=slab.id,
        inverse_id=casts.id,
    )
    target = element(
        ontology, "constraint", "Direct", "Z", domain_id=heat.id, rules=[{"pathId": str(width.id)}]
    )
    mixed = element(
        ontology,
        "constraint",
        "Mixed",
        "B",
        domain_id=slab.id,
        rules=[
            {"pathId": str(inverse.id), "classId": str(heat.id)},
            {"pathId": str(weight.id), "minCount": 1},
            {"pathId": str(width.id), "minCount": 2},
        ],
    )
    empty = element(
        ontology,
        "constraint",
        "Empty",
        "C",
        domain_id=slab.id,
        rules=[{"pathId": str(casts.id)}, {"pathId": str(weight.id)}],
    )
    axiom = element(
        ontology,
        "axiom",
        "",
        "",
        turtle="steel:Slab owl:disjointWith steel:Heat .",
        subject_id=slab.id,
        revision=3,
    )
    axiom.local_name = axiom.label_zh = None
    await add_elements(db, heat, slab, retired, weight, width, casts, inverse, target, mixed, empty)
    await add_elements(db, axiom)
    rows = await elements_by_name(db, ontology)
    rows["axiom"] = axiom
    return ontology, rows


def test_single_root_cascade_carries_revisions_and_object_iri_mentions(
    linked_ontology: tuple[Ontology, dict[str, Element]],
) -> None:
    ontology, rows = linked_ontology
    root = rows["Heat"]

    proposals = cascade_items(ontology, list(rows.values()), [root])

    deletes = ["weight", "casts", "Direct", "axiom"]
    # Empty loses all its rules but stays: an empty rule list is a valid constraint.
    updates = ["Slab", "Mixed", "castBy", "Empty"]
    expected = {
        (op, rows[name].id, rows[name].revision)
        for op, names in (("delete", deletes), ("update", updates))
        for name in names
    }
    assert len(proposals) == len(expected)
    actual = {(item.op, item.target_element_id, item.target_revision) for item in proposals}
    assert actual == expected


async def test_cascade_applies_once_per_target(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology

    response = await save(
        client,
        ontology,
        edit("delete", rows["Heat"]),
        edit("delete", rows["weight"]),
        edit("update", rows["Slab"], labelZh="连铸板坯"),
    )

    assert response.status_code == 200, response.text
    removed = {"Heat", "weight", "casts", "Direct", "axiom"}
    updated = {"Slab", "Mixed", "castBy", "Empty"}
    assert response.json()["merge"] == {"applied": len(removed | updated), "skipped": []}
    detail = await client.get(f"/api/change-sets/{response.json()['changeSetId']}")
    assert detail.status_code == 200
    items = detail.json()["items"]
    assert {item["targetElementId"] for item in items} == {
        str(rows[name].id) for name in removed | updated
    }
    for name in removed | updated:
        row = rows[name]
        await db.refresh(row)
        assert row.revision == (4 if name == "axiom" else 2)
        assert row.status == ("deprecated" if name in removed else "active")
    assert (rows["Slab"].parent_id, rows["Slab"].label_zh) == (None, "连铸板坯")
    assert rows["castBy"].inverse_id is None
    assert rows["Mixed"].rules == [{"pathId": str(rows["width"].id), "minCount": 2}]
    assert rows["Empty"].rules == []


async def test_viewer_reads_sorted_direct_impact_and_cannot_save(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology, rows = linked_ontology
    elements_url = f"/api/ontologies/{ontology.id}/elements"
    response = await client.get(f"{elements_url}/{rows['Heat'].id}/impact")

    assert response.status_code == 200
    impact = response.json()
    assert impact["elementId"] == str(rows["Heat"].id)
    assert impact["inverse"] is None
    for group, names in (
        ("subtypes", ["Slab"]),
        ("relations", ["casts"]),
        ("properties", ["weight"]),
        ("constraints", ["Mixed", "Direct"]),
        ("axioms", ["axiom"]),
    ):
        assert [ref["id"] for ref in impact[group]] == [str(rows[name].id) for name in names]
    assert impact["subtypes"][0] == {
        "id": str(rows["Slab"].id),
        "kind": "entity_type",
        "label": "板坯",
        "iri": ontology.base_iri + "Slab",
    }
    assert impact["axioms"][0]["label"] == rows["axiom"].turtle
    assert impact["axioms"][0]["iri"] is None
    # Everything a delete would change, beyond the direct references.
    cascade = {(change["op"], change["element"]["id"]) for change in impact["cascade"]}
    assert cascade == {
        *(("delete", str(rows[name].id)) for name in ("weight", "casts", "Direct", "axiom")),
        *(("update", str(rows[name].id)) for name in ("Slab", "Mixed", "castBy", "Empty")),
    }
    for name, partner in (("casts", "castBy"), ("castBy", "casts")):
        result = await client.get(f"{elements_url}/{rows[name].id}/impact")
        assert result.status_code == 200
        assert result.json()["inverse"]["id"] == str(rows[partner].id)
    missing = await client.get(f"{elements_url}/{uuid4()}/impact")
    assert missing.status_code == 404
    assert missing.json()["code"] == "element.not_found"
    unknown = await client.get(f"/api/ontologies/{uuid4()}/elements/{rows['Heat'].id}/impact")
    assert unknown.status_code == 404
    assert unknown.json()["code"] == "ontology.not_found"
    refused = await save(client, ontology, edit("delete", rows["Heat"]))
    assert refused.status_code == 403
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_independent_deletes_empty_a_constraint_once(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology
    shape_axiom = element(
        ontology,
        "axiom",
        "",
        "",
        turtle="steel:Empty rdfs:seeAlso steel:Mixed .",
        subject_id=rows["Empty"].id,
    )
    shape_axiom.local_name = shape_axiom.label_zh = None
    await add_elements(db, shape_axiom)

    response = await save(
        client, ontology, edit("delete", rows["casts"]), edit("delete", rows["weight"])
    )

    assert response.status_code == 200, response.text
    detail = await client.get(f"/api/change-sets/{response.json()['changeSetId']}")
    assert detail.status_code == 200
    empty_ops = [
        item["op"]
        for item in detail.json()["items"]
        if item["targetElementId"] == str(rows["Empty"].id)
    ]
    assert empty_ops == ["update"]
    await db.refresh(rows["Empty"])
    await db.refresh(shape_axiom)
    # Both deletes took its rules; it stays, so does the axiom about it.
    assert (rows["Empty"].status, rows["Empty"].rules, rows["Empty"].revision) == ("active", [], 2)
    assert (shape_axiom.status, shape_axiom.revision) == ("active", 1)
    await db.refresh(rows["Mixed"])
    assert rows["Mixed"].rules == [
        {"pathId": str(rows["castBy"].id), "classId": str(rows["Heat"].id)},
        {"pathId": str(rows["width"].id), "minCount": 2},
    ]


async def test_a_reference_moved_away_in_the_same_save_stays(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology
    other = element(ontology, "entity_type", "Other", "其他")
    await add_elements(db, other)

    response = await save(
        client,
        ontology,
        edit("delete", rows["Heat"]),
        edit("update", rows["Slab"], parentRef=str(other.id)),
        edit("update", rows["weight"], domainRef=str(rows["Slab"].id)),
    )

    assert response.status_code == 200, response.text
    for name in ("Slab", "weight"):
        await db.refresh(rows[name])
    # Not cleared by the cascade, and not deleted with Heat: the user moved them away.
    assert rows["Slab"].parent_id == other.id
    assert (rows["weight"].status, rows["weight"].domain_id) == ("active", rows["Slab"].id)


async def test_a_save_cannot_keep_what_it_deletes(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology
    heat = edit("delete", rows["Heat"])
    for items, detail in (
        (
            [heat, edit("update", rows["Slab"], parentRef=str(rows["Heat"].id))],
            "Item 2: it refers to an element this save deletes.",
        ),
        (
            [heat, edit("update", rows["weight"], labelZh="称重")],
            "Item 2: another item of this save deletes this element along with its own.",
        ),
        (
            [
                edit("update", rows["Slab"], labelZh="甲"),
                edit("update", rows["Slab"], labelZh="乙"),
            ],
            "Item 2: item 1 already changes this element.",
        ),
    ):
        response = await save(client, ontology, *items)
        assert response.status_code == 422
        assert (response.json()["code"], response.json()["detail"]) == (
            "changeset.invalid_edit",
            detail,
        )
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_a_new_or_rewritten_axiom_cannot_mention_what_the_save_deletes(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology
    other = element(ontology, "entity_type", "Other", "其他")
    await add_elements(db, other)
    disjoint = "<http://www.w3.org/2002/07/owl#disjointWith>"
    heat, other_iri = (f"<{ontology.base_iri}{name}>" for name in ("Heat", "Other"))
    turtle = f"{heat} {disjoint} {other_iri} ."
    detail = "Item 2: it refers to an element this save deletes."
    for item in (
        {"kind": "axiom", "op": "create", "fields": {"turtle": turtle}},
        edit("update", rows["axiom"], turtle=turtle),
    ):
        response = await save(client, ontology, edit("delete", other), item)
        assert response.status_code == 422, response.text
        assert (response.json()["code"], response.json()["detail"]) == (
            "changeset.invalid_edit",
            detail,
        )
    assert await db.scalar(select(ChangeSet.id)) is None
    await db.refresh(other)
    await db.refresh(rows["axiom"])
    assert (other.status, rows["axiom"].turtle) == (
        "active",
        "steel:Slab owl:disjointWith steel:Heat .",
    )


async def test_rewriting_an_axiom_away_from_a_deleted_subject_is_not_a_conflict(
    client: AsyncClient, db: AsyncSession, linked_ontology: tuple[Ontology, dict[str, Element]]
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology, rows = linked_ontology
    other = element(ontology, "entity_type", "Other", "其他")
    await add_elements(db, other)
    disjoint = "<http://www.w3.org/2002/07/owl#disjointWith>"
    heat, other_iri = (f"<{ontology.base_iri}{name}>" for name in ("Heat", "Other"))
    # The axiom was about Slab, which this save deletes; its new text is about Heat.
    assert rows["axiom"].subject_id == rows["Slab"].id

    response = await save(
        client,
        ontology,
        edit("delete", rows["Slab"]),
        edit("update", rows["axiom"], turtle=f"{heat} {disjoint} {other_iri} ."),
    )

    assert response.status_code == 200, response.text
    await db.refresh(rows["axiom"])
    await db.refresh(rows["Slab"])
    assert (rows["Slab"].status, rows["axiom"].status) == ("deprecated", "active")
    assert rows["axiom"].subject_id == rows["Heat"].id
    assert "Other" in (rows["axiom"].turtle or "")


async def test_restoring_an_axiom_checks_it_again(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await small_ontology(client, db)
    retired = element(
        ontology,
        "axiom",
        "",
        "",
        turtle="ex:A rdfs:subClassOf ex:B .",
        status="deprecated",
    )
    retired.local_name = retired.label_zh = None
    await add_elements(db, retired)

    response = await save(client, ontology, edit("restore", retired))

    assert response.status_code == 422
    assert response.json()["code"] == "axiom.maps_to_element"
