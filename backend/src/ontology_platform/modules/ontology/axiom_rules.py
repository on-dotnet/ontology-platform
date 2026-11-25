"""Axiom fragments in the form exports write them (spec 002, 3.4).

Shared by the working version (service), the merge, manual editing and expert mode; kept apart
so that none of them has to import another just for this.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ontology_platform.modules.ontology.rdf import axioms as rdf_axioms
from ontology_platform.modules.ontology.rdf import writer as rdf_writer
from ontology_platform.modules.ontology.rdf.reader import RdfInputError, parse_fragment


@dataclass(frozen=True, slots=True)
class NormalizedAxiom:
    turtle: str
    non_standard: bool
    subject: str | None
    mentions: frozenset[str]


def normalize_axiom(turtle: str, prefixes: Mapping[str, str]) -> NormalizedAxiom:
    """The axiom written the way exports write it. Raises RdfInputError when the fragment does
    not parse or is not exactly one axiom (spec 002, 3.4)."""
    triples = parse_fragment(turtle, prefixes)
    groups = rdf_axioms.group(triples)
    if len(groups) != 1:
        raise RdfInputError("axiom.invalid", "The fragment must hold exactly one axiom.")
    (axiom,) = rdf_axioms.axioms_of(groups[0])
    return NormalizedAxiom(
        turtle=rdf_writer.fragment(axiom.triples, prefixes),
        non_standard=axiom.non_standard,
        subject=axiom.subject,
        mentions=axiom.mentions,
    )


def axiom_problem(turtle: str, prefixes: Mapping[str, str]) -> str | None:
    try:
        normalize_axiom(turtle, prefixes)
    except RdfInputError as error:
        return error.detail.rstrip(".")
    return None
