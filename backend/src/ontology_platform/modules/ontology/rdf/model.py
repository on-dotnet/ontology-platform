"""The ontology as the RDF layer sees it: elements keyed by IRI, axioms as triples.

`OntologyState` is what the reader produces from a file and what the writer turns into Turtle;
the service converts database rows to and from it, and `diff` compares two of them. References
between elements are IRIs here, never database ids.
"""

import hashlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

import rdflib
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import to_canonical_graph
from rdflib.namespace import XSD
from rdflib.term import Node

# Keep literals exactly as written ("01"^^xsd:integer stays "01"): imports must not lose content.
rdflib.NORMALIZE_LITERALS = False

Triple = tuple[Node, Node, Node]
Term = URIRef | Literal


class _IllTypedLiterals(logging.Filter):
    """rdflib logs a traceback for every ill-typed literal it converts; those are user data
    (a file may well say "abc"^^xsd:integer), not errors of the platform."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith("Failed to convert Literal lexical form")


logging.getLogger("rdflib.term").addFilter(_IllTypedLiterals())


def canonical_term(term: Node) -> Node:
    """The term with a typed literal's value in canonical form, for comparisons only.

    OWL API (and so Protégé) rewrites "01"^^xsd:integer as "1"; both denote the same value.
    """
    if not isinstance(term, Literal) or term.datatype is None:
        if isinstance(term, Literal) and term.language:
            return Literal(str(term), lang=term.language.lower())
        return term
    if term.ill_typed:
        return term
    normalized = Literal(str(term), datatype=term.datatype, normalize=True)
    return normalized if not normalized.ill_typed else term


def _tree_lines(triples: list[Triple]) -> list[str] | None:
    """Statements with every blank node replaced by a hash of what hangs below it.

    Works when the blank nodes form trees (each used as an object at most once, no cycles),
    which is what the reader leaves after splitting shared nodes; then it is linear, while
    rdflib's general canonicalization takes minutes on a list of a thousand members. None for
    anything else.
    """
    below: dict[Node, list[tuple[Node, Node]]] = {}
    used: set[Node] = set()
    # Where the trees start: blank objects of named subjects, and blank subjects nobody uses.
    starts: list[Node] = []
    for s, p, o in triples:
        if isinstance(s, BNode):
            below.setdefault(s, []).append((p, o))
        if isinstance(o, BNode):
            if o in used:
                return None
            used.add(o)
            if not isinstance(s, BNode):
                starts.append(o)
    starts.extend(node for node in below if node not in used)
    names: dict[Node, str] = {}
    # Post-order without recursion: a node is named once all its blank children are.
    for root in starts:
        stack: list[tuple[Node, bool]] = [(root, False)]
        while stack:
            node, ready = stack.pop()
            if node in names:
                continue
            children = [o for _, o in below.get(node, []) if isinstance(o, BNode)]
            if not ready:
                stack.append((node, True))
                stack.extend((child, False) for child in children if child not in names)
                continue
            if any(child not in names for child in children):
                return None  # a cycle
            parts = sorted(
                f"{p.n3()} {names[o] if isinstance(o, BNode) else o.n3()}"
                for p, o in below.get(node, [])
            )
            names[node] = "_:" + hashlib.sha256("\n".join(parts).encode()).hexdigest()
    if any(node not in names for node in below) or any(node not in names for node in used):
        return None  # blank nodes only reachable from a cycle, or never described
    return sorted(
        f"{names.get(s, s.n3())} {p.n3()} {names[o] if isinstance(o, BNode) else o.n3()}"
        for s, p, o in triples
        if not isinstance(s, BNode) or s not in used
    )


def canonical_key(triples: Iterable[Triple], *, exact: bool = False) -> str:
    """A key that two sets of triples share exactly when they are the same graph, up to blank
    node names and (unless `exact`) the spelling of literal values."""
    given = [(s, p, o if exact else canonical_term(o)) for s, p, o in triples]
    lines = _tree_lines(given)
    if lines is None:
        graph = Graph(bind_namespaces="none")
        for triple in given:
            graph.add(triple)
        lines = sorted(f"{s.n3()} {p.n3()} {o.n3()}" for s, p, o in to_canonical_graph(graph))
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def term_json(term: Term) -> dict[str, Any]:
    """An RDF value for the API and the rules column, keeping its exact spelling."""
    if isinstance(term, URIRef):
        return {"iri": str(term)}
    datatype = str(term.datatype) if term.datatype is not None else None
    if datatype is not None and datatype.startswith(str(XSD)):
        datatype = datatype[len(str(XSD)) :]
    return {"lexical": str(term), "datatype": datatype, "lang": term.language}


def term_from_json(value: dict[str, Any]) -> Term:
    iri = value.get("iri")
    if iri is not None:
        return URIRef(str(iri))
    lexical = str(value.get("lexical", ""))
    lang = value.get("lang")
    if lang:
        return Literal(lexical, lang=str(lang))
    datatype = value.get("datatype")
    if not datatype:
        return Literal(lexical)
    datatype = str(datatype)
    if ":" not in datatype:
        datatype = str(XSD) + datatype
    return Literal(lexical, datatype=URIRef(datatype))


@dataclass(frozen=True, slots=True)
class Rule:
    """One sh:property of a constraint (spec 002, 3.3). Literal values keep their spelling."""

    path: str
    min_count: int | None = None
    max_count: int | None = None
    datatype: str | None = None
    class_: str | None = None
    node_kind: str | None = None
    in_: tuple[Term, ...] | None = None
    # sh:in points at an empty blank node: what OWL API writes when it drops the list.
    in_lost: bool = False
    min_inclusive: Term | None = None
    max_inclusive: Term | None = None
    min_exclusive: Term | None = None
    max_exclusive: Term | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    flags: str | None = None
    message: tuple[Literal, ...] = ()

    def key(self) -> tuple[Any, ...]:
        """Equal for rules that state the same thing (literal values compared by value)."""

        def value(term: Term | None) -> str | None:
            return None if term is None else canonical_term(term).n3()

        return (
            self.path,
            self.min_count,
            self.max_count,
            self.datatype,
            self.class_,
            self.node_kind,
            None if self.in_ is None else tuple(value(term) for term in self.in_),
            self.in_lost,
            value(self.min_inclusive),
            value(self.max_inclusive),
            value(self.min_exclusive),
            value(self.max_exclusive),
            self.min_length,
            self.max_length,
            self.pattern,
            self.flags,
            tuple(sorted(value(text) or "" for text in self.message)),
        )

    def references(self) -> set[str]:
        return {iri for iri in (self.path, self.class_) if iri is not None}


@dataclass(slots=True)
class ElementState:
    """An element other than an axiom. References are IRIs of other elements."""

    kind: str
    iri: str
    label_zh: str | None = None
    label_en: str | None = None
    definition_zh: str | None = None
    definition_en: str | None = None
    # (lang, text) pairs; order does not matter.
    synonyms: tuple[tuple[str, str], ...] = ()
    parent: str | None = None
    domain: str | None = None
    range: str | None = None
    inverse: str | None = None
    datatype: str | None = None
    unit: str | None = None
    required: bool = False
    multiple: bool = True
    auto_shape: bool = False
    rules: tuple[Rule, ...] = ()
    active: bool = True
    # The caller's key for the element (the database id), opaque to this package.
    id: str | None = None

    def references(self) -> set[str]:
        refs = {iri for iri in (self.parent, self.domain, self.range, self.inverse) if iri}
        for rule in self.rules:
            refs |= rule.references()
        return refs


@dataclass  # no slots: cached_property needs an instance __dict__
class AxiomState:
    """Triples kept as they are: one connected group of statements (spec 002, 3.4)."""

    triples: tuple[Triple, ...]
    non_standard: bool = False
    # The caller's key for the axiom (the database id), opaque to this package.
    id: str | None = None

    @cached_property
    def key(self) -> str:
        return canonical_key(self.triples)

    @cached_property
    def subject(self) -> str | None:
        """The first named subject, by IRI."""
        named = sorted(str(s) for s, _, _ in self.triples if isinstance(s, URIRef))
        return named[0] if named else None

    @cached_property
    def mentions(self) -> frozenset[str]:
        return frozenset(
            str(term) for triple in self.triples for term in triple if isinstance(term, URIRef)
        )


@dataclass(slots=True)
class OntologyState:
    ontology_iri: str
    name: str | None = None
    description: str | None = None
    elements: dict[str, ElementState] = field(default_factory=dict)
    axioms: list[AxiomState] = field(default_factory=list)

    def active_elements(self) -> list[ElementState]:
        return [element for element in self.elements.values() if element.active]

    def is_type(self, iri: str | None) -> bool:
        element = self.elements.get(iri) if iri else None
        return element is not None and element.active and element.kind == "entity_type"
