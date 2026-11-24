"""Ontologies, the working version (elements, search, provenance, graph, export) and the
service functions other modules call."""

import re
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import Ontology
from support import PROBLEM_JSON, csrf_headers
from test_ontology_support import (
    DOCUMENT_ID,
    accept_and_merge,
    add_elements,
    add_ontology,
    element,
    open_change_set,
    proposal,
    sign_in,
)

SUMMARY_FIELDS = {
    "id",
    "key",
    "name",
    "description",
    "baseIri",
    "ontologyIri",
    "entityTypeCount",
    "relationTypeCount",
    "propertyCount",
    "constraintCount",
    "axiomCount",
    "openChangeSetCount",
    "activeReleaseId",
    "activeReleaseVersion",
    "createdAt",
    "updatedAt",
}
ELEMENT_FIELDS = {
    "id",
    "ontologyId",
    "kind",
    "localName",
    "iri",
    "explicitIri",
    "labelZh",
    "labelEn",
    "definitionZh",
    "definitionEn",
    "synonyms",
    "parentId",
    "domainId",
    "rangeId",
    "inverseId",
    "datatype",
    "unit",
    "required",
    "multiple",
    "autoShape",
    "rules",
    "turtle",
    "subjectId",
    "flags",
    "status",
    "origin",
    "revision",
    "createdAt",
    "updatedAt",
}


async def create(client: AsyncClient, **body: str) -> dict[str, object]:
    response = await client.post("/api/ontologies", json=body, headers=csrf_headers(client))
    assert response.status_code == 201, response.text
    created: dict[str, object] = response.json()
    return created


async def test_create_ontology_with_key(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.EDITOR)

    created = await create(client, name="钢铁冶金", key="steel", description="  样例  ")

    assert set(created) == SUMMARY_FIELDS
    assert created["key"] == "steel"
    assert created["name"] == "钢铁冶金"
    assert created["description"] == "样例"
    assert created["baseIri"] == "https://example.org/ontology/steel#"
    assert created["entityTypeCount"] == 0
    assert created["openChangeSetCount"] == 0
    assert created["activeReleaseId"] is None
    assert created["activeReleaseVersion"] is None
    statement = select(AuditEvent).where(AuditEvent.action == "ontology.created")
    events = (await db.scalars(statement)).all()
    assert [event.target_id for event in events] == [created["id"]]
    assert events[0].actor_id is not None
    assert events[0].detail == {"key": "steel", "name": "钢铁冶金"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Steel Making", "steel-making"),
        ("  Hot-Rolled  Strip!! ", "hot-rolled-strip"),
        ("2024 Plant", "ontology-2024-plant"),
    ],
)
async def test_ascii_name_becomes_the_key(
    client: AsyncClient,
    db: AsyncSession,
    name: str,
    expected: str,
) -> None:
    await sign_in(client, db, Role.REVIEWER)

    created = await create(client, name=name)

    assert created["key"] == expected
    assert created["baseIri"] == f"https://example.org/ontology/{expected}#"


@pytest.mark.parametrize("name", ["钢铁冶金", "!!", "x"])
async def test_other_names_get_a_random_key(
    client: AsyncClient,
    db: AsyncSession,
    name: str,
) -> None:
    await sign_in(client, db, Role.ADMIN)

    first = await create(client, name=name)
    second = await create(client, name=name)

    for created in (first, second):
        assert re.fullmatch(r"ontology-[a-z0-9]{6}", str(created["key"]))
    assert first["key"] != second["key"]


async def test_key_conflict_is_409(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    await create(client, name="Steel")

    by_key = await client.post(
        "/api/ontologies",
        json={"name": "Other", "key": "steel"},
        headers=csrf_headers(client),
    )
    by_name = await client.post(
        "/api/ontologies",
        json={"name": "steel"},
        headers=csrf_headers(client),
    )

    for response in (by_key, by_name):
        assert response.status_code == 409
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.json()["code"] == "ontology.key_taken"
    assert len((await db.scalars(select(Ontology))).all()) == 1


@pytest.mark.parametrize("key", ["S", "steel_", "Steel", "1steel", "a", "-steel", "x" * 64])
async def test_invalid_key_is_rejected(client: AsyncClient, db: AsyncSession, key: str) -> None:
    await sign_in(client, db, Role.ADMIN)

    response = await client.post(
        "/api/ontologies",
        json={"name": "Steel", "key": key},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation.failed"


async def test_blank_name_is_rejected(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)

    response = await client.post(
        "/api/ontologies",
        json={"name": "   "},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422


async def test_list_and_detail_count_active_elements_and_open_change_sets(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    other = await add_ontology(db, key="other", name="其他")
    slab = element(steel, "entity_type", "Slab", "板坯")
    heat = element(steel, "entity_type", "Heat", "炉次")
    old = element(steel, "entity_type", "Old", "旧", status="deprecated")
    cast = element(steel, "relation_type", "castFrom", "浇铸", domain_id=slab.id, range_id=heat.id)
    width = element(steel, "property", "width", "宽度", domain_id=slab.id, datatype="decimal")
    await add_elements(db, slab, heat, old, cast, width)
    coil = proposal("create", "entity_type", local_name="Coil", label_zh="钢卷")
    await open_change_set(db, steel, [coil])
    await sign_in(client, db, Role.VIEWER)

    listed = await client.get("/api/ontologies")
    detail = await client.get(f"/api/ontologies/{steel.id}")

    assert listed.status_code == 200
    by_key = {summary["key"]: summary for summary in listed.json()}
    assert set(by_key) == {"steel", "other"}
    assert by_key["steel"] == detail.json()
    summary = detail.json()
    assert summary["entityTypeCount"] == 2
    assert summary["relationTypeCount"] == 1
    assert summary["propertyCount"] == 1
    assert summary["openChangeSetCount"] == 1
    assert by_key["other"]["entityTypeCount"] == 0
    assert by_key["other"]["id"] == str(other.id)


async def test_unknown_ids_are_404(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await sign_in(client, db, Role.VIEWER)
    missing = uuid4()

    cases = {
        f"/api/ontologies/{missing}": "ontology.not_found",
        f"/api/ontologies/{missing}/elements": "ontology.not_found",
        f"/api/ontologies/{missing}/graph": "ontology.not_found",
        f"/api/ontologies/{missing}/export?format=turtle": "ontology.not_found",
        f"/api/ontologies/{missing}/releases": "ontology.not_found",
        f"/api/ontologies/{steel.id}/elements/{missing}": "element.not_found",
        f"/api/change-sets/{missing}": "changeset.not_found",
        f"/api/releases/{missing}": "release.not_found",
        f"/api/releases/{missing}/export?format=turtle": "release.not_found",
    }
    for path, code in cases.items():
        response = await client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.json()["code"] == code, path


async def test_elements_list_filters_and_searches(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    ladle = element(
        steel,
        "entity_type",
        "Ladle",
        "钢包",
        label_en="Ladle",
        synonyms=[{"lang": "zh", "text": "盛钢桶"}],
    )
    heat = element(steel, "entity_type", "Heat", "炉次")
    weight = element(steel, "property", "netWeight", "净重", domain_id=ladle.id, datatype="date")
    await add_elements(db, ladle, heat, weight)
    await sign_in(client, db, Role.VIEWER)
    base = f"/api/ontologies/{steel.id}/elements"

    everything = (await client.get(base)).json()
    properties = (await client.get(base, params={"kind": "property"})).json()
    by_synonym = (await client.get(base, params={"q": "盛钢"})).json()
    by_label = (await client.get(base, params={"q": "LADLE"})).json()
    by_name = (await client.get(base, params={"q": "weight"})).json()
    bad_kind = await client.get(base, params={"kind": "rule"})
    axioms = await client.get(base, params={"kind": "axiom"})

    assert [item["localName"] for item in everything] == ["Heat", "Ladle", "netWeight"]
    assert set(everything[0]) == ELEMENT_FIELDS
    first = everything[1]
    assert first["iri"] == "https://example.org/ontology/steel#Ladle"
    assert first["synonyms"] == [{"lang": "zh", "text": "盛钢桶"}]
    assert [item["localName"] for item in properties] == ["netWeight"]
    assert properties[0]["domainId"] == str(ladle.id)
    assert properties[0]["datatype"] == "date"
    assert [item["localName"] for item in by_synonym] == ["Ladle"]
    assert [item["localName"] for item in by_label] == ["Ladle"]
    assert [item["localName"] for item in by_name] == ["netWeight"]
    assert bad_kind.status_code == 422
    assert axioms.status_code == 200
    assert axioms.json() == []


async def test_element_detail_shows_merged_provenance(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    slab = proposal("create", "entity_type", temp_ref="new:S", local_name="Slab", label_zh="板坯")
    change_set_id = await open_change_set(db, steel, [slab], title="识别：连铸规程.docx")
    await sign_in(client, db, Role.REVIEWER)
    await accept_and_merge(client, change_set_id)
    elements = (await client.get(f"/api/ontologies/{steel.id}/elements")).json()

    response = await client.get(f"/api/ontologies/{steel.id}/elements/{elements[0]['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == ELEMENT_FIELDS | {"provenance"}
    assert detail["origin"] == "ai"
    [source] = detail["provenance"]
    assert set(source) == {"changeSetId", "changeSetTitle", "itemId", "op", "mergedAt", "evidence"}
    assert source["changeSetId"] == str(change_set_id)
    assert source["changeSetTitle"] == "识别：连铸规程.docx"
    assert source["op"] == "create"
    [quote] = source["evidence"]
    assert set(quote) == {"id", "documentId", "chunkId", "quote", "charStart", "charEnd"}
    assert quote["documentId"] == str(DOCUMENT_ID)
    assert quote["quote"] == "原文引语"
    other = await add_ontology(db, key="other")
    wrong_ontology = await client.get(f"/api/ontologies/{other.id}/elements/{detail['id']}")
    assert wrong_ontology.status_code == 404
    assert wrong_ontology.json()["code"] == "element.not_found"


async def test_graph_has_types_relations_and_subclass_edges(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    equipment = element(steel, "entity_type", "Equipment", "装备")
    converter = element(steel, "entity_type", "Converter", "转炉", parent_id=equipment.id)
    heat = element(steel, "entity_type", "Heat", "炉次")
    gone = element(steel, "entity_type", "Gone", "废弃", status="deprecated")
    produced = element(
        steel,
        "relation_type",
        "producedIn",
        "冶炼于",
        domain_id=heat.id,
        range_id=converter.id,
    )
    dangling = element(steel, "relation_type", "goesTo", "去", domain_id=heat.id, range_id=gone.id)
    number = element(steel, "property", "heatNumber", "炉号", domain_id=heat.id, datatype="string")
    weight = element(steel, "property", "weight", "重量", domain_id=heat.id, datatype="decimal")
    await add_elements(db, equipment, converter, heat, gone, produced, dangling, number, weight)
    await sign_in(client, db, Role.VIEWER)

    response = await client.get(f"/api/ontologies/{steel.id}/graph")

    assert response.status_code == 200
    graph = response.json()
    nodes = {node["localName"]: node for node in graph["nodes"]}
    assert set(nodes) == {"Equipment", "Converter", "Heat"}
    assert set(nodes["Heat"]) == {"id", "label", "localName", "parentId", "propertyCount"}
    assert nodes["Heat"]["label"] == "炉次"
    assert nodes["Heat"]["propertyCount"] == 2
    assert nodes["Converter"]["propertyCount"] == 0
    assert nodes["Converter"]["parentId"] == str(equipment.id)
    assert nodes["Equipment"]["parentId"] is None
    edges = sorted(graph["edges"], key=lambda edge: edge["kind"])
    assert edges == [
        {
            "id": str(produced.id),
            "source": str(heat.id),
            "target": str(converter.id),
            "kind": "relation",
            "label": "冶炼于",
        },
        {
            "id": f"subclass:{converter.id}",
            "source": str(converter.id),
            "target": str(equipment.id),
            "kind": "subclass",
            "label": None,
        },
    ]


async def test_working_version_export_is_stable_turtle(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    slab = element(steel, "entity_type", "Slab", "板坯")
    hidden = element(steel, "entity_type", "Hidden", "隐藏", status="deprecated")
    await add_elements(db, slab, hidden)
    await sign_in(client, db, Role.VIEWER)
    path = f"/api/ontologies/{steel.id}/export"

    first = await client.get(path, params={"format": "turtle"})
    second = await client.get(path)
    unsupported = await client.get(path, params={"format": "rdfxml"})

    assert first.status_code == 200
    assert first.headers["content-type"] == "text/turtle; charset=utf-8"
    assert first.headers["content-disposition"] == 'attachment; filename="steel.ttl"'
    assert first.content == second.content
    text = first.text
    assert "steel:Slab a owl:Class" in text
    assert "Hidden" not in text
    assert "owl:versionInfo" not in text
    assert unsupported.status_code == 422


async def test_interface_functions_for_other_modules(db: AsyncSession) -> None:
    steel = await add_ontology(db)
    other = await add_ontology(db, key="other")
    slab = element(steel, "entity_type", "Slab", "板坯")
    width = element(steel, "property", "width", "宽度", domain_id=slab.id, datatype="decimal")
    old = element(steel, "entity_type", "Old", "旧", status="deprecated")
    coil = element(other, "entity_type", "Coil", "钢卷")
    await add_elements(db, slab, width, old, coil)
    heat = proposal("create", "entity_type", local_name="Heat", label_zh="炉次")
    await open_change_set(db, steel, [heat])

    found = await service.ontology_exists(db, steel.id)
    missing = await service.ontology_exists(db, uuid4())
    alignment = await service.list_alignment_elements(db, steel.id)

    assert found
    assert not missing
    assert [item.local_name for item in alignment] == ["Slab", "width"]
    assert await service.count_entity_types(db) == 2
    assert await service.count_open_change_sets(db) == 1
