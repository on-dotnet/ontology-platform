"""Expert mode (spec 002, section 7): editing the whole Turtle, and checking single axioms."""

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import expert
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology
from support import csrf_headers
from test_ontology_import import FIXTURES, STEEL, export, import_and_merge
from test_ontology_support import change_set_items, sign_in

SMALL = b"""
@prefix ex: <urn:t:> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:A a owl:Class ; rdfs:label "\xe7\x94\xb2"@zh .
ex:B a owl:Class .
ex:C a owl:Class .
ex:A owl:disjointWith ex:C .
"""


async def save(client: AsyncClient, ontology_id: str, turtle: str) -> Any:
    return await client.post(
        f"/api/ontologies/{ontology_id}/turtle",
        json={"turtle": turtle},
        headers=csrf_headers(client),
    )


async def test_edited_turtle_becomes_a_manual_change_set_for_review(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, STEEL, filename="steel.ttl")
    ontology_id = result["ontology"]["id"]
    exported = await export(client, ontology_id)
    assert '"炉次"@zh' in exported

    edited = exported.replace('"炉次"@zh', '"熔炼炉次"@zh') + "\nex:Ladle a owl:Class .\n"
    response = await save(client, ontology_id, edited)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"create": 1, "update": 1, "delete": 0, "restore": 0}
    change_set = await db.get(ChangeSet, UUID(body["changeSetId"]))
    assert change_set is not None
    # Even an admin's edit waits for review: expert edits never merge themselves.
    assert (change_set.source, change_set.status, change_set.title) == (
        "manual",
        "open",
        "专家模式：编辑 Turtle",
    )
    items = await change_set_items(client, body["changeSetId"])
    update = next(item for item in items if item["op"] == "update")
    assert update["proposed"] == {"labelZh": "熔炼炉次"}


async def test_unchanged_turtle_makes_no_change_set(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SMALL)
    await sign_in(client, db, Role.EDITOR)
    ontology_id = result["ontology"]["id"]

    response = await save(client, ontology_id, await export(client, ontology_id))

    assert response.status_code == 200
    assert response.json()["changeSetId"] is None


async def test_expert_edit_does_not_restore_a_lost_nested_list(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    original = (FIXTURES / "shacl-lists" / "qualified-in.ttl").read_bytes()
    saved = (FIXTURES / "owlapi" / "shacl-lists" / "qualified-in.ttl").read_text()
    result = await import_and_merge(client, original, filename="qualified-in.ttl")

    response = await save(client, result["ontology"]["id"], saved)

    assert response.status_code == 200, response.text
    items = await change_set_items(client, response.json()["changeSetId"])
    assert [(item["op"], item["kind"]) for item in items] == [
        ("create", "axiom"),
        ("create", "axiom"),
        ("delete", "axiom"),
    ]
    assert any("sh:in [" in item["proposed"].get("turtle", "") for item in items)


async def test_a_syntax_error_names_its_line(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SMALL)
    await sign_in(client, db, Role.EDITOR)

    response = await save(client, result["ontology"]["id"], "@prefix ex: <urn:t:> .\n\nex:A ex:p .")

    assert response.status_code == 422
    assert (response.json()["code"], response.json()["line"]) == ("import.parse_error", 3)


async def test_viewers_cannot_edit_turtle(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SMALL)
    await sign_in(client, db, Role.VIEWER)

    response = await save(client, result["ontology"]["id"], "@prefix ex: <urn:t:> .")

    assert response.status_code == 403


# ---------- single axioms ----------


async def small_ontology(client: AsyncClient, db: AsyncSession) -> Ontology:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SMALL)
    ontology = await db.get(Ontology, UUID(result["ontology"]["id"]))
    assert ontology is not None
    return ontology


async def test_an_axiom_the_forms_cannot_express_passes(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await small_ontology(client, db)

    axiom = await expert.check_axiom(db, ontology, "ex:A owl:disjointWith   ex:B .")

    assert axiom.turtle == "ex:A owl:disjointWith ex:B ."
    assert axiom.subject == "urn:t:A"


@pytest.mark.parametrize(
    ("turtle", "code"),
    [
        ("ex:A rdfs:subClassOf ex:B .", "axiom.maps_to_element"),
        ('ex:B rdfs:label "乙"@zh .', "axiom.maps_to_element"),
        # A new IRI would come back as a new element after an export and a fresh import.
        ("ex:A owl:disjointWith ex:Unknown .", "axiom.maps_to_element"),
        ("ex:A owl:disjointWith .", "axiom.invalid"),
        ("ex:A owl:disjointWith ex:B . ex:B owl:disjointWith ex:C .", "axiom.invalid"),
        ("ex:A owl:disjointWith ex:C .", "axiom.invalid"),
    ],
)
async def test_fragments_that_are_not_one_new_axiom_are_refused(
    client: AsyncClient, db: AsyncSession, turtle: str, code: str
) -> None:
    ontology = await small_ontology(client, db)

    with pytest.raises(AppError) as raised:
        await expert.check_axiom(db, ontology, turtle)

    assert (raised.value.status, raised.value.code) == (422, code)


async def test_rewriting_an_axiom_leaves_the_old_one_out(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await small_ontology(client, db)
    listed = await client.get(f"/api/ontologies/{ontology.id}/elements", params={"kind": "axiom"})
    (old,) = listed.json()
    stored = await db.get(Element, UUID(old["id"]))
    assert stored is not None

    axiom = await expert.check_axiom(
        db,
        ontology,
        "ex:A owl:disjointWith ex:C .",
        replacing=stored.id,
    )

    assert axiom.turtle == "ex:A owl:disjointWith ex:C ."
