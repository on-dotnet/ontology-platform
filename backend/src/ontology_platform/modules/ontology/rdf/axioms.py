"""Splitting leftover triples into axioms, and spotting the ones Protégé rewrites (spec 002, 3.4).

An axiom is a connected group of triples: a statement about a named subject together with every
blank node reachable from it. Statements that share a blank node belong to the same axiom, so
that the blank node structure survives the round trip unchanged.
"""

from collections import defaultdict
from collections.abc import Iterable

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology.rdf.model import AxiomState, Triple

_BOOLEAN_CLASS_PREDICATES = frozenset(
    {OWL.unionOf, OWL.intersectionOf, OWL.complementOf, OWL.oneOf},
)
_CARDINALITIES = frozenset(
    {
        OWL.cardinality,
        OWL.minCardinality,
        OWL.maxCardinality,
        OWL.qualifiedCardinality,
        OWL.minQualifiedCardinality,
        OWL.maxQualifiedCardinality,
    },
)


def _blank(node: Node) -> bool:
    return isinstance(node, BNode)


def group(triples: Iterable[Triple]) -> list[list[Triple]]:
    """Connected groups: triples sharing a blank node end up together. Ordered for stability."""
    ordered = sorted(set(triples), key=lambda t: (t[0].n3(), t[1].n3(), t[2].n3()))
    parent: dict[int, int] = {}

    def find(index: int) -> int:
        while parent.setdefault(index, index) != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    owner: dict[Node, int] = {}
    for index, triple in enumerate(ordered):
        find(index)
        for node in (triple[0], triple[2]):
            if not _blank(node):
                continue
            if node in owner:
                parent[find(index)] = find(owner[node])
            else:
                owner[node] = index
    groups: dict[int, list[Triple]] = defaultdict(list)
    for index, triple in enumerate(ordered):
        groups[find(index)].append(triple)
    return sorted(groups.values(), key=lambda g: (g[0][0].n3(), g[0][1].n3(), g[0][2].n3()))


def non_standard(triples: Iterable[Triple]) -> bool:
    """Whether OWL API rewrites this axiom when it reads it (see the spec's measurements)."""
    for subject, predicate, value in triples:
        if predicate in _BOOLEAN_CLASS_PREDICATES and isinstance(subject, URIRef):
            # A named class with a class constructor: read as an equivalent-class axiom.
            return True
        if predicate in _CARDINALITIES and (
            not isinstance(value, Literal) or value.datatype != XSD.nonNegativeInteger
        ):
            # Cardinalities must be xsd:nonNegativeInteger; anything else becomes an error class.
            return True
    return False


def axioms_of(triples: Iterable[Triple]) -> list[AxiomState]:
    return [
        AxiomState(triples=tuple(component), non_standard=non_standard(component))
        for component in group(triples)
    ]
