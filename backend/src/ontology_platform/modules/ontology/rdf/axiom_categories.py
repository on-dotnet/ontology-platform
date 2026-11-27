"""Read-only descriptions of retained Turtle fragments, independent of prefix spelling."""

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from rdflib import Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS

from ontology_platform.modules.ontology.rdf.reader import RdfInputError, parse_fragment
from ontology_platform.modules.ontology.rdf.vocab import SH, SH_NAMESPACE, is_builtin
from ontology_platform.modules.ontology.schemas import AxiomCategory

type Prefixes = tuple[tuple[str, str], ...]

_LOGIC_PREDICATES = {
    RDFS.domain,
    RDFS.range,
    RDFS.subPropertyOf,
    OWL.onProperty,
    OWL.onProperties,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.hasValue,
    OWL.hasSelf,
    OWL.onClass,
    OWL.onDataRange,
    OWL.cardinality,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.qualifiedCardinality,
    OWL.minQualifiedCardinality,
    OWL.maxQualifiedCardinality,
    OWL.equivalentClass,
    OWL.equivalentProperty,
    OWL.disjointWith,
    OWL.disjointUnionOf,
    OWL.propertyDisjointWith,
    OWL.propertyChainAxiom,
    OWL.unionOf,
    OWL.intersectionOf,
    OWL.complementOf,
    OWL.datatypeComplementOf,
    OWL.oneOf,
    OWL.inverseOf,
    OWL.hasKey,
    OWL.sameAs,
    OWL.differentFrom,
    OWL.distinctMembers,
    OWL.onDatatype,
    OWL.withRestrictions,
}
_LOGIC_TYPES = {
    OWL.Restriction,
    OWL.AllDisjointClasses,
    OWL.AllDisjointProperties,
    OWL.AllDifferent,
    OWL.NegativePropertyAssertion,
    OWL.TransitiveProperty,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
}
_ANNOTATIONS = {
    RDFS.label,
    RDFS.comment,
    RDFS.seeAlso,
    RDFS.isDefinedBy,
    OWL.versionInfo,
    OWL.versionIRI,
    OWL.priorVersion,
    OWL.backwardCompatibleWith,
    OWL.incompatibleWith,
    OWL.deprecated,
    SKOS.prefLabel,
    SKOS.altLabel,
    SKOS.hiddenLabel,
    SKOS.definition,
    SKOS.note,
    SKOS.changeNote,
    SKOS.editorialNote,
    SKOS.historyNote,
    SKOS.scopeNote,
    SKOS.example,
}
_NOTES = (SH.message, RDFS.comment, SKOS.definition)
# Code lists: membership, notation and the links between concepts.
_CODE_PREDICATES = {
    SKOS.inScheme,
    SKOS.notation,
    SKOS.topConceptOf,
    SKOS.hasTopConcept,
    SKOS.broader,
    SKOS.narrower,
    SKOS.broaderTransitive,
    SKOS.narrowerTransitive,
    SKOS.related,
    SKOS.member,
    SKOS.memberList,
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
}
# Large imported ontologies keep tens of thousands of fragments; a smaller cache thrashes.
FRAGMENT_CACHE_SIZE = 65536
_DECLARES_ANNOTATION = "AnnotationProperty"


@dataclass(frozen=True, slots=True)
class FragmentInfo:
    category: AxiomCategory
    note: str | None
    unknown_predicates: frozenset[str]
    declares: frozenset[str]


@lru_cache(maxsize=FRAGMENT_CACHE_SIZE)
def fragment_info(turtle: str, prefixes: Prefixes) -> FragmentInfo:
    try:
        triples = parse_fragment(turtle, dict(prefixes))
    except RdfInputError:
        # Historical or invalid proposals must still be reviewable as submitted.
        return FragmentInfo("other", None, frozenset(), frozenset())
    predicates = {p for _, p, _ in triples}
    types = {o for _, p, o in triples if p == RDF.type and isinstance(o, URIRef)}
    unknown = frozenset(
        str(p)
        for p in predicates
        if p not in _ANNOTATIONS and not str(p).startswith((str(DC), str(DCTERMS)))
    )
    declares = frozenset(
        str(s)
        for s, p, o in triples
        if p == RDF.type and o == OWL.AnnotationProperty and isinstance(s, URIRef)
    )
    category: AxiomCategory
    if any(str(term).startswith(SH_NAMESPACE) for term in predicates | types):
        category = "shape"
    elif predicates & _LOGIC_PREDICATES or types & _LOGIC_TYPES:
        category = "logic"
    elif predicates & _CODE_PREDICATES or any(
        t in (OWL.NamedIndividual, OWL.Thing, OWL.Nothing, RDFS.Resource)
        or not str(t).startswith((str(OWL), str(RDFS), str(RDF)))
        for t in types
    ):
        category = "individual"
    elif any(p == RDFS.subClassOf and isinstance(o, URIRef) for _, p, o in triples):
        category = "parent"
    elif predicates and not unknown:
        category = "annotation"
    else:
        category = "other"
    # RDF graphs are unordered. Break ties between notes of equal priority by lexical value.
    notes = [
        (_NOTES.index(p), str(o))
        for _, p, o in triples
        if isinstance(p, URIRef)
        and p in _NOTES
        and isinstance(o, Literal)
        and (o.language or "").lower() == "zh"
        and str(o).strip()
    ]
    return FragmentInfo(category, min(notes)[1] if notes else None, unknown, declares)


def declared_annotations(fragments: Iterable[str], prefixes: Prefixes) -> frozenset[str]:
    # Any spelling of owl:AnnotationProperty contains its local name; skip parsing the rest.
    return frozenset(
        iri
        for text in fragments
        if _DECLARES_ANNOTATION in text
        for iri in fragment_info(text, prefixes).declares
    )


def classify_axiom(
    turtle: str,
    prefixes: Prefixes,
    annotations: frozenset[str] = frozenset(),
    properties: frozenset[str] = frozenset(),
) -> tuple[AxiomCategory, str | None]:
    info = fragment_info(turtle, prefixes)
    unknown = info.unknown_predicates
    if info.category == "other" and unknown:
        if unknown <= annotations:
            return "annotation", info.note
        if not any(is_builtin(iri) for iri in unknown):
            return ("annotation" if unknown.isdisjoint(properties) else "individual"), info.note
    return info.category, info.note
