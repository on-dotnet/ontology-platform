"""From a Turtle or RDF/XML file to an `OntologyState` (spec 002, 4.1).

What the platform can represent becomes elements; everything else stays as axioms, so that
writing the state gives back every triple of the file. A triple is only absorbed into an
element when the writer reproduces it exactly; the rest of the file is kept as it was.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from xml.sax import SAXParseException

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontology_platform.modules.ontology.rdf.axioms import axioms_of
from ontology_platform.modules.ontology.rdf.declarations import (
    implied_declarations,
    missing_declarations,
)
from ontology_platform.modules.ontology.rdf.model import (
    ElementState,
    OntologyState,
    Rule,
    Term,
    Triple,
)
from ontology_platform.modules.ontology.rdf.vocab import (
    DATATYPE_OF,
    DECLARATION_TYPES,
    ELEMENT_TYPES,
    NODE_KINDS,
    OP,
    SH,
    SHAPE_SUFFIX,
    XSD_TYPES,
    is_reserved,
)
from ontology_platform.modules.ontology.rdf.writer import build_graph

MAX_BYTES = 5 * 1024 * 1024
MAX_TRIPLES = 50_000
# Base for relative IRIs in a file that sets none (never the server's own path).
PUBLIC_ID = "urn:x-import:"
LABEL_MAX = 200
UNIT_MAX = 32
DEFINITION_MAX = 4000
DESCRIPTION_MAX = 2000

_XML_START = re.compile(rb"\s*(<\?xml|<!DOCTYPE|<!--|<[A-Za-z_][\w.-]*:RDF[\s>]|<RDF[\s>])")
_RDF_ROOT = re.compile(rb"<([A-Za-z_][\w.-]*:)?RDF[\s>]")
_EXTERNAL_ENTITY = re.compile(rb"<!(ENTITY|DOCTYPE)[^>]*\b(SYSTEM|PUBLIC)\b", re.IGNORECASE)
_LINE = re.compile(r"line[: ]+(\d+)", re.IGNORECASE)
_PLACEHOLDER_CREATED = datetime(2000, 1, 1, tzinfo=UTC)
_TYPE_OF_KIND = {kind: rdf_type for rdf_type, kind in ELEMENT_TYPES.items()}


class RdfInputError(Exception):
    """A file or fragment that cannot be read; `code` is the problem+json code."""

    def __init__(self, code: str, detail: str, *, line: int | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.line = line


# ---------- parsing ----------


def _format(data: bytes) -> str:
    head = data[:65536].lstrip(b"\xef\xbb\xbf")
    if not _XML_START.match(head):
        return "turtle"
    if b"http://www.w3.org/1999/02/22-rdf-syntax-ns#" in head and _RDF_ROOT.search(head):
        return "xml"
    # Other XML, such as OWL/XML, is not supported.
    raise RdfInputError("import.unsupported_format", "Only Turtle and RDF/XML can be imported.")


def _line_of(error: Exception) -> int | None:
    if isinstance(error, SAXParseException):
        return error.getLineNumber()
    match = _LINE.search(str(error))
    return int(match.group(1)) if match else None


def parse_document(data: bytes) -> Graph:
    """Parse an uploaded file; nothing is fetched (owl:imports are kept, never loaded)."""
    if len(data) > MAX_BYTES:
        raise RdfInputError("import.too_large", "The file is larger than 5 MB.")
    kind = _format(data)
    graph = Graph(bind_namespaces="none")
    try:
        if kind == "xml":
            if _EXTERNAL_ENTITY.search(data):
                raise RdfInputError(
                    "import.unsupported_format",
                    "RDF/XML with external entities or DTDs is not supported.",
                )
            graph.parse(data=data, format="xml", publicID=PUBLIC_ID)
        else:
            try:
                text = data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise RdfInputError(
                    "import.unsupported_format",
                    "The file is not UTF-8 encoded Turtle.",
                ) from exc
            graph.parse(data=text, format="turtle", publicID=PUBLIC_ID)
    except RdfInputError:
        raise
    except Exception as exc:  # rdflib raises many types for malformed input
        raise RdfInputError(
            "import.parse_error",
            "The file is not valid " + ("RDF/XML." if kind == "xml" else "Turtle."),
            line=_line_of(exc),
        ) from exc
    if len(graph) == 0:
        raise RdfInputError("import.empty", "The file contains no triples.")
    if len(graph) > MAX_TRIPLES:
        raise RdfInputError("import.too_many_triples", "The file has more than 50,000 triples.")
    return graph


def parse_fragment(text: str, prefixes: Mapping[str, str]) -> list[Triple]:
    """Triples of an axiom fragment written with the ontology's prefixes."""
    header = "".join(f"@prefix {name}: <{iri}> .\n" for name, iri in sorted(prefixes.items()))
    graph = Graph(bind_namespaces="none")
    try:
        graph.parse(data=header + text, format="turtle", publicID=PUBLIC_ID)
    except Exception as exc:
        line = _line_of(exc)
        if line is not None:
            line = max(1, line - len(prefixes))
        raise RdfInputError(
            "axiom.invalid", "The fragment is not valid Turtle.", line=line
        ) from exc
    return list(graph)


# ---------- reading ----------


@dataclass
class ReadResult:
    state: OntologyState
    # The namespace most element IRIs share, as a base for elements made later in the platform.
    base_iri: str | None
    prefixes: dict[str, str]
    # The ontology IRI the file itself declared, if any.
    file_ontology_iri: str | None
    warnings: Counter[str] = field(default_factory=Counter)


def _clean(value: Node, limit: int) -> str | None:
    """The text of a literal the platform can hold unchanged, else None."""
    if not isinstance(value, Literal):
        return None
    text = str(value)
    if not text or text != text.strip() or len(text) > limit:
        return None
    return text


def _plain(value: Node) -> bool:
    return isinstance(value, Literal) and value.language is None and value.datatype is None


def _namespace(iri: str) -> str:
    for separator in ("#", "/", ":"):
        index = iri.rfind(separator)
        if index > 0:
            return iri[: index + 1]
    return iri


def _rename(node: Node, old: URIRef, new: URIRef) -> Node:
    return new if node == old else node


def unshare(graph: Graph) -> Graph:
    """The graph with every blank node used as an object more than once copied per use.

    OWL 2 does not share anonymous structures, but OWL API writes equal lists (such as the
    `( true )` of several sh:in) once and points to that node from each place. Copying keeps
    each statement's structure on its own, so it compares equal to the file before Protégé.
    """
    refs = Counter(o for _, _, o in graph if isinstance(o, BNode))
    if all(count <= 1 for count in refs.values()):
        return graph
    out = Graph(bind_namespaces="none")
    for prefix, namespace in graph.namespaces():
        out.bind(prefix, namespace)
    # Blank nodes in a cycle are kept as they are, with their own statements.
    kept: set[Node] = set()

    def copy(node: Node, path: frozenset[Node]) -> Node:
        if not isinstance(node, BNode):
            return node
        if node in path:
            kept.add(node)
            return node
        fresh = BNode()
        for predicate, value in graph.predicate_objects(node):
            out.add((fresh, predicate, copy(value, path | {node})))
        return fresh

    roots = [t for t in graph if not (isinstance(t[0], BNode) and t[0] in refs)]
    reachable: set[Node] = set()
    stack = [o for _, _, o in roots if isinstance(o, BNode)]
    while stack:
        node = stack.pop()
        if node not in reachable:
            reachable.add(node)
            stack.extend(o for o in graph.objects(node) if isinstance(o, BNode))
    for subject, predicate, value in roots:
        out.add((subject, predicate, copy(value, frozenset({subject}))))
    for subject, predicate, value in graph:
        shared = isinstance(subject, BNode) and subject in refs
        if shared and (subject not in reachable or subject in kept):
            out.add((subject, predicate, value))
    return out


class _Reader:
    def __init__(self, graph: Graph, ontology_iri: str, absorb: Mapping[URIRef, Literal]) -> None:
        self.graph = graph
        self.remaining: set[Triple] = set(graph)
        self.ontology = URIRef(ontology_iri)
        self.absorb = absorb
        self.state = OntologyState(ontology_iri=ontology_iri)
        self.warnings: Counter[str] = Counter()
        self.refs: Counter[Node] = Counter(o for _, _, o in graph if isinstance(o, BNode))
        self.object_iris: set[Node] = {o for _, _, o in graph if isinstance(o, URIRef)}

    # ----- helpers -----

    def take(self, triple: Triple) -> None:
        self.remaining.discard(triple)

    def left(self, subject: Node, predicate: Node) -> list[Node]:
        values = [
            o
            for o in self.graph.objects(subject, predicate)
            if (subject, predicate, o) in self.remaining
        ]
        return sorted(values, key=lambda value: value.n3())

    def text(self, subject: URIRef, predicate: URIRef, lang: str, limit: int) -> str | None:
        for value in self.left(subject, predicate):
            if isinstance(value, Literal) and value.language == lang and value.datatype is None:
                text = _clean(value, limit)
                if text is not None:
                    self.take((subject, predicate, value))
                    return text
        return None

    def single(self, subject: URIRef, predicate: URIRef) -> Node | None:
        values = list(self.graph.objects(subject, predicate))
        if len(values) != 1 or (subject, predicate, values[0]) not in self.remaining:
            return None
        return values[0]

    def element(self, iri: Node, *kinds: str) -> ElementState | None:
        element = self.state.elements.get(str(iri)) if isinstance(iri, URIRef) else None
        return element if element is not None and element.kind in kinds else None

    # ----- steps -----

    def header(self) -> None:
        ontology = self.ontology
        if (ontology, RDF.type, OWL.Ontology) not in self.remaining:
            return
        self.take((ontology, RDF.type, OWL.Ontology))
        labels = [v for v in self.left(ontology, RDFS.label) if _plain(v)]
        if len(labels) == 1 and _clean(labels[0], LABEL_MAX):
            self.state.name = str(labels[0])
            self.take((ontology, RDFS.label, labels[0]))
        descriptions = [v for v in self.left(ontology, DCTERMS.description) if _plain(v)]
        if len(descriptions) == 1 and _clean(descriptions[0], DESCRIPTION_MAX):
            self.state.description = str(descriptions[0])
            self.take((ontology, DCTERMS.description, descriptions[0]))
        for predicate, value in self.absorb.items():
            self.take((ontology, predicate, value))

    def anonymous_headers(self) -> None:
        # OWL API writes `[] a owl:Ontology` for a file that names no ontology.
        for node in list(self.graph.subjects(RDF.type, OWL.Ontology)):
            if not isinstance(node, BNode) or node in self.refs:
                continue
            if len(list(self.graph.predicate_objects(node))) == 1:
                self.take((node, RDF.type, OWL.Ontology))

    def elements(self) -> None:
        kinds: dict[URIRef, set[str]] = defaultdict(set)
        for rdf_type, kind in ELEMENT_TYPES.items():
            for subject in self.graph.subjects(RDF.type, rdf_type):
                if (
                    isinstance(subject, URIRef)
                    and subject != self.ontology
                    and not is_reserved(str(subject))
                ):
                    kinds[subject].add(kind)
        for subject in sorted(kinds, key=str):
            if len(kinds[subject]) != 1:
                continue  # punning: keep everything as axioms
            (kind,) = kinds[subject]
            self.state.elements[str(subject)] = ElementState(
                kind=kind,
                iri=str(subject),
                multiple=True,
                auto_shape=False,
            )
            self.take((subject, RDF.type, _TYPE_OF_KIND[kind]))

    def fields(self) -> None:
        for element in self.state.elements.values():
            subject = URIRef(element.iri)
            element.label_zh = self.text(subject, RDFS.label, "zh", LABEL_MAX)
            element.label_en = self.text(subject, RDFS.label, "en", LABEL_MAX)
            element.definition_zh = self.text(subject, SKOS.definition, "zh", DEFINITION_MAX)
            element.definition_en = self.text(subject, SKOS.definition, "en", DEFINITION_MAX)
            element.synonyms = self.synonyms(subject)
            if element.kind == "entity_type":
                self.parent(element, subject)
            else:
                self.references(element, subject)

    def synonyms(self, subject: URIRef) -> tuple[tuple[str, str], ...]:
        found: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for value in self.left(subject, SKOS.altLabel):
            if not isinstance(value, Literal) or value.datatype is not None:
                continue
            lang = value.language
            text = _clean(value, LABEL_MAX)
            if lang not in ("zh", "en") or text is None or (lang, text.casefold()) in seen:
                continue
            seen.add((lang, text.casefold()))
            found.append((lang, text))
            self.take((subject, SKOS.altLabel, value))
        return tuple(found)

    def parent(self, element: ElementState, subject: URIRef) -> None:
        named = [v for v in self.graph.objects(subject, RDFS.subClassOf) if isinstance(v, URIRef)]
        if len(named) > 1:
            self.warnings["multiple_parents"] += 1
        if len(named) == 1 and named[0] != subject and self.element(named[0], "entity_type"):
            element.parent = str(named[0])
            self.take((subject, RDFS.subClassOf, named[0]))

    def references(self, element: ElementState, subject: URIRef) -> None:
        domain = self.single(subject, RDFS.domain)
        if domain is not None and self.element(domain, "entity_type"):
            element.domain = str(domain)
            self.take((subject, RDFS.domain, domain))
        target = self.single(subject, RDFS.range)
        if element.kind == "relation_type":
            if target is not None and self.element(target, "entity_type"):
                element.range = str(target)
                self.take((subject, RDFS.range, target))
            inverse = self.single(subject, OWL.inverseOf)
            if (
                inverse is not None
                and inverse != subject
                and self.element(inverse, "relation_type")
            ):
                element.inverse = str(inverse)
                self.take((subject, OWL.inverseOf, inverse))
            return
        if isinstance(target, URIRef) and target in DATATYPE_OF:
            element.datatype = DATATYPE_OF[target]
            self.take((subject, RDFS.range, target))
        unit = self.single(subject, OP.unit)
        if unit is not None and _plain(unit) and _clean(unit, UNIT_MAX):
            element.unit = str(unit)
            self.take((subject, OP.unit, unit))

    def break_cycles(self) -> None:
        elements = self.state.elements
        for element in sorted(elements.values(), key=lambda e: e.iri):
            seen: set[str] = set()
            current = element.parent
            while current is not None and current not in seen and current != element.iri:
                seen.add(current)
                parent = elements.get(current)
                current = parent.parent if parent else None
            if current == element.iri and element.parent is not None:
                self.remaining.add((URIRef(element.iri), RDFS.subClassOf, URIRef(element.parent)))
                element.parent = None

    # ----- shapes -----

    def own_bnode(self, node: Node) -> bool:
        """A blank node used exactly once, as an object, and still unclaimed."""
        return isinstance(node, BNode) and self.refs[node] == 1

    def subject_triples(self, subject: Node) -> list[Triple]:
        """The statements about a shape, without its owl:NamedIndividual declaration (OWL API
        declares every shape so; the declaration is absorbed with the other ones)."""
        return [
            (subject, p, o)
            for p, o in self.graph.predicate_objects(subject)
            if not (p == RDF.type and o == OWL.NamedIndividual)
        ]

    def auto_shapes(self) -> None:
        elements = self.state.elements
        for entity in sorted(elements.values(), key=lambda e: e.iri):
            if entity.kind != "entity_type":
                continue
            shape = URIRef(entity.iri + SHAPE_SUFFIX)
            claimed = self.auto_shape(entity, shape)
            if claimed is None:
                continue
            members, triples = claimed
            for triple in triples:
                self.take(triple)
            entity.auto_shape = True
            for member, required, multiple in members:
                member.auto_shape = True
                member.required = required
                member.multiple = multiple

    def auto_shape(
        self,
        entity: ElementState,
        shape: URIRef,
    ) -> tuple[list[tuple[ElementState, bool, bool]], list[Triple]] | None:
        own = self.subject_triples(shape)
        if not own or shape in self.object_iris or any(t not in self.remaining for t in own):
            return None
        if (shape, RDF.type, SH.NodeShape) not in self.graph:
            return None
        if (shape, SH.targetClass, URIRef(entity.iri)) not in self.graph:
            return None
        triples = list(own)
        members: list[tuple[ElementState, bool, bool]] = []
        paths: set[str] = set()
        for _, predicate, value in own:
            if predicate == RDF.type and value == SH.NodeShape:
                continue
            if predicate == SH.targetClass and value == URIRef(entity.iri):
                continue
            if predicate != SH.property or not self.own_bnode(value):
                return None
            claimed = self.auto_member(entity, value)
            if claimed is None or claimed[0].iri in paths:
                return None
            paths.add(claimed[0].iri)
            members.append(claimed[:3])
            triples.extend(claimed[3])
        return members, triples

    def auto_member(
        self,
        entity: ElementState,
        node: Node,
    ) -> tuple[ElementState, bool, bool, list[Triple]] | None:
        pairs = list(self.graph.predicate_objects(node))
        by_predicate: dict[Node, list[Node]] = defaultdict(list)
        for predicate, value in pairs:
            by_predicate[predicate].append(value)
        if any(len(values) != 1 for values in by_predicate.values()):
            return None
        if set(by_predicate) - {SH.path, SH.datatype, SH["class"], SH.minCount, SH.maxCount}:
            return None
        path = by_predicate.get(SH.path, [None])[0]
        member = self.element(path, "relation_type", "property") if path is not None else None
        if member is None or member.domain != entity.iri:
            return None
        one = Literal("1", datatype=XSD.integer)
        for predicate in (SH.minCount, SH.maxCount):
            if predicate in by_predicate and by_predicate[predicate][0] != one:
                return None
        datatype = by_predicate.get(SH.datatype, [None])[0]
        class_ = by_predicate.get(SH["class"], [None])[0]
        if member.kind == "property":
            expected = XSD_TYPES[member.datatype] if member.datatype else None
            if class_ is not None or datatype != expected:
                return None
        else:
            expected_class = URIRef(member.range) if member.range else None
            if datatype is not None or class_ != expected_class:
                return None
        triples = [(node, p, o) for p, o in pairs]
        if any(t not in self.remaining for t in triples):
            return None
        return member, SH.minCount in by_predicate, SH.maxCount not in by_predicate, triples

    def constraints(self) -> None:
        candidates = sorted(
            (s for s in self.graph.subjects(RDF.type, SH.NodeShape) if isinstance(s, URIRef)),
            key=str,
        )
        for shape in candidates:
            if str(shape) in self.state.elements or shape in self.object_iris:
                continue
            if is_reserved(str(shape)):
                continue
            own = self.subject_triples(shape)
            if any(t not in self.remaining for t in own):
                continue
            read = self.constraint(shape, own)
            if read is None:
                self.warnings["unsupported_shape"] += 1
                continue
            element, triples = read
            self.state.elements[element.iri] = element
            for triple in triples:
                self.take(triple)

    def constraint(
        self,
        shape: URIRef,
        own: list[Triple],
    ) -> tuple[ElementState, list[Triple]] | None:
        element = ElementState(kind="constraint", iri=str(shape), multiple=True)
        triples = list(own)
        targets: list[Node] = []
        labels: dict[str, list[Node]] = defaultdict(list)
        rules: list[Rule] = []
        for _, predicate, value in own:
            if predicate == RDF.type:
                if value != SH.NodeShape:
                    return None
            elif predicate == SH.targetClass:
                targets.append(value)
            elif predicate == RDFS.label and isinstance(value, Literal) and value.datatype is None:
                if value.language not in ("zh", "en") or _clean(value, LABEL_MAX) is None:
                    return None
                labels[value.language].append(value)
            elif predicate == SH.property and self.own_bnode(value):
                read = self.rule(value)
                if read is None:
                    return None
                rules.append(read[0])
                triples.extend(read[1])
            else:
                return None
        if len(targets) != 1 or not self.element(targets[0], "entity_type"):
            return None
        if any(len(values) > 1 for values in labels.values()):
            return None
        element.domain = str(targets[0])
        element.label_zh = str(labels["zh"][0]) if labels["zh"] else None
        element.label_en = str(labels["en"][0]) if labels["en"] else None
        element.rules = tuple(sorted(rules, key=lambda rule: repr(rule.key())))
        if any(t not in self.remaining for t in triples):
            return None
        return element, triples

    def rule(self, node: Node) -> tuple[Rule, list[Triple]] | None:
        pairs = list(self.graph.predicate_objects(node))
        triples: list[Triple] = [(node, p, o) for p, o in pairs]
        values: dict[Node, list[Node]] = defaultdict(list)
        for predicate, value in pairs:
            values[predicate].append(value)
        messages = values.pop(SH.message, [])
        if any(len(found) != 1 for found in values.values()):
            return None
        single = {predicate: found[0] for predicate, found in values.items()}
        path = single.pop(SH.path, None)
        if path is None or not self.element(path, "relation_type", "property"):
            return None
        fields: dict[str, object] = {"path": str(path)}
        counts = {
            SH.minCount: "min_count",
            SH.maxCount: "max_count",
            SH.minLength: "min_length",
            SH.maxLength: "max_length",
        }
        for predicate, name in counts.items():
            if predicate in single:
                count = self.count(single.pop(predicate))
                if count is None:
                    return None
                fields[name] = count
        if SH.datatype in single:
            datatype = single.pop(SH.datatype)
            if not isinstance(datatype, URIRef):
                return None
            fields["datatype"] = str(datatype)
        if SH["class"] in single:
            target = single.pop(SH["class"])
            if not self.element(target, "entity_type"):
                return None
            fields["class_"] = str(target)
        if SH.nodeKind in single:
            node_kind = single.pop(SH.nodeKind)
            if node_kind not in NODE_KINDS:
                return None
            fields["node_kind"] = str(node_kind)
        bounds = {
            SH.minInclusive: "min_inclusive",
            SH.maxInclusive: "max_inclusive",
            SH.minExclusive: "min_exclusive",
            SH.maxExclusive: "max_exclusive",
        }
        for predicate, name in bounds.items():
            if predicate in single:
                bound = single.pop(predicate)
                if not isinstance(bound, Literal | URIRef):
                    return None
                fields[name] = bound
        for predicate, name in ((SH.pattern, "pattern"), (SH.flags, "flags")):
            if predicate in single:
                text = single.pop(predicate)
                if not _plain(text):
                    return None
                fields[name] = str(text)
        if SH["in"] in single:
            head = single.pop(SH["in"])
            if self.own_bnode(head) and (head, None, None) not in self.graph:
                # OWL API drops lists used as annotation values and leaves `sh:in [ ]`.
                fields["in_lost"] = True
                self.warnings["lost_list"] += 1
            else:
                listed = self.list_items(head)
                if listed is None:
                    return None
                items, list_triples = listed
                fields["in_"] = items
                triples.extend(list_triples)
        if single:
            return None
        if any(not isinstance(m, Literal) or m.datatype is not None for m in messages):
            return None
        fields["message"] = tuple(sorted((m for m in messages if isinstance(m, Literal)), key=str))
        return Rule(**fields), triples  # type: ignore[arg-type]

    @staticmethod
    def count(value: Node) -> int | None:
        if not isinstance(value, Literal) or value.datatype != XSD.integer:
            return None
        lexical = str(value)
        if not lexical.isdigit() or str(int(lexical)) != lexical:
            return None
        return int(lexical)

    def list_items(self, head: Node) -> tuple[tuple[Term, ...], list[Triple]] | None:
        items: list[Term] = []
        triples: list[Triple] = []
        node = head
        while node != RDF.nil:
            if not self.own_bnode(node):
                return None
            pairs = list(self.graph.predicate_objects(node))
            firsts = [o for p, o in pairs if p == RDF.first]
            rests = [o for p, o in pairs if p == RDF.rest]
            if len(pairs) != 2 or len(firsts) != 1 or len(rests) != 1:
                return None
            if not isinstance(firsts[0], Literal | URIRef):
                return None
            items.append(firsts[0])
            triples.extend((node, p, o) for p, o in pairs)
            node = rests[0]
        return tuple(items), triples

    # ----- leftovers -----

    def axioms(self) -> None:
        residual = set(self.remaining)
        declarations = {
            t
            for t in residual
            if t[1] == RDF.type and t[2] in DECLARATION_TYPES and isinstance(t[0], URIRef)
        }
        rest = residual - declarations

        def implied(kept: set[Triple]) -> set[Triple]:
            graph = build_graph(
                self.state,
                version=None,
                created=_PLACEHOLDER_CREATED,
                declarations=False,
                axioms=rest | kept,
            )
            return implied_declarations(graph)

        # Declarations the export adds again by itself are not stored; check that dropping them
        # leaves them implied, and keep any that would otherwise get lost.
        absorbed = declarations & implied(declarations)
        while absorbed:
            missing = absorbed - implied(declarations - absorbed)
            if not missing:
                break
            absorbed -= missing
        self.state.axioms = axioms_of(rest | (declarations - absorbed))
        self.warnings["non_standard"] += sum(axiom.non_standard for axiom in self.state.axioms)


def read(
    graph: Graph,
    *,
    ontology_iri: str | None = None,
    fallback_iri: str = "urn:x-ontology",
    absorb: Mapping[URIRef, Literal] | None = None,
) -> ReadResult:
    """Map a parsed file onto platform elements and axioms.

    `ontology_iri` is the IRI of the ontology being imported into; the file's own ontology IRI
    (if different) is renamed to it. Without it the file's IRI is used, or `fallback_iri`.
    `absorb` lists header values the platform itself would generate (such as dcterms:created of
    a working-version export) so that importing an export again does not keep them as axioms.
    """
    named = sorted(
        (s for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)),
        key=str,
    )
    file_iri = named[0] if named else None
    target = URIRef(ontology_iri) if ontology_iri else (file_iri or URIRef(fallback_iri))
    work = Graph(bind_namespaces="none")
    for s, p, o in graph:
        if file_iri is not None:
            s, o = _rename(s, file_iri, target), _rename(o, file_iri, target)
        work.add((s, p, o))
    work = unshare(work)
    # Read the file as OWL API does: an entity that is only used is still an entity of its
    # kind. Otherwise the copy Protégé saves (with those declarations) would read differently.
    for triple in missing_declarations(work):
        work.add(triple)
    reader = _Reader(work, str(target), absorb or {})
    reader.header()
    reader.anonymous_headers()
    reader.elements()
    reader.fields()
    reader.break_cycles()
    reader.auto_shapes()
    reader.constraints()
    reader.axioms()

    namespaces = Counter(_namespace(iri) for iri in reader.state.elements)
    base = namespaces.most_common(1)[0][0] if namespaces else None
    prefixes = {str(name): str(namespace) for name, namespace in graph.namespaces()}
    return ReadResult(
        state=reader.state,
        base_iri=base,
        prefixes=prefixes,
        file_ontology_iri=str(file_iri) if file_iri is not None else None,
        warnings=reader.warnings,
    )


def with_ontology_iri(result: ReadResult, ontology_iri: str) -> OntologyState:
    """The state with another ontology IRI, for a file that named none."""
    return replace(result.state, ontology_iri=ontology_iri)
