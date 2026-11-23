"""Turtle export: a golden file compared byte for byte, determinism and a valid RDF round trip."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from rdflib import Graph
from rdflib.compare import isomorphic

from ontology_platform.modules.ontology.schemas import Element
from ontology_platform.modules.ontology.turtle import OntologyHeader, build_graph, export_turtle

GOLDEN = Path(__file__).parent / "fixtures" / "ontology" / "steel-v2.ttl"
BASE = "https://example.org/ontology/steel#"
ONTOLOGY_ID = UUID("00000000-0000-4000-8000-0000000057ee")
STAMP = datetime(2026, 11, 22, 8, 0, tzinfo=UTC)
HEADER = OntologyHeader(
    key="steel",
    name="钢铁冶金",
    description="合成的钢铁冶金样例。",
    base_iri=BASE,
)


def element_id(local_name: str) -> UUID:
    return uuid5(NAMESPACE_URL, BASE + local_name)


def make(local_name: str, kind: str, label_zh: str, **fields: Any) -> Element:
    data: dict[str, Any] = {
        "id": element_id(local_name),
        "ontology_id": ONTOLOGY_ID,
        "kind": kind,
        "local_name": local_name,
        "iri": BASE + local_name,
        "label_zh": label_zh,
        "label_en": None,
        "definition_zh": None,
        "definition_en": None,
        "synonyms": [],
        "parent_id": None,
        "domain_id": None,
        "range_id": None,
        "inverse_id": None,
        "explicit_iri": False,
        "datatype": None,
        "unit": None,
        "required": False,
        "multiple": False,
        "auto_shape": True,
        "rules": None,
        "turtle": None,
        "subject_id": None,
        "flags": [],
        "status": "active",
        "origin": "ai",
        "revision": 1,
        "created_at": STAMP,
        "updated_at": STAMP,
    }
    data.update(fields)
    return Element.model_validate(data)


def steel_elements() -> list[Element]:
    return [
        make("Equipment", "entity_type", "装备", label_en="Equipment", definition_zh="生产设备。"),
        make(
            "Converter",
            "entity_type",
            "转炉",
            label_en="Converter",
            parent_id=element_id("Equipment"),
            definition_zh="吹氧炼钢的炉子。",
            definition_en="Basic oxygen furnace.",
            synonyms=[{"lang": "zh", "text": "氧气转炉"}, {"lang": "en", "text": "BOF"}],
        ),
        make(
            "Heat",
            "entity_type",
            "炉次",
            label_en="Heat",
            definition_en='One "melt" of a converter.',
        ),
        make(
            "Slab",
            "entity_type",
            "板坯",
            label_en="Slab",
            definition_zh="连铸产出的\n半成品。",
        ),
        make("Obsolete", "entity_type", "废弃", status="deprecated"),
        make(
            "producedIn",
            "relation_type",
            "冶炼于",
            label_en="produced in",
            domain_id=element_id("Heat"),
            range_id=element_id("Converter"),
            required=True,
        ),
        make(
            "castFrom",
            "relation_type",
            "浇铸自",
            label_en="cast from",
            domain_id=element_id("Slab"),
            range_id=element_id("Heat"),
            multiple=True,
        ),
        make(
            "heatNumber",
            "property",
            "炉号",
            domain_id=element_id("Heat"),
            datatype="string",
            required=True,
            synonyms=[{"lang": "zh", "text": "炉次号"}],
        ),
        make(
            "tappedAt",
            "property",
            "出钢时间",
            domain_id=element_id("Heat"),
            datatype="dateTime",
        ),
        make(
            "thickness",
            "property",
            "厚度",
            label_en="Thickness",
            domain_id=element_id("Slab"),
            datatype="decimal",
            unit="mm",
            required=True,
        ),
        make(
            "oldWeight",
            "property",
            "旧重量",
            domain_id=element_id("Obsolete"),
            datatype="decimal",
            status="deprecated",
        ),
    ]


def test_export_matches_the_golden_file() -> None:
    turtle = export_turtle(HEADER, steel_elements(), version=2, created=STAMP)

    assert turtle.encode() == GOLDEN.read_bytes()


def test_export_is_byte_stable() -> None:
    elements = steel_elements()
    later = STAMP.astimezone(UTC) + timedelta(microseconds=250)

    first = export_turtle(HEADER, elements, version=2, created=STAMP)
    second = export_turtle(HEADER, elements, version=2, created=STAMP)
    reordered = export_turtle(HEADER, list(reversed(elements)), version=2, created=later)

    assert first == second
    assert reordered == first


def test_export_is_valid_turtle_for_the_whole_graph() -> None:
    elements = steel_elements()
    turtle = export_turtle(HEADER, elements, version=2, created=STAMP)

    parsed = Graph().parse(data=turtle, format="turtle")

    assert isomorphic(parsed, build_graph(HEADER, elements, version=2, created=STAMP))
    assert len(parsed) > 50


def test_working_version_has_no_version_info() -> None:
    turtle = export_turtle(HEADER, steel_elements(), version=None, created=STAMP)

    assert "owl:versionInfo" not in turtle
    assert 'dcterms:created "2026-11-22T08:00:00+00:00"^^xsd:dateTime' in turtle


def test_reserved_keys_use_a_fallback_prefix() -> None:
    header = OntologyHeader(key="owl", name="OWL", description=None, base_iri=BASE)

    turtle = export_turtle(header, steel_elements(), version=1, created=STAMP)

    assert f"@prefix ont: <{BASE}> ." in turtle
    assert "@prefix owl: <http://www.w3.org/2002/07/owl#> ." in turtle
    assert "ont:Slab a owl:Class" in turtle
    assert "dcterms:description" not in turtle
    assert isomorphic(
        Graph().parse(data=turtle, format="turtle"),
        build_graph(header, steel_elements(), version=1, created=STAMP),
    )
