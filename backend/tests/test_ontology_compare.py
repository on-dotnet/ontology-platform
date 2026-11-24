from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Ontology, Release
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in


async def comparison(
    client: AsyncClient, ontology: Ontology, source: str, target: str | None = None
) -> dict[str, Any]:
    params = {"from": source}
    if target is not None:
        params["to"] = target
    response = await client.get(f"/api/ontologies/{ontology.id}/compare", params=params)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def publish_id(client: AsyncClient, ontology: Ontology) -> str:
    response = await publish(client, ontology)
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def snapshot(
    db: AsyncSession, ontology: Ontology, version: int, rows: list[dict[str, Any]]
) -> str:
    release = Release(
        ontology_id=ontology.id,
        version=version,
        title=str(version),
        snapshot=rows,
        turtle="",
        turtle_sha256="0" * 64,
        element_count=len(rows),
        created_at=datetime.now(UTC),
    )
    db.add(release)
    await db.commit()
    return str(release.id)


async def test_viewer_compares_working_and_published_versions(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    old = element(ontology, "entity_type", "Old", "Old")
    child = element(ontology, "entity_type", "Child", "Child", parent_id=old.id)
    await add_elements(db, old, child)
    v1 = await publish_id(client, ontology)

    new = element(ontology, "entity_type", "New", "New")
    await add_elements(db, new)
    old.status = "deprecated"
    old.label_zh = "Retired"
    child.parent_id = new.id
    child.definition_en = "A child"
    await db.commit()
    v2 = await publish_id(client, ontology)
    await sign_in(client, db, Role.VIEWER)
    working = await comparison(client, ontology, v1)
    assert working["from"] == {"releaseId": v1, "version": 1}
    assert working["to"] == {"releaseId": None, "version": None}
    assert working["counts"] == {"breaking": 2, "review": 0, "compatible": 1}
    changes = working["changes"]
    assert [(c["elementId"], c["change"], c["level"]) for c in changes] == [
        (str(child.id), "changed", "breaking"),
        (str(old.id), "removed", "breaking"),
        (str(new.id), "added", "compatible"),
    ]
    assert changes[0]["fields"] == [
        {"field": "definitionEn", "before": None, "after": "A child"},
        {
            "field": "parentId",
            "before": {"id": str(old.id), "label": "Old"},
            "after": {"id": str(new.id), "label": "New"},
        },
    ]
    assert changes[1]["fields"] == changes[2]["fields"] == []
    assert changes[1]["label"] == "Old"

    old.status = "active"
    old.label_zh = "Old"
    await db.commit()
    assert await comparison(client, ontology, v1, v2) == working | {
        "to": {"releaseId": v2, "version": 2}
    }
    restored = await comparison(client, ontology, v2, "working")
    assert restored["changes"] == [
        {
            "elementId": str(old.id),
            "kind": "entity_type",
            "label": "Old",
            "iri": ontology.base_iri + "Old",
            "change": "restored",
            "level": "compatible",
            "fields": [],
        }
    ]
    before_deletion = await comparison(client, ontology, v1)
    assert str(old.id) not in [c["elementId"] for c in before_deletion["changes"]]
    same = await comparison(client, ontology, v1, v1)
    assert same["changes"] == []
    assert same["counts"] == {"breaking": 0, "review": 0, "compatible": 0}


async def test_field_levels_and_reference_values(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    missing = str(uuid4())
    synonym = {"lang": "en", "text": "Alias"}
    rule = {"pathId": str(uuid4()), "minCount": 1}
    cases: list[tuple[str, str, Any, Any, str]] = [
        ("entity_type", "labelZh", "甲", "乙", "compatible"),
        ("entity_type", "labelEn", None, "New", "compatible"),
        ("entity_type", "definitionZh", None, "定义", "compatible"),
        ("entity_type", "definitionEn", None, "Definition", "compatible"),
        ("entity_type", "synonyms", [], [synonym], "compatible"),
        ("entity_type", "parentId", None, missing, "breaking"),
        ("relation_type", "domainId", missing, None, "breaking"),
        ("relation_type", "rangeId", None, missing, "breaking"),
        ("relation_type", "inverseId", missing, None, "breaking"),
        ("property", "datatype", "integer", "decimal", "breaking"),
        ("property", "unit", "g", "kg", "breaking"),
        ("property", "required", False, True, "breaking"),
        ("property", "required", True, False, "compatible"),
        ("property", "multiple", False, True, "compatible"),
        ("property", "multiple", True, False, "breaking"),
        ("property", "autoShape", True, False, "review"),
        ("constraint", "rules", [], [rule], "review"),
        ("axiom", "turtle", "old", "a" * 130 + "\nsecond", "review"),
    ]
    left = []
    right = []
    for kind, field, before, after, _ in cases:
        row = {"id": str(uuid4()), "kind": kind, "localName": "Item", field: before}
        left.append(row)
        right.append(row | {field: after})
    v1 = await snapshot(db, ontology, 1, left)
    v2 = await snapshot(db, ontology, 2, right)
    result = await comparison(client, ontology, v1, v2)
    changes = {c["elementId"]: c for c in result["changes"]}
    assert len(changes) == len(cases)
    for row, (_, field, before, after, level) in zip(left, cases, strict=True):
        change = changes[row["id"]]
        assert (change["change"], change["level"]) == ("changed", level)
        ref = {"id": missing, "label": None}
        assert change["fields"] == [
            {
                "field": field,
                "before": ref if before == missing else before,
                "after": ref if after == missing else after,
            }
        ]
        if field == "turtle":
            assert (change["label"], change["iri"]) == ("a" * 120, None)


async def test_review_additions_and_removals_sort_by_kind(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    old = [
        {"id": str(uuid4()), "kind": "axiom", "turtle": "A\nold"},
        {"id": str(uuid4()), "kind": "constraint", "localName": "Check", "labelEn": "C"},
    ]
    v1 = await snapshot(db, ontology, 1, old)
    new = [
        row | {"id": str(uuid4()), "createdAt": datetime.now(UTC).isoformat(), **fields}
        for row, fields in zip(old, [{"turtle": "B\nnew"}, {"labelEn": "D"}], strict=True)
    ]
    v2 = await snapshot(db, ontology, 2, new)
    result = await comparison(client, ontology, v1, v2)
    assert result["counts"] == {"breaking": 0, "review": 4, "compatible": 0}
    assert [(c["label"], c["change"], c["level"]) for c in result["changes"]] == [
        ("C", "removed", "review"),
        ("D", "added", "review"),
        ("A", "removed", "review"),
        ("B", "added", "review"),
    ]


async def test_m1_snapshot_defaults_and_synonym_sets(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    synonyms = [{"lang": "en", "text": "A"}, {"lang": "zh", "text": "甲"}]
    item = element(ontology, "entity_type", "Alpha", "甲", synonyms=synonyms)
    await add_elements(db, item)
    legacy = {
        "id": str(item.id),
        "localName": "Alpha",
        "kind": "entity_type",
        "labelZh": "甲",
        "synonyms": [synonyms[1], synonyms[0], synonyms[0]],
        "required": False,
        "multiple": False,
        "createdAt": item.created_at.isoformat(),
    }
    v1 = await snapshot(db, ontology, 1, [legacy])
    assert (await comparison(client, ontology, v1))["changes"] == []
    item.status = "deprecated"
    await db.commit()
    changes = (await comparison(client, ontology, v1))["changes"]
    assert len(changes) == 1
    assert changes[0]["iri"] == ontology.base_iri + "Alpha"


async def test_scope_errors(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    other = await add_ontology(db, "other")
    own = await snapshot(db, ontology, 1, [])
    foreign = await snapshot(db, other, 1, [])
    for ontology_id, source, target, code in (
        (ontology.id, foreign, own, "release.not_found"),
        (ontology.id, own, foreign, "release.not_found"),
        (ontology.id, foreign, foreign, "release.not_found"),
        (uuid4(), own, own, "ontology.not_found"),
    ):
        response = await client.get(
            f"/api/ontologies/{ontology_id}/compare", params={"from": source, "to": target}
        )
        assert response.status_code == 404
        assert response.json()["code"] == code


async def test_created_at_release_instant_counts_as_added(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    v1 = await snapshot(db, ontology, 1, [])
    release = await db.get(Release, UUID(v1))
    assert release is not None
    imported = {
        "id": str(uuid4()),
        "kind": "entity_type",
        "localName": "Imported",
        "iri": "urn:example:imported",
        "createdAt": release.created_at.isoformat(),
    }
    v2 = await snapshot(db, ontology, 2, [imported])
    result = await comparison(client, ontology, v1, v2)
    assert result["changes"] == [
        {
            "elementId": imported["id"],
            "kind": "entity_type",
            "label": "Imported",
            "iri": "urn:example:imported",
            "change": "added",
            "level": "compatible",
            "fields": [],
        }
    ]


async def test_restored_constraints_and_axioms_need_review(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    ontology = await add_ontology(db)
    v1 = await snapshot(db, ontology, 1, [])
    earlier = "2020-01-01T00:00:00+00:00"
    back = [
        {"id": str(uuid4()), "kind": "entity_type", "localName": "Back", "createdAt": earlier},
        {"id": str(uuid4()), "kind": "constraint", "localName": "Check", "createdAt": earlier},
        {"id": str(uuid4()), "kind": "axiom", "turtle": "A", "createdAt": earlier},
    ]
    v2 = await snapshot(db, ontology, 2, back)
    result = await comparison(client, ontology, v1, v2)
    assert [(c["kind"], c["change"], c["level"]) for c in result["changes"]] == [
        ("constraint", "restored", "review"),
        ("axiom", "restored", "review"),
        ("entity_type", "restored", "compatible"),
    ]
