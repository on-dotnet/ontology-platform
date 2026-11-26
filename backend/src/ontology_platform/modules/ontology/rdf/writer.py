"""From an `OntologyState` to RDF and to deterministic Turtle (spec 002, 4.2).

The graph holds the elements, the constraints, the platform's generated shapes, the axioms as
they were imported, and the declarations OWL 2 expects (see `declarations`). It is written by
the small serializer below rather than by rdflib's, so that the bytes depend on nothing but the
graph: prefixes fixed, the ontology header first, other subjects sorted by IRI, predicates by IRI
(rdf:type and sh:path first), objects by their Turtle text; blank nodes used once are written
inline, RDF lists as ( … ), and the rest with labels in a stable order.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology.rdf.declarations import missing_declarations
from ontology_platform.modules.ontology.rdf.model import (
    ElementState,
    OntologyState,
    Rule,
    Term,
    Triple,
)
from ontology_platform.modules.ontology.rdf.vocab import (
    FIXED_PREFIXES,
    OP,
    SH,
    SHAPE_SUFFIX,
    XSD_TYPES,
)

# Ontology keys that cannot double as the ontology's own prefix.
_RESERVED_PREFIXES = frozenset(FIXED_PREFIXES) | {"base", "prefix", "true", "false"}
FALLBACK_PREFIX = "ont"
_PREFIX_NAME = re.compile(r"[A-Za-z](?:[A-Za-z0-9_.-]*[A-Za-z0-9_-])?")

_RDF_TYPES: dict[str, URIRef] = {
    "entity_type": OWL.Class,
    "relation_type": OWL.ObjectProperty,
    "property": OWL.DatatypeProperty,
    "constraint": SH.NodeShape,
}

INDENT = "    "
# A conservative subset of Turtle's PN_LOCAL; anything else is written as a full IRI.
_LOCAL_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_IRI_UNSAFE = re.compile(r'[\x00-\x20<>"{}|^`\\]')
# Only canonical integers may be written bare: Turtle parsers read a bare 001 as 1.
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)")
_STRING_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def ontology_iri_of(base_iri: str) -> str:
    """The default IRI of the owl:Ontology: the element namespace without its trailing # or /."""
    return base_iri[:-1] if base_iri.endswith(("#", "/")) else base_iri


def own_prefix(key: str) -> str:
    return FALLBACK_PREFIX if key in _RESERVED_PREFIXES else key


def valid_prefix_name(name: str) -> bool:
    return name == "" or (name not in _RESERVED_PREFIXES and bool(_PREFIX_NAME.fullmatch(name)))


def prefix_order(item: tuple[str, str]) -> tuple[bool, str]:
    """Named prefixes before the empty one, then by name: which name a namespace gets when a
    file gives it several."""
    return (item[0] == "", item[0])


def prefix_map(key: str, base_iri: str, extra: Mapping[str, str]) -> dict[str, str]:
    """The prefixes an export uses: fixed ones, the ontology's own, then imported ones that clash
    with neither (a clash would change what an existing prefix means).

    The ontology's own namespace is named after its key, unless the stored prefixes name it
    (an ontology imported from a file keeps the file's name for it).
    """
    prefixes = dict(FIXED_PREFIXES)
    if base_iri not in prefixes.values():
        named = [
            name
            for name, namespace in sorted(extra.items(), key=prefix_order)
            if namespace == base_iri and valid_prefix_name(name)
        ]
        own = named[0] if named else own_prefix(key)
        if own not in prefixes:
            prefixes[own] = base_iri
    taken = set(prefixes.values())
    for name, namespace in sorted(extra.items(), key=prefix_order):
        if name in prefixes or namespace in taken or not valid_prefix_name(name):
            continue
        prefixes[name] = namespace
        taken.add(namespace)
    return prefixes


# ---------- graph ----------


def _list(graph: Graph, items: Sequence[Node]) -> Node:
    head: Node = RDF.nil
    for item in reversed(items):
        node = BNode()
        graph.add((node, RDF.first, item))
        graph.add((node, RDF.rest, head))
        head = node
    return head


def _integer(value: int) -> Literal:
    return Literal(str(value), datatype=XSD.integer)


def _rule_triples(graph: Graph, shape: URIRef, rule: Rule) -> None:
    node = BNode()
    graph.add((shape, SH.property, node))
    graph.add((node, SH.path, URIRef(rule.path)))
    counts = (
        (SH.minCount, rule.min_count),
        (SH.maxCount, rule.max_count),
        (SH.minLength, rule.min_length),
        (SH.maxLength, rule.max_length),
    )
    for predicate, count in counts:
        if count is not None:
            graph.add((node, predicate, _integer(count)))
    iris = ((SH.datatype, rule.datatype), (SH["class"], rule.class_), (SH.nodeKind, rule.node_kind))
    for predicate, iri in iris:
        if iri is not None:
            graph.add((node, predicate, URIRef(iri)))
    terms: tuple[tuple[URIRef, Term | None], ...] = (
        (SH.minInclusive, rule.min_inclusive),
        (SH.maxInclusive, rule.max_inclusive),
        (SH.minExclusive, rule.min_exclusive),
        (SH.maxExclusive, rule.max_exclusive),
    )
    for predicate, term in terms:
        if term is not None:
            graph.add((node, predicate, term))
    if rule.in_ is not None:
        graph.add((node, SH["in"], _list(graph, rule.in_)))
    elif rule.in_lost:
        graph.add((node, SH["in"], BNode()))
    if rule.pattern is not None:
        graph.add((node, SH.pattern, Literal(rule.pattern)))
    if rule.flags is not None:
        graph.add((node, SH.flags, Literal(rule.flags)))
    for message in rule.message:
        graph.add((node, SH.message, message))


def _element_triples(graph: Graph, state: OntologyState, element: ElementState) -> None:
    subject = URIRef(element.iri)
    graph.add((subject, RDF.type, _RDF_TYPES[element.kind]))
    texts = (
        (RDFS.label, element.label_zh, "zh"),
        (RDFS.label, element.label_en, "en"),
        (SKOS.definition, element.definition_zh, "zh"),
        (SKOS.definition, element.definition_en, "en"),
    )
    for predicate, text, lang in texts:
        if text:
            graph.add((subject, predicate, Literal(text, lang=lang)))
    for lang, text in element.synonyms:
        graph.add((subject, SKOS.altLabel, Literal(text, lang=lang)))

    # References to anything but an active object type (or relation) are left out.
    if element.kind == "entity_type":
        if element.parent and state.is_type(element.parent):
            graph.add((subject, RDFS.subClassOf, URIRef(element.parent)))
        return
    if element.kind == "constraint":
        if element.domain and state.is_type(element.domain):
            graph.add((subject, SH.targetClass, URIRef(element.domain)))
        for rule in element.rules:
            _rule_triples(graph, subject, rule)
        return
    if element.domain and state.is_type(element.domain):
        graph.add((subject, RDFS.domain, URIRef(element.domain)))
    if element.kind == "relation_type":
        if element.range and state.is_type(element.range):
            graph.add((subject, RDFS.range, URIRef(element.range)))
        inverse = state.elements.get(element.inverse) if element.inverse else None
        if inverse is not None and inverse.active and inverse.kind == "relation_type":
            graph.add((subject, OWL.inverseOf, URIRef(inverse.iri)))
        return
    if element.datatype is not None:
        graph.add((subject, RDFS.range, XSD_TYPES[element.datatype]))
    if element.unit:
        graph.add((subject, OP.unit, Literal(element.unit)))


def _auto_shapes(graph: Graph, state: OntologyState) -> None:
    active = state.active_elements()
    members = sorted(
        (e for e in active if e.kind in ("relation_type", "property") and e.auto_shape),
        key=lambda e: e.iri,
    )
    for entity in sorted(active, key=lambda e: e.iri):
        if entity.kind != "entity_type" or not entity.auto_shape:
            continue
        shape = URIRef(entity.iri + SHAPE_SUFFIX)
        graph.add((shape, RDF.type, SH.NodeShape))
        graph.add((shape, SH.targetClass, URIRef(entity.iri)))
        for member in members:
            if member.domain != entity.iri:
                continue
            node = BNode()
            graph.add((shape, SH.property, node))
            graph.add((node, SH.path, URIRef(member.iri)))
            if member.kind == "relation_type":
                if member.range and state.is_type(member.range):
                    graph.add((node, SH["class"], URIRef(member.range)))
            elif member.datatype is not None:
                graph.add((node, SH.datatype, XSD_TYPES[member.datatype]))
            if member.required:
                graph.add((node, SH.minCount, _integer(1)))
            if not member.multiple:
                graph.add((node, SH.maxCount, _integer(1)))


def _header(
    graph: Graph,
    state: OntologyState,
    version: int | None,
    created: datetime | None,
) -> None:
    ontology = URIRef(state.ontology_iri)
    graph.add((ontology, RDF.type, OWL.Ontology))
    if state.name:
        graph.add((ontology, RDFS.label, Literal(state.name)))
    if state.description:
        graph.add((ontology, DCTERMS.description, Literal(state.description)))
    # An imported file's own version and date win over the generated ones.
    kept = {p for axiom in state.axioms for s, p, _ in axiom.triples if s == ontology}
    if version is not None and OWL.versionInfo not in kept:
        graph.add((ontology, OWL.versionInfo, Literal(str(version))))
    if created is not None and DCTERMS.created not in kept:
        graph.add((ontology, DCTERMS.created, created_literal(created)))


def created_literal(created: datetime) -> Literal:
    """The dcterms:created value an export writes (an import of the export absorbs it)."""
    return Literal(created.astimezone(UTC).replace(microsecond=0), datatype=XSD.dateTime)


def build_graph(
    state: OntologyState,
    *,
    version: int | None,
    created: datetime | None,
    declarations: bool = True,
    axioms: Iterable[Triple] | None = None,
) -> Graph:
    """The RDF graph of the active content. `axioms` replaces the state's axioms when given."""
    graph = Graph(bind_namespaces="none")
    _header(graph, state, version, created)
    for element in sorted(state.active_elements(), key=lambda e: e.iri):
        if element.kind != "metric":
            _element_triples(graph, state, element)
    _auto_shapes(graph, state)
    if axioms is None:
        for axiom in state.axioms:
            for triple in axiom.triples:
                graph.add(triple)
    else:
        for triple in axioms:
            graph.add(triple)
    if declarations:
        for triple in missing_declarations(graph):
            graph.add(triple)
    return graph


def export(
    state: OntologyState,
    prefixes: Mapping[str, str],
    *,
    version: int | None,
    created: datetime | None,
) -> str:
    graph = build_graph(state, version=version, created=created)
    return TurtleWriter(graph, prefixes).document(URIRef(state.ontology_iri))


def fragment(triples: Iterable[Triple], prefixes: Mapping[str, str]) -> str:
    """Turtle for one axiom, without prefix lines; parsed back with the same prefixes."""
    graph = Graph(bind_namespaces="none")
    for triple in triples:
        graph.add(triple)
    return TurtleWriter(graph, prefixes).fragment()


# ---------- Turtle ----------


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


class TurtleWriter:
    """Writes any graph deterministically (see the module docstring)."""

    def __init__(self, graph: Graph, prefixes: Mapping[str, str]) -> None:
        self._graph = graph
        self._prefixes = sorted(prefixes.items())
        # Longest namespace first, so that the most specific prefix wins.
        self._by_length = sorted(self._prefixes, key=lambda item: -len(item[1]))
        self._refs: Counter[BNode] = Counter(o for _, _, o in graph if isinstance(o, BNode))
        self._inline = {node for node, count in self._refs.items() if count == 1}
        self._break_cycles()
        self._labels = self._assign_labels()

    # ----- structure -----

    def _shape(self, node: Node) -> str:
        """A node's statements with blank node objects blanked out, for a stable order."""
        pairs = sorted(
            f"{p.n3()} {'[]' if isinstance(o, BNode) else o.n3()}"
            for p, o in self._graph.predicate_objects(node)
        )
        return "\n".join(pairs)

    def _break_cycles(self) -> None:
        """Blank nodes that reach themselves through inline objects need a label instead.

        An inline node is referenced exactly once, so following that reference upwards from
        any node either leaves the inline nodes or runs into a cycle; each cycle loses one
        node (the one with the smallest shape) to labelling. Linear, without recursion.
        """
        parent: dict[Node, Node] = {}
        for subject, _, value in self._graph:
            if isinstance(value, BNode) and value in self._inline:
                parent[value] = subject
        state: dict[Node, int] = {}  # 1: on the current walk, 2: done
        for start in sorted(self._inline, key=str):
            walk: list[Node] = []
            node: Node | None = start
            while isinstance(node, BNode) and node in self._inline and node not in state:
                state[node] = 1
                walk.append(node)
                node = parent.get(node)
            if node is not None and state.get(node) == 1:
                cycle = walk[walk.index(node) :]
                breaker = min(cycle, key=lambda n: (self._shape(n), str(n)))
                self._inline.discard(breaker)
            for visited in walk:
                state[visited] = 2

    def _assign_labels(self) -> dict[BNode, str]:
        labelled = [node for node in self._refs if node not in self._inline]
        ordered = sorted(labelled, key=lambda node: (self._shape(node), str(node)))
        return {node: f"b{index}" for index, node in enumerate(ordered)}

    def _list_items(self, node: Node) -> list[Node] | None:
        """The members if `node` is a well-formed inline RDF list, otherwise None."""
        items: list[Node] = []
        current = node
        while current != RDF.nil:
            if not isinstance(current, BNode) or current not in self._inline:
                return None
            pairs = list(self._graph.predicate_objects(current))
            firsts = [o for p, o in pairs if p == RDF.first]
            rests = [o for p, o in pairs if p == RDF.rest]
            if len(pairs) != 2 or len(firsts) != 1 or len(rests) != 1:
                return None
            items.append(firsts[0])
            current = rests[0]
        return items

    # ----- output -----

    def document(self, first: URIRef) -> str:
        header = "".join(
            f"@prefix {prefix}: <{_escape_iri(namespace)}> .\n"
            for prefix, namespace in self._prefixes
        )
        return header + "\n" + self.fragment(first) + "\n"

    def fragment(self, first: URIRef | None = None) -> str:
        subjects = {s for s in self._graph.subjects() if isinstance(s, URIRef)}
        named = sorted(subjects, key=lambda subject: (subject != first, str(subject)))
        blocks = [f"{self._iri(subject)} {self._predicates(subject, 1)} ." for subject in named]
        labelled = sorted(self._labels.items(), key=lambda item: int(item[1][1:]))
        blocks.extend(
            f"_:{label} {self._predicates(node, 1)} ."
            for node, label in labelled
            if (node, None, None) in self._graph
        )
        roots = {s for s in self._graph.subjects() if isinstance(s, BNode) and s not in self._refs}
        blocks.extend(sorted(f"{self._inline_node(node, 0)} ." for node in roots))
        return "\n\n".join(blocks)

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

    def _inline_node(self, node: BNode, depth: int) -> str:
        if (node, None, None) not in self._graph:
            return "[]"
        inner = INDENT * (depth + 1)
        return f"[\n{inner}{self._predicates(node, depth + 1)}\n{INDENT * depth}]"

    def _object(self, value: Node, depth: int) -> str:
        if value == RDF.nil:
            return "()"
        if isinstance(value, BNode):
            if value in self._labels:
                return f"_:{self._labels[value]}"
            items = self._list_items(value)
            if items is not None:
                return "( " + " ".join(self._object(item, depth + 1) for item in items) + " )"
            return self._inline_node(value, depth)
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
