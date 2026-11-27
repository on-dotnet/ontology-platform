"""Characterize the SHACL lists lost in OWL API 4.5.29's recorded Turtle copies."""

from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, SH, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology import owlcheck

FIXTURES = Path(__file__).parent / "fixtures" / "ontology"
EX = Namespace("urn:synthetic:shacl-lists:")
SHAPES = {
    "qualified-in": EX.QualifiedInShape,
    "or-member-in": EX.OrMemberInShape,
    "logical-or": EX.LogicalOrShape,
    "logical-and": EX.LogicalAndShape,
    "logical-xone": EX.LogicalXoneShape,
    "alternative-path": EX.AlternativePathShape,
    "sequence-path": EX.SequencePathShape,
}
SAVED = FIXTURES / "owlapi" / "shacl-lists"


@pytest.mark.parametrize("stem", list(SHAPES))
def test_round_trip_reports_a_change(stem: str) -> None:
    """OWL API loses the list in each case and the platform reports a change."""
    original = (FIXTURES / "shacl-lists" / f"{stem}.ttl").read_bytes()
    saved = (SAVED / f"{stem}.ttl").read_bytes()

    outcome = owlcheck.compare_case(stem, original, saved)

    assert not outcome.passed, outcome.detail
    assert outcome.status == "changed", outcome.detail


def _saved_property(stem: str) -> tuple[Graph, BNode]:
    graph = Graph().parse(SAVED / f"{stem}.ttl", format="turtle")
    shape = SHAPES[stem]
    assert (shape, RDF.type, SH.NodeShape) in graph
    assert (shape, SH.targetClass, EX.Item) in graph
    (rule,) = graph.objects(shape, SH.property)
    assert isinstance(rule, BNode)
    return graph, rule


def _assert_empty_object(graph: Graph, subject: Node, predicate: URIRef) -> None:
    (head,) = graph.objects(subject, predicate)
    assert isinstance(head, BNode)
    assert (head, None, None) not in graph


def test_qualified_in() -> None:
    """OWL API keeps the qualified shape and its count but empties its enumeration."""
    graph, rule = _saved_property("qualified-in")
    assert (rule, SH.path, EX.p) in graph
    assert (rule, SH.qualifiedMinCount, Literal(1)) in graph
    (qualified,) = graph.objects(rule, SH.qualifiedValueShape)
    assert isinstance(qualified, BNode)
    _assert_empty_object(graph, qualified, SH["in"])


@pytest.mark.parametrize(
    ("stem", "operator", "members"),
    [
        ("or-member-in", SH["or"], [(SH["in"], None), (SH.datatype, XSD.integer)]),
        ("logical-or", SH["or"], [(SH.datatype, XSD.string), (SH.datatype, XSD.integer)]),
        ("logical-and", SH["and"], [(SH.minLength, Literal(1)), (SH.maxLength, Literal(8))]),
        (
            "logical-xone",
            SH.xone,
            [(SH.datatype, XSD.string), (SH.datatype, XSD.integer), (SH.datatype, XSD.boolean)],
        ),
    ],
    ids=["or-member-in", "logical-or", "logical-and", "logical-xone"],
)
def test_logical_members(
    stem: str, operator: URIRef, members: list[tuple[URIRef, Node | None]]
) -> None:
    """OWL API empties the logical list and detaches each member, emptying any nested sh:in."""
    graph, rule = _saved_property(stem)
    assert (rule, SH.path, EX.p) in graph
    _assert_empty_object(graph, rule, operator)
    detached = set()
    for predicate, value in members:
        (member,) = graph.subjects(predicate, value)
        assert isinstance(member, BNode)
        assert (None, None, member) not in graph
        detached.add(member)
        if value is None:
            _assert_empty_object(graph, member, predicate)
    assert len(detached) == len(members)


def test_alternative_path() -> None:
    """OWL API keeps the alternative path node but replaces its paths with an empty blank node."""
    graph, rule = _saved_property("alternative-path")
    assert (rule, SH.minCount, Literal(1)) in graph
    (path,) = graph.objects(rule, SH.path)
    assert isinstance(path, BNode)
    _assert_empty_object(graph, path, SH.alternativePath)


def test_sequence_path() -> None:
    """OWL API replaces the whole path sequence with an empty blank node."""
    graph, rule = _saved_property("sequence-path")
    assert (rule, SH.minCount, Literal(1)) in graph
    _assert_empty_object(graph, rule, SH.path)
