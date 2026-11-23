"""The OWL 2 declarations a graph implies, the way OWL API (and so Protégé) reads them.

OWL 2 wants every entity in use declared. When a file leaves declarations out, OWL API works
out each entity's kind from how it is used and writes the declarations when it saves. The
platform's export adds the same declarations itself, so that a file saved by Protégé comes
back without differences; the import absorbs them again. `./dev.ps1 owl-check` compares these
rules with OWL API itself.
"""

from collections import defaultdict
from collections.abc import Iterator

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology.rdf.model import Triple
from ontology_platform.modules.ontology.rdf.vocab import DECLARATION_TYPES, is_builtin

# Annotation properties that are part of RDF and OWL themselves.
_BUILTIN_ANNOTATIONS = frozenset(
    {
        RDFS.label,
        RDFS.comment,
        RDFS.seeAlso,
        RDFS.isDefinedBy,
        OWL.versionInfo,
        OWL.deprecated,
        OWL.priorVersion,
        OWL.backwardCompatibleWith,
        OWL.incompatibleWith,
    },
)
_CLASS_PAIRS = (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith)
_CLASS_LISTS = (OWL.unionOf, OWL.intersectionOf, OWL.disjointUnionOf)
_OBJECT_ONLY = (
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    OWL.InverseFunctionalProperty,
)
_FILLERS = (OWL.someValuesFrom, OWL.allValuesFrom)
_RDF_DATATYPES = frozenset(
    {RDF.PlainLiteral, RDF.langString, RDF.XMLLiteral, RDF.HTML, RDFS.Literal},
)


def _items(graph: Graph, head: Node) -> Iterator[Node]:
    """Members of an RDF list; stops at anything that is not a well-formed list node."""
    seen: set[Node] = set()
    node = head
    while isinstance(node, BNode) and node not in seen:
        seen.add(node)
        first = graph.value(node, RDF.first)
        if first is not None:
            yield first
        rest = graph.value(node, RDF.rest)
        if rest is None:
            return
        node = rest


class _Kinds:
    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self.kinds: dict[URIRef, set[URIRef]] = defaultdict(set)
        for subject, kind in graph.subject_objects(RDF.type):
            declared = isinstance(kind, URIRef) and kind in DECLARATION_TYPES
            if isinstance(subject, URIRef) and isinstance(kind, URIRef) and declared:
                self.kinds[subject].add(kind)
        self.implied: set[Triple] = set()
        self.changed = False

    def add(self, node: Node, kind: URIRef) -> None:
        if not isinstance(node, URIRef) or is_builtin(str(node)):
            return
        self.implied.add((node, RDF.type, kind))
        if kind not in self.kinds[node]:
            self.kinds[node].add(kind)
            self.changed = True

    def has(self, node: Node, kind: URIRef) -> bool:
        return isinstance(node, URIRef) and kind in self.kinds.get(node, set())

    def is_datatype(self, node: Node) -> bool:
        if not isinstance(node, URIRef):
            return False
        return (
            str(node).startswith(str(XSD))
            or node in _RDF_DATATYPES
            or self.has(node, RDFS.Datatype)
        )


def _structural(kinds: _Kinds) -> None:
    graph = kinds.graph
    for subject, kind in graph.subject_objects(RDF.type):
        if isinstance(kind, URIRef) and not is_builtin(str(kind)):
            kinds.add(kind, OWL.Class)
            kinds.add(subject, OWL.NamedIndividual)
        if kind in _OBJECT_ONLY:
            kinds.add(subject, OWL.ObjectProperty)
    for predicate in _CLASS_PAIRS:
        for subject, value in graph.subject_objects(predicate):
            kinds.add(subject, OWL.Class)
            kinds.add(value, OWL.Class)
    for predicate in _CLASS_LISTS:
        for subject, head in graph.subject_objects(predicate):
            kinds.add(subject, OWL.Class)
            for member in _items(graph, head):
                kinds.add(member, OWL.Class)
    for subject, value in graph.subject_objects(OWL.complementOf):
        kinds.add(subject, OWL.Class)
        kinds.add(value, OWL.Class)
    for subject, head in graph.subject_objects(OWL.oneOf):
        kinds.add(subject, OWL.Class)
        for member in _items(graph, head):
            kinds.add(member, OWL.NamedIndividual)
    for subject in graph.subjects(OWL.hasKey):
        kinds.add(subject, OWL.Class)
    for subject, value in graph.subject_objects(OWL.inverseOf):
        kinds.add(subject, OWL.ObjectProperty)
        kinds.add(value, OWL.ObjectProperty)
    for subject, head in graph.subject_objects(OWL.propertyChainAxiom):
        kinds.add(subject, OWL.ObjectProperty)
        for member in _items(graph, head):
            kinds.add(member, OWL.ObjectProperty)
    for prop, value in graph.subject_objects(RDFS.domain):
        if not kinds.has(prop, OWL.AnnotationProperty):
            kinds.add(value, OWL.Class)
    for prop, value in graph.subject_objects(RDFS.range):
        if kinds.has(prop, OWL.ObjectProperty):
            kinds.add(value, OWL.Class)
        elif kinds.has(prop, OWL.DatatypeProperty) and not is_builtin(str(value)):
            kinds.add(value, RDFS.Datatype)
    for restriction, prop in graph.subject_objects(OWL.onProperty):
        _restriction(kinds, restriction, prop)
    for subject, value in (
        *graph.subject_objects(OWL.sameAs),
        *graph.subject_objects(OWL.differentFrom),
    ):
        kinds.add(subject, OWL.NamedIndividual)
        kinds.add(value, OWL.NamedIndividual)
    for group in graph.subjects(RDF.type, OWL.AllDifferent):
        for predicate in (OWL.members, OWL.distinctMembers):
            for head in graph.objects(group, predicate):
                for member in _items(graph, head):
                    kinds.add(member, OWL.NamedIndividual)
    for group in graph.subjects(RDF.type, OWL.AllDisjointClasses):
        for head in graph.objects(group, OWL.members):
            for member in _items(graph, head):
                kinds.add(member, OWL.Class)
    for predicate in (RDFS.subPropertyOf, OWL.equivalentProperty, OWL.propertyDisjointWith):
        for subject, value in graph.subject_objects(predicate):
            for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
                if kinds.has(subject, kind):
                    kinds.add(value, kind)
                if kinds.has(value, kind):
                    kinds.add(subject, kind)


def _restriction(kinds: _Kinds, restriction: Node, prop: Node) -> None:
    graph = kinds.graph
    for predicate in _FILLERS:
        for filler in graph.objects(restriction, predicate):
            if isinstance(filler, URIRef):
                if kinds.is_datatype(filler):
                    kinds.add(prop, OWL.DatatypeProperty)
                else:
                    kinds.add(prop, OWL.ObjectProperty)
                    kinds.add(filler, OWL.Class)
            elif (filler, RDF.type, OWL.Class) in graph or (
                filler,
                RDF.type,
                OWL.Restriction,
            ) in graph:
                kinds.add(prop, OWL.ObjectProperty)
    for value in graph.objects(restriction, OWL.hasValue):
        if isinstance(value, Literal):
            kinds.add(prop, OWL.DatatypeProperty)
        else:
            kinds.add(prop, OWL.ObjectProperty)
            kinds.add(value, OWL.NamedIndividual)
    for value in graph.objects(restriction, OWL.onClass):
        kinds.add(prop, OWL.ObjectProperty)
        kinds.add(value, OWL.Class)
    if (restriction, OWL.onDataRange, None) in graph:
        kinds.add(prop, OWL.DatatypeProperty)
    if (restriction, OWL.hasSelf, None) in graph:
        kinds.add(prop, OWL.ObjectProperty)


def _assertions(kinds: _Kinds) -> None:
    for subject, predicate, value in kinds.graph:
        if not isinstance(predicate, URIRef) or is_builtin(str(predicate)):
            continue
        if predicate in _BUILTIN_ANNOTATIONS:
            continue
        if kinds.has(predicate, OWL.ObjectProperty):
            kinds.add(subject, OWL.NamedIndividual)
            kinds.add(value, OWL.NamedIndividual)
        elif kinds.has(predicate, OWL.DatatypeProperty):
            kinds.add(subject, OWL.NamedIndividual)
        else:
            # Declared or not, a predicate of neither kind is an annotation property.
            kinds.add(predicate, OWL.AnnotationProperty)


def implied_declarations(graph: Graph) -> set[Triple]:
    """Every declaration the usage in `graph` implies, whether or not the graph states it."""
    kinds = _Kinds(graph)
    kinds.changed = True
    while kinds.changed:
        kinds.changed = False
        _structural(kinds)
    _assertions(kinds)
    return kinds.implied


def missing_declarations(graph: Graph) -> set[Triple]:
    return {triple for triple in implied_declarations(graph) if triple not in graph}
