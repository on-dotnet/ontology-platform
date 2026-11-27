"""Read-only descriptions of the Turtle that ontology forms cannot express."""

from collections import Counter
from time import perf_counter
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import Ontology
from ontology_platform.modules.ontology.rdf.axiom_categories import (
    classify_axiom,
    declared_annotations,
    fragment_info,
)
from ontology_platform.modules.ontology.rdf.vocab import FIXED_PREFIXES
from ontology_platform.modules.ontology.rdf.writer import prefix_map
from support import csrf_headers
from test_ontology_import import STEEL_PROTEGE, all_elements, import_and_merge, upload
from test_ontology_support import change_set_items, sign_in

PREFIXES = {**FIXED_PREFIXES, "ex": "urn:steel:"}
SOURCE = """
    @prefix ex: <urn:steel:> .
    @prefix owl: <http://www.w3.org/2002/07/owl#> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Heat a owl:Class ; rdfs:comment "一次冶炼"@zh .
""".encode()


@pytest.mark.parametrize(
    ("turtle", "category", "note"),
    [
        ('ex:S sh:property [ a owl:Restriction ; sh:message "形状"@zh ] .', "shape", "形状"),
        ("ex:S a sh:PropertyShape .", "shape", None),
        ("ex:A rdfs:subClassOf [ a owl:Restriction ; owl:hasValue 3 ] .", "logic", None),
        ("ex:p a owl:TransitiveProperty .", "logic", None),
        ("ex:p rdfs:subPropertyOf ex:q .", "logic", None),
        ("ex:p owl:propertyDisjointWith ex:q .", "logic", None),
        ("ex:A a ex:Code ; rdfs:subClassOf ex:B .", "individual", None),
        ("ex:A a skos:ConceptScheme .", "individual", None),
        ("ex:A a owl:NamedIndividual .", "individual", None),
        ("ex:A rdfs:subClassOf ex:B .", "parent", None),
        ('ex:A rdfs:isDefinedBy ex:B ; dcterms:source "source" .', "annotation", None),
        ('ex:A rdfs:comment "owl:Restriction sh:message"@en .', "annotation", None),
        ("ex:p a owl:AnnotationProperty .", "other", None),
        ('ex:A rdfs:label "A" ; ex:code 123 .', "other", None),
        (
            'ex:S sh:message "规则"@zh ; rdfs:comment "备注"@zh ; skos:definition "定义"@zh .',
            "shape",
            "规则",
        ),
        (
            'ex:S sh:message "rule"@en ; rdfs:comment "备注"@zh ; skos:definition "定义"@zh .',
            "shape",
            "备注",
        ),
        ('ex:S rdfs:comment "note" ; skos:definition "定义"@zh .', "annotation", "定义"),
    ],
)
def test_category_and_note(turtle: str, category: str, note: str | None) -> None:
    assert classify_axiom(turtle, tuple(sorted(PREFIXES.items()))) == (category, note)


def test_classification_resolves_the_ontology_prefixes() -> None:
    turtle = "<urn:A> vocab:inverseOf <urn:B> ."
    for prefix in ("vocab", "another"):
        renamed = turtle.replace("vocab:", f"{prefix}:")
        assert classify_axiom(renamed, ((prefix, PREFIXES["owl"]),)) == ("logic", None)
    assert classify_axiom(turtle, (("vocab", "urn:other:"),)) == ("other", None)


async def test_element_list_describes_only_axioms(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, SOURCE)
    elements = await all_elements(client, result)
    by_kind = {element["kind"]: element for element in elements}
    assert by_kind["axiom"]["axiomCategory"] == "annotation"
    assert by_kind["axiom"]["axiomNote"] == "一次冶炼"
    assert by_kind["entity_type"]["axiomCategory"] is None
    assert by_kind["entity_type"]["axiomNote"] is None


async def test_change_set_describes_the_effective_turtle(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    response = await upload(client, SOURCE)
    assert response.status_code == 201
    change_set = UUID(response.json()["changeSetId"])
    items = {item["kind"]: item for item in await change_set_items(client, change_set)}
    axiom = items["axiom"]
    assert (axiom["axiomCategory"], axiom["axiomNote"]) == ("annotation", "一次冶炼")
    assert items["entity_type"]["axiomCategory"] is None
    assert items["entity_type"]["axiomNote"] is None

    edited = await client.patch(
        f"/api/change-sets/{change_set}/items/{axiom['id']}",
        json={"edited": {"turtle": 'ex:Heat sh:message "需要校验"@zh .'}},
        headers=csrf_headers(client),
    )
    assert edited.status_code == 200, edited.text
    current = next(i for i in await change_set_items(client, change_set) if i["id"] == axiom["id"])
    assert (current["axiomCategory"], current["axiomNote"]) == ("shape", "需要校验")


async def test_classifies_all_imported_steel_axioms(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.ADMIN)
    result = await import_and_merge(client, STEEL_PROTEGE)
    ontology = await db.get(Ontology, UUID(result["ontology"]["id"]))
    assert ontology is not None
    prefixes = prefix_map(ontology.key, ontology.base_iri, ontology.prefixes or {})
    key = tuple(sorted(prefixes.items()))
    axioms = [e for e in await all_elements(client, result) if e["kind"] == "axiom"]
    fragments = [axiom["turtle"] for axiom in axioms]

    fragment_info.cache_clear()
    start = perf_counter()
    annotations = declared_annotations(fragments, key)
    counts: Counter[str] = Counter(
        classify_axiom(fragment, key, annotations)[0] for fragment in fragments
    )
    seconds = perf_counter() - start
    assert seconds <= 3
    assert counts == Counter(axiom["axiomCategory"] for axiom in axioms)
    # The steel shapes import as constraints, so what remains covers only these categories.
    assert counts == Counter({"individual": 2, "annotation": 3, "other": 1})
