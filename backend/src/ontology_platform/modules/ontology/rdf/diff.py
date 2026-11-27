"""What changes turn one `OntologyState` into another (spec 002, section 5).

Elements are matched by IRI, including deleted ones (which come back as a restore); axioms by
their canonical key, so blank node names and the spelling of literal values do not count.
"""

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from rdflib import BNode, URIRef
from rdflib.namespace import RDF, RDFS, SH, XSD

from ontology_platform.modules.ontology.rdf.model import AxiomState, ElementState, OntologyState

ChangeKind = Literal["create", "update", "delete", "restore"]

FIELDS: tuple[str, ...] = (
    "label_zh",
    "label_en",
    "definition_zh",
    "definition_en",
    "synonyms",
    "parent",
    "domain",
    "range",
    "inverse",
    "datatype",
    "unit",
    "required",
    "multiple",
    "auto_shape",
    "rules",
)
_TEXT_FIELDS = ("label_zh", "label_en", "definition_zh", "definition_en", "synonyms")
# The fields each kind has; the others hold defaults that mean nothing for it.
KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "entity_type": (*_TEXT_FIELDS, "parent", "auto_shape"),
    "relation_type": (
        *_TEXT_FIELDS,
        "domain",
        "range",
        "inverse",
        "required",
        "multiple",
        "auto_shape",
    ),
    "property": (
        *_TEXT_FIELDS,
        "domain",
        "datatype",
        "unit",
        "required",
        "multiple",
        "auto_shape",
    ),
    "constraint": (*_TEXT_FIELDS, "domain", "rules"),
}


@dataclass(frozen=True, slots=True)
class Change:
    op: ChangeKind
    kind: str
    # The target's version for create, update and restore; the current one for delete.
    element: ElementState | None = None
    axiom: AxiomState | None = None
    # The fields that differ (every field for a create).
    fields: frozenset[str] = frozenset()


@dataclass(slots=True)
class Diff:
    changes: list[Change] = field(default_factory=list)
    # IRIs of elements whose kind differs between the two sides; they are left alone.
    kind_changed: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.changes)


def field_value(element: ElementState, name: str) -> Any:
    if name == "synonyms":
        return frozenset(element.synonyms)
    if name == "rules":
        return tuple(sorted(repr(rule.key()) for rule in element.rules))
    return getattr(element, name)


def inverses(state: OntologyState) -> dict[str, str]:
    """Each relation's inverse, read both ways: owl:inverseOf is symmetric, and OWL API writes
    a pair that names each other with one triple only (the other direction is implied)."""
    found: dict[str, str] = {}
    for element in state.elements.values():
        if element.active and element.inverse:
            found[element.iri] = element.inverse
    for iri, partner in sorted(found.items()):
        found.setdefault(partner, iri)
    return found


def changed_fields(
    have: ElementState,
    wanted: ElementState,
    have_inverses: dict[str, str] | None = None,
    wanted_inverses: dict[str, str] | None = None,
) -> frozenset[str]:
    def value(element: ElementState, name: str, pairs: dict[str, str] | None) -> Any:
        if name == "inverse" and pairs is not None:
            return pairs.get(element.iri)
        return field_value(element, name)

    return frozenset(
        name
        for name in KIND_FIELDS[wanted.kind]
        if value(have, name, have_inverses) != value(wanted, name, wanted_inverses)
    )


def keep_lost_lists(current: OntologyState, target: OntologyState) -> int:
    """Give rules whose sh:in list Protégé dropped the values the platform already has.

    OWL API keeps `sh:in` but not the list behind it, because a list used as an annotation value
    is not OWL. Returns how many rules got their values back.
    """
    restored = 0
    for iri, wanted in target.elements.items():
        have = current.elements.get(iri)
        if wanted.kind != "constraint" or have is None or have.kind != "constraint":
            continue
        rules = list(wanted.rules)
        for index, rule in enumerate(rules):
            if not rule.in_lost:
                continue
            for old in have.rules:
                if old.path == rule.path and old.in_ is not None:
                    candidate = replace(rule, in_=old.in_, in_lost=False)
                    if candidate.key() == old.key():
                        rules[index] = candidate
                        restored += 1
                        break
        wanted.rules = tuple(rules)
    return restored


_LOST_AXIOM_LISTS = frozenset({SH["in"], SH.alternativePath})


def _empty_list_positions(axiom: AxiomState) -> bool:
    relevant = [value for _, predicate, value in axiom.triples if predicate in _LOST_AXIOM_LISTS]
    if not relevant:
        return False
    return all(
        isinstance(value, BNode)
        and not any(subject == value for subject, _, _ in axiom.triples)
        and sum(obj == value for _, _, obj in axiom.triples) == 1
        for value in relevant
    )


def _without_axiom_lists(axiom: AxiomState) -> str | None:
    """Compare a complete old RDF list as the empty node OWL API writes in its place."""
    triples = set(axiom.triples)
    references = Counter(obj for _, _, obj in triples)
    heads = [triple for triple in triples if triple[1] in _LOST_AXIOM_LISTS]
    if not heads:
        return None
    for subject, predicate, head in heads:
        cell = head
        cells: set[BNode] = set()
        while cell != RDF.nil:
            if not isinstance(cell, BNode) or cell in cells or references[cell] != 1:
                return None
            cells.add(cell)
            outgoing = [(p, o) for s, p, o in triples if s == cell]
            if len(outgoing) != 2 or {p for p, _ in outgoing} != {RDF.first, RDF.rest}:
                return None
            cell = next(obj for pred, obj in outgoing if pred == RDF.rest)
        if not cells:
            return None
        triples.difference_update({triple for triple in triples if triple[0] in cells})
        triples.remove((subject, predicate, head))
        triples.add((subject, predicate, BNode()))
    return AxiomState(tuple(triples)).key


def keep_lost_axiom_lists(current: OntologyState, target: OntologyState) -> int:
    """Keep a unique unchanged axiom when OWL API has only erased its nested SHACL lists."""
    existing = {axiom.key for axiom in current.axioms}
    restored = 0
    for index, wanted in enumerate(target.axioms):
        if wanted.key in existing or not _empty_list_positions(wanted):
            continue
        matches = [
            old
            for old in current.axioms
            if old.subject == wanted.subject and _without_axiom_lists(old) == wanted.key
        ]
        if len(matches) == 1:
            target.axioms[index] = matches[0]
            restored += 1
    return restored


def _is_xsd_datatype_declaration(axiom: AxiomState) -> bool:
    if len(axiom.triples) != 1:
        return False
    subject, predicate, value = axiom.triples[0]
    return (
        predicate == RDF.type
        and value == RDFS.Datatype
        and isinstance(subject, URIRef)
        and subject.startswith(str(XSD))
    )


def diff(current: OntologyState, target: OntologyState) -> Diff:
    result = Diff()
    pairs = (inverses(current), inverses(target))
    for iri in sorted(target.elements):
        wanted = target.elements[iri]
        if not wanted.active:
            continue
        have = current.elements.get(iri)
        if have is None:
            every = frozenset(KIND_FIELDS[wanted.kind])
            result.changes.append(Change("create", wanted.kind, wanted, fields=every))
        elif have.kind != wanted.kind:
            result.kind_changed.append(iri)
        elif not have.active:
            result.changes.append(
                Change("restore", wanted.kind, wanted, fields=changed_fields(have, wanted)),
            )
        else:
            changed = changed_fields(have, wanted, *pairs)
            if changed:
                result.changes.append(Change("update", wanted.kind, wanted, fields=changed))
    for iri in sorted(current.elements):
        have = current.elements[iri]
        wanted_element = target.elements.get(iri)
        if have.active and (wanted_element is None or not wanted_element.active):
            result.changes.append(Change("delete", have.kind, have))

    current_axioms = [a for a in current.axioms if not _is_xsd_datatype_declaration(a)]
    target_axioms = [a for a in target.axioms if not _is_xsd_datatype_declaration(a)]
    remaining = Counter(axiom.key for axiom in current_axioms)
    for axiom in target_axioms:
        if remaining[axiom.key] > 0:
            remaining[axiom.key] -= 1
        else:
            result.changes.append(Change("create", "axiom", axiom=axiom))
    wanted_keys = Counter(axiom.key for axiom in target_axioms)
    for axiom in current_axioms:
        if wanted_keys[axiom.key] > 0:
            wanted_keys[axiom.key] -= 1
        else:
            result.changes.append(Change("delete", "axiom", axiom=axiom))
    return result
