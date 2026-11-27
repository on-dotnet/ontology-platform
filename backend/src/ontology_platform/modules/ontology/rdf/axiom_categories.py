"""Read-only descriptions of retained Turtle fragments, independent of prefix spelling."""

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from rdflib import Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS

from ontology_platform.modules.ontology.rdf.reader import RdfInputError, parse_fragment
from ontology_platform.modules.ontology.rdf.vocab import SH, SH_NAMESPACE
from ontology_platform.modules.ontology.schemas import AxiomCategory

type Prefixes = tuple[tuple[str, str], ...]

_LOGIC_PREDICATES = {
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


@dataclass(frozen=True, slots=True)
class FragmentInfo:
    category: AxiomCategory
    note: str | None
    unknown_predicates: frozenset[str]
    declares: frozenset[str]


@lru_cache(maxsize=2048)
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
    elif any(
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
    return frozenset(iri for text in fragments for iri in fragment_info(text, prefixes).declares)


def classify_axiom(
    turtle: str, prefixes: Prefixes, annotations: frozenset[str] = frozenset()
) -> tuple[AxiomCategory, str | None]:
    info = fragment_info(turtle, prefixes)
    if (
        info.category == "other"
        and info.unknown_predicates
        and info.unknown_predicates <= annotations
    ):
        return "annotation", info.note
    return info.category, info.note
