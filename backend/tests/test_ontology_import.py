"""Importing OWL files through the API, reviewing and merging them, exporting again (spec 002,
section 4), and the merge rules M2 adds (delete, restore, constraints, axioms)."""

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient, Response
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDFS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import ChangeSet, Element
from ontology_platform.modules.ontology.rdf.reader import parse_document
from support import PROBLEM_JSON, csrf_headers
from test_ontology_rdf import OWL_FEATURES, STEEL_FILES, missing_from
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    change_set_items,
    decide,
    element,
    merge,
    open_change_set,
    proposal,
    publish,
    sign_in,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
STEEL = b"\n".join(path.read_bytes() for path in STEEL_FILES)
# What OWL API (Protégé) wrote back for each steel file.
STEEL_PROTEGE = b"\n".join(
    (FIXTURES / "owlapi" / f"steel-{path.name}").read_bytes() for path in STEEL_FILES
)
SOURCES = {path.name: path.read_bytes() for path in OWL_FEATURES}


def lost(source: bytes, exported: str) -> list[str]:
    return missing_from(parse_document(source), Graph().parse(data=exported, format="turtle"))


async def upload(
    client: AsyncClient,
    data: bytes,
    *,
    ontology_id: UUID | str | None = None,
    filename: str = "sample.ttl",
    name: str | None = None,
) -> Response:
    url = f"/api/ontologies/{ontology_id}/import" if ontology_id else "/api/ontologies/import"
    form = {"name": name} if name else {}
    return await client.post(
        url,
        files={"file": (filename, data, "text/turtle")},
        data=form,
        headers=csrf_headers(client),
    )


async def export(client: AsyncClient, ontology_id: str) -> str:
    response = await client.get(f"/api/ontologies/{ontology_id}/export")
    assert response.status_code == 200
    return response.text


async def import_and_merge(client: AsyncClient, data: bytes, **kwargs: Any) -> dict[str, Any]:
    response = await upload(client, data, **kwargs)
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    if result["changeSetId"]:
        merged = await accept_and_merge(client, result["changeSetId"])
        assert merged["skipped"] == []
    return result


# ---------- importing ----------


@pytest.mark.parametrize("name", sorted(SOURCES))
async def test_every_owl_feature_survives_import_merge_and_export(
    client: AsyncClient,
    db: AsyncSession,
    name: str,
) -> None:
    await sign_in(client, db, Role.ADMIN)
    source = SOURCES[name]

    result = await import_and_merge(client, source, filename=name)
    exported = await export(client, result["ontology"]["id"])

    assert lost(source, exported) == []
    again = await upload(client, exported.encode(), ontology_id=result["ontology"]["id"])
    assert again.status_code == 200
    assert again.json()["changeSetId"] is None
    assert await export(client, result["ontology"]["id"]) == exported


async def test_importing_the_steel_case(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.EDITOR)

    response = await upload(client, STEEL, filename="steel.ttl", name="钢铁样例")

    assert response.status_code == 201
    result = response.json()
    assert set(result) == {"ontology", "changeSetId", "counts", "warnings"}
    assert result["ontology"]["name"] == "钢铁样例"
    assert result["counts"]["create"] > 0
    assert result["counts"]["update"] == result["counts"]["delete"] == 0
    change_set = await db.get(ChangeSet, UUID(result["changeSetId"]))
    assert change_set is not None
    assert (change_set.source, change_set.status, change_set.title) == (
        "import",
        "open",
        "导入：steel.ttl",
    )
    items = await change_set_items(client, result["changeSetId"])
    kinds = {item["kind"] for item in items}
    assert {"entity_type", "relation_type", "property", "constraint", "axiom"} <= kinds
    shape = next(i for i in items if i["proposed"].get("iri") == "urn:synthetic:metals:CoilShape")
    (rule,) = [r for r in shape["proposed"]["rules"] if "minInclusive" in r]
    assert rule["minInclusive"] == {"lexical": "0", "datatype": "integer", "lang": None}

    await sign_in(client, db, Role.REVIEWER)
    await accept_and_merge(client, result["changeSetId"])
    listed = await client.get(
        f"/api/ontologies/{result['ontology']['id']}/elements",
        params={"kind": "constraint"},
    )
    constraints = listed.json()
    assert len(constraints) == 5
    coil = next(c for c in constraints if c["iri"] == "urn:synthetic:metals:CoilShape")
    assert coil["explicitIri"] is True
    assert coil["labelZh"] is None
    assert {r["pathId"] for r in coil["rules"]} <= {
        e["id"] for e in await all_elements(client, result)
    }
    exported = await export(client, result["ontology"]["id"])
    assert lost(STEEL, exported) == []


async def test_a_new_ontology_names_its_namespace_as_the_file_does(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, STEEL, filename="steel.ttl")
    ontology_id = result["ontology"]["id"]
    key = result["ontology"]["key"]

    exported = await export(client, ontology_id)
    assert "@prefix ex: <urn:synthetic:metals:> ." in exported
    assert f"@prefix {key}:" not in exported
    axioms = await client.get(f"/api/ontologies/{ontology_id}/elements", params={"kind": "axiom"})
    assert all(a["turtle"].startswith("ex:") for a in axioms.json()), axioms.json()

    # The name a namespace has stays: fragments stored earlier are written with it.
    renamed = STEEL.replace(b"ex:", b"m:")
    assert b"ex:" not in renamed
    again = await upload(client, renamed, ontology_id=ontology_id)
    assert again.json()["changeSetId"] is None
    assert await export(client, ontology_id) == exported


async def test_an_ontology_made_by_hand_keeps_its_own_prefix(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db, key="plant")
    base = ontology.base_iri.encode()
    data = b"@prefix p: <" + base + b"> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    data += b"p:Mill a owl:Class .\n"

    response = await upload(client, data, ontology_id=ontology.id)
    await accept_and_merge(client, response.json()["changeSetId"])

    exported = await export(client, str(ontology.id))
    assert f"@prefix plant: <{ontology.base_iri}> ." in exported
    assert "@prefix p:" not in exported


async def all_elements(client: AsyncClient, result: dict[str, Any]) -> list[dict[str, Any]]:
    response = await client.get(f"/api/ontologies/{result['ontology']['id']}/elements")
    elements: list[dict[str, Any]] = response.json()
    return elements


async def test_a_copy_saved_by_protege_changes_nothing(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, STEEL, filename="steel.ttl")

    response = await upload(client, STEEL_PROTEGE, ontology_id=result["ontology"]["id"])

    assert response.status_code == 200
    assert response.json()["changeSetId"] is None
    assert response.json()["warnings"] == []


async def test_importing_changes_into_an_ontology(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    first = b"""
        @prefix ex: <urn:t:> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:A a owl:Class ; rdfs:label "\xe7\x94\xb2"@zh .
        ex:B a owl:Class .
        ex:A rdfs:comment "note" .
    """
    second = b"""
        @prefix ex: <urn:t:> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:A a owl:Class ; rdfs:label "A"@en .
        ex:A owl:disjointWith ex:C . ex:C a owl:Class .
    """
    result = await import_and_merge(client, first)
    ontology_id = result["ontology"]["id"]

    changed = await upload(client, second, ontology_id=ontology_id)
    assert changed.status_code == 200
    counts = changed.json()["counts"]
    assert counts == {"create": 2, "update": 1, "delete": 2, "restore": 0}
    await accept_and_merge(client, changed.json()["changeSetId"])
    query = select(Element).where(Element.ontology_id == UUID(ontology_id))
    rows = (await db.scalars(query)).all()
    by_iri = {row.iri: row for row in rows if row.iri}
    assert by_iri["urn:t:B"].status == "deprecated"
    assert (by_iri["urn:t:A"].label_zh, by_iri["urn:t:A"].label_en) == (None, "A")

    back = await upload(client, first, ontology_id=ontology_id)
    items = await change_set_items(client, back.json()["changeSetId"])
    ops = sorted(item["op"] for item in items)
    assert ops == ["create", "delete", "delete", "restore", "update"]
    await accept_and_merge(client, back.json()["changeSetId"])
    assert (await upload(client, first, ontology_id=ontology_id)).json()["changeSetId"] is None


async def test_imported_ontologies_can_be_published(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SOURCES["21-advanced.ttl"])
    ontology = result["ontology"]

    response = await client.post(
        f"/api/ontologies/{ontology['id']}/releases",
        json={"title": "导入版"},
        headers=csrf_headers(client),
    )

    assert response.status_code == 201, response.text
    release = await client.get(f"/api/releases/{response.json()['id']}/export")
    graph = Graph().parse(data=release.text, format="turtle")
    assert (URIRef("urn:synthetic:m5:ontology"), OWL.imports, None) in graph
    assert ontology["ontologyIri"] == "urn:synthetic:m5:ontology"


async def test_import_problems(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.EDITOR)

    broken = await upload(client, b"@prefix ex: <urn:t:> .\nex:a ex:p ex:b ;\n ex:q .")
    owl_xml = await upload(
        client,
        b'<?xml version="1.0"?><Ontology xmlns="http://www.w3.org/2002/07/owl#"/>',
    )
    empty = await upload(client, b"# nothing\n")
    too_large = await upload(client, b"#" * (5 * 1024 * 1024 + 1))
    missing = await upload(client, b"<urn:a> <urn:b> <urn:c> .", ontology_id=UUID(int=1))

    assert broken.status_code == 422
    assert broken.headers["content-type"].startswith(PROBLEM_JSON)
    assert {k: broken.json()[k] for k in ("code", "line", "column")} == {
        "code": "import.parse_error",
        "line": 3,
        "column": None,
    }
    assert (owl_xml.status_code, owl_xml.json()["code"]) == (415, "import.unsupported_format")
    assert (empty.status_code, empty.json()["code"]) == (422, "import.empty")
    assert (too_large.status_code, too_large.json()["code"]) == (413, "import.too_large")
    assert (missing.status_code, missing.json()["code"]) == (404, "ontology.not_found")


async def test_import_needs_a_creator_role(client: AsyncClient, db: AsyncSession) -> None:
    anonymous = await client.post(
        "/api/ontologies/import",
        files={"file": ("a.ttl", b"<urn:a> <urn:b> <urn:c> .", "text/turtle")},
    )
    await sign_in(client, db, Role.VIEWER)
    viewer = await upload(client, b"<urn:a> <urn:b> <urn:c> .")

    assert anonymous.status_code == 401
    assert (viewer.status_code, viewer.json()["code"]) == (403, "auth.forbidden")


# ---------- merge rules ----------


async def test_delete_waits_for_dependents_and_restore_brings_back(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    weight = element(steel, "property", "weight", "重量", domain_id=heat.id, datatype="decimal")
    await add_elements(db, heat, weight)
    lone = proposal("delete", "entity_type", target=heat.id)
    change_set_id = await open_change_set(db, steel, [lone])
    await sign_in(client, db, Role.REVIEWER)

    result = await accept_and_merge(client, change_set_id)

    assert [skip["code"] for skip in result["skipped"]] == ["changeset.has_dependents"]
    both = await open_change_set(
        db,
        steel,
        [
            proposal("delete", "entity_type", target=heat.id),
            proposal("delete", "property", target=weight.id),
        ],
    )
    assert (await accept_and_merge(client, both))["skipped"] == []
    await db.refresh(heat)
    assert (heat.status, heat.revision) == ("deprecated", 2)
    restore = await open_change_set(
        db,
        steel,
        [proposal("restore", "entity_type", target=heat.id, label_zh="炉次（恢复）")],
    )
    assert (await accept_and_merge(client, restore))["skipped"] == []
    await db.refresh(heat)
    assert (heat.status, heat.label_zh, heat.revision) == ("active", "炉次（恢复）", 3)


async def test_constraints_axioms_and_inverses_merge(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    coil = element(steel, "entity_type", "Coil", "钢卷")
    weight = element(steel, "property", "weight", "重量", domain_id=coil.id, datatype="decimal")
    await add_elements(db, coil, weight)
    rule = {"pathRef": str(weight.id), "minCount": 1, "message": [{"lang": "zh", "text": "必填"}]}
    items = [
        proposal(
            "create",
            "constraint",
            temp_ref="new:shape",
            local_name="CoilShape",
            label_zh="钢卷规则",
            domain_ref=str(coil.id),
            rules=[rule],
        ),
        proposal(
            "create",
            "relation_type",
            temp_ref="new:of",
            local_name="partOf",
            label_zh="属于",
            domain_ref=str(coil.id),
            range_ref=str(coil.id),
            inverse_ref="new:has",
        ),
        proposal(
            "create",
            "relation_type",
            temp_ref="new:has",
            local_name="hasPart",
            label_zh="包含",
            domain_ref=str(coil.id),
            range_ref=str(coil.id),
        ),
        proposal("create", "axiom", turtle='steel:Coil rdfs:comment "注释" .'),
        proposal("create", "axiom", turtle="this is not turtle"),
    ]
    change_set_id = await open_change_set(db, steel, items)
    await sign_in(client, db, Role.REVIEWER)

    result = await accept_and_merge(client, change_set_id)

    assert [skip["code"] for skip in result["skipped"]] == ["changeset.invalid_item"]
    listed = (
        await client.get(f"/api/ontologies/{steel.id}/elements", params={"status": "all"})
    ).json()
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for item in listed:
        by_kind.setdefault(item["kind"], []).append(item)
    (shape,) = by_kind["constraint"]
    assert shape["rules"] == [
        {
            "pathId": str(weight.id),
            "minCount": 1,
            "message": [{"lang": "zh", "text": "必填"}],
            "maxCount": None,
            "datatype": None,
            "nodeKind": None,
            "allowedValues": None,
            "allowedValuesLost": False,
            "minInclusive": None,
            "maxInclusive": None,
            "minExclusive": None,
            "maxExclusive": None,
            "minLength": None,
            "maxLength": None,
            "pattern": None,
            "flags": None,
            "classId": None,
        },
    ]
    relations = {item["localName"]: item for item in by_kind["relation_type"]}
    assert relations["partOf"]["inverseId"] == relations["hasPart"]["id"]
    (axiom,) = by_kind["axiom"]
    assert axiom["subjectId"] == str(coil.id)
    assert axiom["localName"] is None
    turtle = await client.get(f"/api/ontologies/{steel.id}/export")
    graph = Graph().parse(data=turtle.text, format="turtle")
    base = "https://example.org/ontology/steel#"
    assert (URIRef(base + "Coil"), RDFS.comment, None) in graph
    assert (URIRef(base + "partOf"), OWL.inverseOf, URIRef(base + "hasPart")) in graph


async def test_review_edits_of_axioms_are_checked(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        steel,
        [proposal("create", "axiom", turtle='steel:A rdfs:comment "x" .')],
    )
    await sign_in(client, db, Role.REVIEWER)
    (item,) = await change_set_items(client, change_set_id)

    response = await client.patch(
        f"/api/change-sets/{change_set_id}/items/{item['id']}",
        json={"edited": {"turtle": "steel:A rdfs:comment"}},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "changeset.invalid_edit"
    assert (await decide(client, change_set_id, [item["id"]], "accepted")).status_code == 200
    assert (await merge(client, change_set_id)).json()["skipped"] == []
    assert (await publish(client, steel)).status_code == 201


# ---------- found in review ----------

INVERSES = b"""
@prefix ex: <urn:inv:> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<urn:inv:onto> a owl:Ontology ; rdfs:label "Inverses" .
ex:p a owl:ObjectProperty ; owl:inverseOf ex:q .
ex:q a owl:ObjectProperty ; owl:inverseOf ex:p .
ex:keep a owl:Class .
"""


async def test_relations_that_are_each_others_inverse(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, INVERSES)
    ontology_id = result["ontology"]["id"]
    relations = (
        await client.get(
            f"/api/ontologies/{ontology_id}/elements", params={"kind": "relation_type"}
        )
    ).json()
    by_iri = {item["iri"]: item for item in relations}

    assert by_iri["urn:inv:p"]["inverseId"] == by_iri["urn:inv:q"]["id"]
    assert by_iri["urn:inv:q"]["inverseId"] == by_iri["urn:inv:p"]["id"]
    assert lost(INVERSES, await export(client, ontology_id)) == []

    without = INVERSES.split(b"ex:p a")[0] + b"ex:keep a owl:Class .\n"
    removed = await upload(client, without, ontology_id=ontology_id)
    merged = await accept_and_merge(client, removed.json()["changeSetId"])
    assert merged["skipped"] == []
    remaining = (await client.get(f"/api/ontologies/{ontology_id}/elements")).json()
    assert [item["iri"] for item in remaining] == ["urn:inv:keep"]


async def test_names_from_the_file_are_kept(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    named = await import_and_merge(client, INVERSES, name="我起的名字")
    ontology_id = named["ontology"]["id"]

    exported = Graph().parse(data=await export(client, ontology_id), format="turtle")
    labels = {str(o) for o in exported.objects(URIRef("urn:inv:onto"), RDFS.label)}
    assert labels == {"我起的名字", "Inverses"}

    renamed = INVERSES.replace(b'"Inverses"', b'"Renamed"')
    changed = await upload(client, renamed, ontology_id=ontology_id)
    items = await change_set_items(client, changed.json()["changeSetId"])
    assert [(item["op"], item["kind"]) for item in items] == [
        ("create", "axiom"),
        ("delete", "axiom"),
    ]


async def test_the_same_file_can_be_imported_twice(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)

    first = await upload(client, INVERSES, filename="inverses.ttl")
    second = await upload(client, INVERSES, filename="inverses.ttl")

    assert (first.status_code, second.status_code) == (201, 201)
    assert first.json()["ontology"]["key"] == "inverses"
    assert second.json()["ontology"]["key"] == "inverses-2"


async def test_an_axiom_too_long_to_keep(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    text = "x" * 2_000_001
    data = f'<urn:t:a> <http://www.w3.org/2000/01/rdf-schema#comment> "{text}" .'.encode()

    response = await upload(client, data)

    assert (response.status_code, response.json()["code"]) == (422, "import.axiom_too_large")


async def test_a_rejected_restore_skips_what_depends_on_it(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次", status="deprecated")
    await add_elements(db, heat)
    change_set_id = await open_change_set(
        db,
        steel,
        [
            proposal("restore", "entity_type", target=heat.id),
            proposal(
                "create",
                "property",
                temp_ref="new:weight",
                local_name="weight",
                label_zh="重量",
                domain_ref=str(heat.id),
                datatype="decimal",
            ),
        ],
    )
    await sign_in(client, db, Role.REVIEWER)
    restore, create = await change_set_items(client, change_set_id)
    assert (await decide(client, change_set_id, [restore["id"]], "rejected")).status_code == 200
    assert (await decide(client, change_set_id, [create["id"]], "accepted")).status_code == 200

    result = (await merge(client, change_set_id)).json()

    assert result["skipped"] == [{"itemId": create["id"], "code": "changeset.dependency_skipped"}]
