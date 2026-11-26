"""Releases: publish checks, versions, immutable snapshots, stored Turtle and activation."""

import hashlib
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Ontology, Release
from ontology_platform.modules.ontology.schemas import Element
from ontology_platform.modules.ontology.turtle import OntologyHeader, export_turtle
from support import PROBLEM_JSON, csrf_headers
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    element,
    open_change_set,
    proposal,
    publish,
    sign_in,
)

RELEASE_FIELDS = {
    "id",
    "ontologyId",
    "version",
    "title",
    "notes",
    "elementCount",
    "bindingCount",
    "isActive",
    "createdBy",
    "createdAt",
}


async def seed_steel(client: AsyncClient, db: AsyncSession) -> Ontology:
    """An ontology with Slab, Heat and a relation between them, merged from a change set."""
    steel = await add_ontology(db)
    items = [
        proposal("create", "entity_type", temp_ref="new:Slab", local_name="Slab", label_zh="板坯"),
        proposal("create", "entity_type", temp_ref="new:Heat", local_name="Heat", label_zh="炉次"),
        proposal(
            "create",
            "relation_type",
            local_name="castFrom",
            label_zh="浇铸自",
            domain_ref="new:Slab",
            range_ref="new:Heat",
        ),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)
    assert (await accept_and_merge(client, change_set_id))["applied"] == 3
    return steel


async def release_rows(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(Release)) or 0


async def test_publish_checks_list_every_problem(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    alpha = element(steel, "entity_type", "Alpha", "甲")
    beta = element(steel, "entity_type", "Beta", "乙", parent_id=alpha.id)
    gone = element(steel, "entity_type", "Gone", "废弃", status="deprecated")
    orphan = element(steel, "entity_type", "Orphan", "孤儿", parent_id=gone.id)
    badly_named = element(steel, "entity_type", "slab", "板坯")
    unlabeled = element(steel, "entity_type", "Coil", "  ")
    to_gone = element(steel, "relation_type", "toGone", "去", domain_id=alpha.id, range_id=gone.id)
    back = element(steel, "relation_type", "back", "来", domain_id=gone.id, range_id=beta.id)
    weight = element(steel, "property", "weight", "重量", domain_id=gone.id, datatype="decimal")
    retired = element(
        steel,
        "property",
        "Retired",
        "",
        domain_id=gone.id,
        datatype="decimal",
        status="deprecated",
    )
    await add_elements(db, alpha, beta, gone, orphan, badly_named, unlabeled)
    await add_elements(db, to_gone, back, weight, retired)
    alpha.parent_id = beta.id
    await db.commit()
    await sign_in(client, db, Role.REVIEWER)

    response = await publish(client, steel)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert set(problem) == {"type", "title", "status", "detail", "code", "problems"}
    assert problem["code"] == "release.invalid"
    assert problem["status"] == 422
    found = {(item["code"], item["elementId"]) for item in problem["problems"]}
    assert found == {
        ("release.cyclic_hierarchy", str(alpha.id)),
        ("release.cyclic_hierarchy", str(beta.id)),
        ("release.invalid_parent", str(orphan.id)),
        ("release.invalid_local_name", str(badly_named.id)),
        ("release.missing_label", str(unlabeled.id)),
        ("release.invalid_range", str(to_gone.id)),
        ("release.invalid_domain", str(back.id)),
        ("release.invalid_domain", str(weight.id)),
    }
    assert all(set(item) == {"code", "elementId", "message"} for item in problem["problems"])
    assert await release_rows(db) == 0


async def test_publish_increments_the_version(client: AsyncClient, db: AsyncSession) -> None:
    steel = await seed_steel(client, db)

    first = await publish(client, steel, "首版")
    second = await client.post(
        f"/api/ontologies/{steel.id}/releases",
        json={"title": "第二版", "notes": "  补充关系  "},
        headers=csrf_headers(client),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    v1, v2 = first.json(), second.json()
    assert set(v1) == RELEASE_FIELDS
    assert (v1["version"], v2["version"]) == (1, 2)
    assert v1["elementCount"] == 3
    assert v1["isActive"] is True
    assert v1["createdBy"] is not None
    assert v2["notes"] == "补充关系"
    listed = (await client.get(f"/api/ontologies/{steel.id}/releases")).json()
    assert [(item["version"], item["isActive"]) for item in listed] == [(2, True), (1, False)]
    summary = (await client.get(f"/api/ontologies/{steel.id}")).json()
    assert summary["activeReleaseId"] == v2["id"]
    assert summary["activeReleaseVersion"] == 2
    fetched = await client.get(f"/api/releases/{v1['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == {**v1, "isActive": False}
    statement = select(AuditEvent).where(AuditEvent.action == "release.published")
    events = (await db.scalars(statement.order_by(AuditEvent.id))).all()
    assert [event.target_id for event in events] == [v1["id"], v2["id"]]
    assert events[0].detail == {
        "ontologyId": str(steel.id),
        "version": 1,
        "elementCount": 3,
        "bindingCount": 0,
    }


async def test_release_export_is_the_stored_turtle(client: AsyncClient, db: AsyncSession) -> None:
    steel = await seed_steel(client, db)
    release_id = (await publish(client, steel)).json()["id"]

    response = await client.get(f"/api/releases/{release_id}/export", params={"format": "turtle"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/turtle; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="steel-v1.ttl"'
    release = await db.get(Release, UUID(release_id))
    assert release is not None
    assert response.text == release.turtle
    assert release.turtle_sha256 == hashlib.sha256(response.content).hexdigest()
    assert release.element_count == len(release.snapshot) == 3
    assert {item["localName"] for item in release.snapshot} == {"Slab", "Heat", "castFrom"}
    assert 'owl:versionInfo "1"' in release.turtle
    header = OntologyHeader(
        key=steel.key,
        name=steel.name,
        description=steel.description,
        base_iri=steel.base_iri,
    )
    snapshot = [Element.model_validate(item) for item in release.snapshot]
    regenerated = export_turtle(header, snapshot, version=1, created=release.created_at)
    assert regenerated == release.turtle


async def test_snapshot_is_immutable(client: AsyncClient, db: AsyncSession) -> None:
    steel = await seed_steel(client, db)
    v1 = (await publish(client, steel)).json()
    before = (await client.get(f"/api/releases/{v1['id']}/export")).content
    stored = await db.get(Release, UUID(v1["id"]))
    assert stored is not None
    snapshot_before = list(stored.snapshot)
    slab_id = next(item["id"] for item in snapshot_before if item["localName"] == "Slab")
    update = proposal("update", "entity_type", target=UUID(slab_id), label_zh="连铸坯")
    change_set_id = await open_change_set(db, steel, [update])
    assert (await accept_and_merge(client, change_set_id))["applied"] == 1

    after = (await client.get(f"/api/releases/{v1['id']}/export")).content
    working = (await client.get(f"/api/ontologies/{steel.id}/export")).text
    v2 = (await publish(client, steel)).json()
    latest = (await client.get(f"/api/releases/{v2['id']}/export")).text

    assert after == before
    assert "连铸坯" not in before.decode()
    assert "连铸坯" in working
    assert "连铸坯" in latest
    reloaded = await db.get(Release, UUID(v1["id"]), populate_existing=True)
    assert reloaded is not None
    assert reloaded.snapshot == snapshot_before
    assert next(item for item in reloaded.snapshot if item["id"] == slab_id)["labelZh"] == "板坯"


async def test_activate_rolls_back_to_an_older_release(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await seed_steel(client, db)
    v1 = (await publish(client, steel)).json()
    v2 = (await publish(client, steel)).json()

    response = await client.post(
        f"/api/releases/{v1['id']}/activate",
        headers=csrf_headers(client),
    )
    missing = await client.post(f"/api/releases/{uuid4()}/activate", headers=csrf_headers(client))

    assert response.status_code == 200
    assert response.json()["isActive"] is True
    assert response.json()["version"] == 1
    summary = (await client.get(f"/api/ontologies/{steel.id}")).json()
    assert summary["activeReleaseId"] == v1["id"]
    assert summary["activeReleaseVersion"] == 1
    listed = (await client.get(f"/api/ontologies/{steel.id}/releases")).json()
    assert [(item["version"], item["isActive"]) for item in listed] == [(2, False), (1, True)]
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "release.activated"))
    assert event is not None
    assert event.target_id == v1["id"]
    assert event.detail == {
        "ontologyId": str(steel.id),
        "version": 1,
        "previousReleaseId": v2["id"],
        "bindingCount": 0,
    }
    assert missing.status_code == 404
    assert missing.json()["code"] == "release.not_found"


async def test_empty_title_is_rejected(client: AsyncClient, db: AsyncSession) -> None:
    steel = await seed_steel(client, db)

    response = await publish(client, steel, "   ")

    assert response.status_code == 422
    assert response.json()["code"] == "validation.failed"
    assert await release_rows(db) == 0


async def test_an_empty_ontology_cannot_be_published(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await sign_in(client, db, Role.REVIEWER)

    response = await publish(client, steel)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "release.invalid"
    assert [(p["code"], p["elementId"]) for p in body["problems"]] == [("release.empty", None)]
    assert await release_rows(db) == 0
