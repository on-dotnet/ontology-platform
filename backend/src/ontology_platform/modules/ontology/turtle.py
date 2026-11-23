"""Turtle export of an ontology: OWL 2 classes and properties, SHACL shapes, SKOS terms.

The working version and every release go through `export_turtle`, whose input is a list of
API `Element` objects (a release snapshot or the current active elements).

The RDF graph is built with rdflib; it is written by the small serializer below rather than by
rdflib's own, so that the bytes depend on nothing but the graph: the prefixes are fixed, the
ontology header comes first and the other subjects follow sorted by IRI, predicates are sorted
by IRI (rdf:type and sh:path first), objects by their Turtle text, and blank nodes (the SHACL
property shapes) are written inline. Exporting the same snapshot twice gives the same bytes.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology.schemas import Element

OP_NAMESPACE = "https://w3id.org/ontology-platform/vocab#"
SH_NAMESPACE = "http://www.w3.org/ns/shacl#"

FIXED_PREFIXES: dict[str, str] = {
    "dcterms": "http://purl.org/dc/terms/",
    "op": OP_NAMESPACE,
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "sh": SH_NAMESPACE,
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
# Ontology keys that cannot double as the ontology's own prefix.
_RESERVED_PREFIXES = frozenset(FIXED_PREFIXES) | {"base", "prefix", "true", "false"}
FALLBACK_PREFIX = "ont"
# Appended to an object type's local name to name its node shape. Local names never contain a
# hyphen, so shapes cannot collide with elements.
SHAPE_SUFFIX = "-shape"

OP = Namespace(OP_NAMESPACE)
SH = Namespace(SH_NAMESPACE)

XSD_TYPES: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.date,
    "dateTime": XSD.dateTime,
}
_OWL_TYPES: dict[str, URIRef] = {
    "entity_type": OWL.Class,
    "relation_type": OWL.ObjectProperty,
    "property": OWL.DatatypeProperty,
}

INDENT = "    "
# A conservative subset of Turtle's PN_LOCAL; anything else is written as a full IRI.
_LOCAL_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_IRI_UNSAFE = re.compile(r'[\x00-\x20<>"{}|^`\\]')
_INTEGER = re.compile(r"[+-]?[0-9]+")
_STRING_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


@dataclass(frozen=True, slots=True)
class OntologyHeader:
    """What the export needs to know about the ontology itself."""

    key: str
    name: str
    description: str | None
    base_iri: str


def ontology_iri(base_iri: str) -> str:
    """The IRI of the owl:Ontology: the element namespace without its trailing # or /."""
    return base_iri[:-1] if base_iri.endswith(("#", "/")) else base_iri


def own_prefix(key: str) -> str:
    return FALLBACK_PREFIX if key in _RESERVED_PREFIXES else key


def build_graph(
    header: OntologyHeader,
    elements: Iterable[Element],
    *,
    version: int | None,
    created: datetime,
) -> Graph:
    """The RDF graph of the active elements. `version` is None for the working version."""
    graph = Graph()
    base = header.base_iri
    ontology = URIRef(ontology_iri(base))
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal(header.name)))
    if header.description:
        graph.add((ontology, DCTERMS.description, Literal(header.description)))
    if version is not None:
        graph.add((ontology, OWL.versionInfo, Literal(str(version))))
    timestamp = created.astimezone(UTC).replace(microsecond=0)
    graph.add((ontology, DCTERMS.created, Literal(timestamp, datatype=XSD.dateTime)))

    active = [element for element in elements if element.status == "active"]
    types = {element.id: element for element in active if element.kind == "entity_type"}

    def iri(element: Element) -> URIRef:
        return URIRef(base + element.local_name)

    def type_iri(element_id: UUID | None) -> URIRef | None:
        # References to anything but an active object type are left out of the export.
        target = types.get(element_id) if element_id is not None else None
        return iri(target) if target is not None else None

    for element in active:
        subject = iri(element)
        graph.add((subject, RDF.type, _OWL_TYPES[element.kind]))
        graph.add((subject, RDFS.label, Literal(element.label_zh, lang="zh")))
        if element.label_en:
            graph.add((subject, RDFS.label, Literal(element.label_en, lang="en")))
        if element.definition_zh:
            graph.add((subject, SKOS.definition, Literal(element.definition_zh, lang="zh")))
        if element.definition_en:
            graph.add((subject, SKOS.definition, Literal(element.definition_en, lang="en")))
        for synonym in element.synonyms:
            graph.add((subject, SKOS.altLabel, Literal(synonym.text, lang=synonym.lang)))

        if element.kind == "entity_type":
            parent = type_iri(element.parent_id)
            if parent is not None:
                graph.add((subject, RDFS.subClassOf, parent))
            continue
        domain = type_iri(element.domain_id)
        if domain is not None:
            graph.add((subject, RDFS.domain, domain))
        if element.kind == "relation_type":
            target = type_iri(element.range_id)
            if target is not None:
                graph.add((subject, RDFS.range, target))
        else:
            if element.datatype is not None:
                graph.add((subject, RDFS.range, XSD_TYPES[element.datatype]))
            if element.unit:
                graph.add((subject, OP.unit, Literal(element.unit)))
    # OWL 2 DL tools such as Protégé expect every annotation property in use to be declared.
    for prop in (DCTERMS.created, DCTERMS.description, SKOS.altLabel, SKOS.definition, OP.unit):
        if (None, prop, None) in graph:
            graph.add((prop, RDF.type, OWL.AnnotationProperty))

    for entity in types.values():
        shape = URIRef(base + entity.local_name + SHAPE_SUFFIX)
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, iri(entity)))
        for member in active:
            if member.kind == "entity_type" or member.domain_id != entity.id:
                continue
            constraint = BNode()
            graph.add((shape, SH.property, constraint))
            graph.add((constraint, SH.path, iri(member)))
            if member.kind == "relation_type":
                target = type_iri(member.range_id)
                if target is not None:
                    graph.add((constraint, SH["class"], target))
            elif member.datatype is not None:
                graph.add((constraint, SH.datatype, XSD_TYPES[member.datatype]))
            if member.required:
                graph.add((constraint, SH.minCount, Literal(1)))
            if not member.multiple:
                graph.add((constraint, SH.maxCount, Literal(1)))
    return graph


def export_turtle(
    header: OntologyHeader,
    elements: Sequence[Element],
    *,
    version: int | None,
    created: datetime,
) -> str:
    graph = build_graph(header, elements, version=version, created=created)
    prefixes = {**FIXED_PREFIXES, own_prefix(header.key): header.base_iri}
    return _TurtleWriter(graph, prefixes).write(URIRef(ontology_iri(header.base_iri)))


def _escape_iri(iri: str) -> str:
    return _IRI_UNSAFE.sub(lambda match: f"\\u{ord(match.group()):04X}", iri)


def _quote(text: str) -> str:
    parts: list[str] = []
    for char in text:
        escaped = _STRING_ESCAPES.get(char)
        if escaped is not None:
            parts.append(escaped)
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            parts.append(f"\\u{ord(char):04X}")
        else:
            parts.append(char)
    return '"' + "".join(parts) + '"'


def _predicate_order(predicate: URIRef) -> tuple[int, str]:
    if predicate == RDF.type:
        return (0, "")
    if predicate == SH.path:
        return (1, "")
    return (2, str(predicate))


class _TurtleWriter:
    """Writes a graph whose blank nodes each appear once, as an object, inline."""

    def __init__(self, graph: Graph, prefixes: dict[str, str]) -> None:
        self._graph = graph
        self._prefixes = sorted(prefixes.items())
        # Longest namespace first, so that the most specific prefix wins.
        self._by_length = sorted(self._prefixes, key=lambda item: -len(item[1]))

    def write(self, first: URIRef) -> str:
        header = "".join(
            f"@prefix {prefix}: <{_escape_iri(namespace)}> .\n"
            for prefix, namespace in self._prefixes
        )
        subjects = {subject for subject in self._graph.subjects() if isinstance(subject, URIRef)}
        ordered = sorted(subjects, key=lambda subject: (subject != first, str(subject)))
        blocks = [f"{self._iri(subject)} {self._predicates(subject, 1)} ." for subject in ordered]
        return header + "\n" + "\n\n".join(blocks) + "\n"

    def _predicates(self, subject: Node, depth: int) -> str:
        objects: dict[URIRef, list[str]] = {}
        for predicate, value in self._graph.predicate_objects(subject):
            if not isinstance(predicate, URIRef):
                raise TypeError("predicates must be IRIs")
            objects.setdefault(predicate, []).append(self._object(value, depth))
        lines: list[str] = []
        for predicate in sorted(objects, key=_predicate_order):
            values = ", ".join(sorted(objects[predicate]))
            lines.append(f"{self._verb(predicate)} {values}")
        return (" ;\n" + INDENT * depth).join(lines)

    def _verb(self, predicate: URIRef) -> str:
        return "a" if predicate == RDF.type else self._iri(predicate)

    def _object(self, value: Node, depth: int) -> str:
        if isinstance(value, BNode):
            inner = INDENT * (depth + 1)
            return f"[\n{inner}{self._predicates(value, depth + 1)}\n{INDENT * depth}]"
        if isinstance(value, Literal):
            return self._literal(value)
        if isinstance(value, URIRef):
            return self._iri(value)
        raise TypeError(f"cannot write {type(value).__name__}")

    def _iri(self, iri: str) -> str:
        for prefix, namespace in self._by_length:
            local = iri[len(namespace) :]
            if iri.startswith(namespace) and _LOCAL_PART.fullmatch(local):
                return f"{prefix}:{local}"
        return f"<{_escape_iri(iri)}>"

    def _literal(self, literal: Literal) -> str:
        lexical = str(literal)
        if literal.language:
            return f"{_quote(lexical)}@{literal.language}"
        datatype = literal.datatype
        if datatype is None:
            return _quote(lexical)
        if datatype == XSD.integer and _INTEGER.fullmatch(lexical):
            return lexical
        return f"{_quote(lexical)}^^{self._iri(datatype)}"
