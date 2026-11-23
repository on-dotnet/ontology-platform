"""Namespaces and term sets shared by the RDF reader, writer and declaration inference."""

from rdflib import Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

OP_NAMESPACE = "https://w3id.org/ontology-platform/vocab#"
SH_NAMESPACE = "http://www.w3.org/ns/shacl#"
OP = Namespace(OP_NAMESPACE)
SH = Namespace(SH_NAMESPACE)

FIXED_PREFIXES: dict[str, str] = {
    "dcterms": str(DCTERMS),
    "op": OP_NAMESPACE,
    "owl": str(OWL),
    "rdf": str(RDF),
    "rdfs": str(RDFS),
    "sh": SH_NAMESPACE,
    "skos": str(SKOS),
    "xsd": str(XSD),
}

# Appended to an object type's IRI to name the platform's generated node shape. Local names of
# platform elements never contain a hyphen, so these cannot collide with elements.
SHAPE_SUFFIX = "-shape"

# The datatypes a property can have in the platform's forms.
XSD_TYPES: dict[str, URIRef] = {
    "string": XSD.string,
    "integer": XSD.integer,
    "decimal": XSD.decimal,
    "boolean": XSD.boolean,
    "date": XSD.date,
    "dateTime": XSD.dateTime,
}
DATATYPE_OF: dict[URIRef, str] = {iri: name for name, iri in XSD_TYPES.items()}

# OWL 2 never needs a declaration for these (they are the language itself).
BUILTIN_NAMESPACES: tuple[str, ...] = (str(RDF), str(RDFS), str(OWL), str(XSD))
# IRIs here are vocabulary, never elements of a user's ontology.
RESERVED_NAMESPACES: tuple[str, ...] = (
    *BUILTIN_NAMESPACES,
    SH_NAMESPACE,
    str(SKOS),
    str(DCTERMS),
    "http://purl.org/dc/elements/1.1/",
    "http://www.w3.org/ns/prov#",
    "http://www.w3.org/2006/time#",
    "http://www.w3.org/XML/1998/namespace",
    OP_NAMESPACE,
)

DECLARATION_TYPES: frozenset[URIRef] = frozenset(
    {
        OWL.Class,
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
        OWL.AnnotationProperty,
        OWL.NamedIndividual,
        RDFS.Datatype,
    },
)
ELEMENT_TYPES: dict[URIRef, str] = {
    OWL.Class: "entity_type",
    OWL.ObjectProperty: "relation_type",
    OWL.DatatypeProperty: "property",
}

NODE_KINDS: frozenset[URIRef] = frozenset(
    SH[name]
    for name in (
        "IRI",
        "Literal",
        "BlankNode",
        "BlankNodeOrIRI",
        "BlankNodeOrLiteral",
        "IRIOrLiteral",
    )
)


def is_builtin(iri: str) -> bool:
    return iri.startswith(BUILTIN_NAMESPACES)


def is_reserved(iri: str) -> bool:
    return iri.startswith(RESERVED_NAMESPACES)
