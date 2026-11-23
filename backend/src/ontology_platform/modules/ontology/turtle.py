"""Between the API's `Element` objects and the RDF layer (`modules/ontology/rdf`).

The working version and every release are exported through `export_turtle`, whose input is a
list of API `Element` objects (a release snapshot or the current elements). `to_state` turns
such a list into an `OntologyState`; references by id become references by IRI, and axioms are
parsed from their Turtle fragments with the ontology's prefixes.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from rdflib import Graph, Literal
from rdflib.namespace import XSD

from ontology_platform.modules.ontology.rdf import writer
from ontology_platform.modules.ontology.rdf.model import (
    AxiomState,
    ElementState,
    OntologyState,
    Rule,
    Term,
    term_from_json,
    term_json,
)
from ontology_platform.modules.ontology.rdf.reader import parse_fragment
from ontology_platform.modules.ontology.rdf.vocab import SH
from ontology_platform.modules.ontology.schemas import ConstraintRule, Element, RdfValue


@dataclass(frozen=True, slots=True)
class OntologyHeader:
    """What the export needs to know about the ontology itself."""

    key: str
    name: str
    description: str | None
    base_iri: str
    iri: str | None = None
    prefixes: Mapping[str, str] = field(default_factory=dict)

    @property
    def ontology_iri(self) -> str:
        return self.iri or writer.ontology_iri_of(self.base_iri)

    def prefix_map(self) -> dict[str, str]:
        return writer.prefix_map(self.key, self.base_iri, self.prefixes)


# ---------- rules: API / stored JSON <-> RDF ----------


def _xsd_name(iri: str) -> str:
    return iri[len(str(XSD)) :] if iri.startswith(str(XSD)) else iri


def _xsd_iri(name: str) -> str:
    return name if ":" in name else str(XSD) + name


def _term(value: RdfValue | None) -> Term | None:
    return None if value is None else term_from_json(value.model_dump())


def _value(term: Term | None) -> dict[str, Any] | None:
    return None if term is None else term_json(term)


def rule_from_api(rule: ConstraintRule, iris: Mapping[UUID, str]) -> Rule | None:
    """The RDF rule, or None when its path element is not among `iris`."""
    path = iris.get(rule.path_id)
    if path is None:
        return None
    message = tuple(
        Literal(text.text, lang=text.lang) if text.lang else Literal(text.text)
        for text in rule.message
    )
    allowed = rule.allowed_values
    return Rule(
        path=path,
        min_count=rule.min_count,
        max_count=rule.max_count,
        datatype=_xsd_iri(rule.datatype) if rule.datatype else None,
        class_=iris.get(rule.class_id) if rule.class_id else None,
        node_kind=str(SH[rule.node_kind]) if rule.node_kind else None,
        in_=None if allowed is None else tuple(t for t in map(_term, allowed) if t is not None),
        in_lost=rule.allowed_values_lost,
        min_inclusive=_term(rule.min_inclusive),
        max_inclusive=_term(rule.max_inclusive),
        min_exclusive=_term(rule.min_exclusive),
        max_exclusive=_term(rule.max_exclusive),
        min_length=rule.min_length,
        max_length=rule.max_length,
        pattern=rule.pattern,
        flags=rule.flags,
        message=tuple(sorted(message, key=str)),
    )


def rule_fields(rule: Rule, refs: Mapping[str, str]) -> dict[str, Any]:
    """A change item's rule (camelCase JSON) for an RDF rule; `refs` maps IRIs to refs."""
    data: dict[str, Any] = {"pathRef": refs[rule.path]}
    if rule.class_ is not None:
        data["classRef"] = refs[rule.class_]
    for key, count in (
        ("minCount", rule.min_count),
        ("maxCount", rule.max_count),
        ("minLength", rule.min_length),
        ("maxLength", rule.max_length),
    ):
        if count is not None:
            data[key] = count
    if rule.datatype is not None:
        data["datatype"] = _xsd_name(rule.datatype)
    if rule.node_kind is not None:
        data["nodeKind"] = rule.node_kind[len(str(SH)) :]
    if rule.in_ is not None:
        data["allowedValues"] = [term_json(term) for term in rule.in_]
    if rule.in_lost:
        data["allowedValuesLost"] = True
    for key, term in (
        ("minInclusive", rule.min_inclusive),
        ("maxInclusive", rule.max_inclusive),
        ("minExclusive", rule.min_exclusive),
        ("maxExclusive", rule.max_exclusive),
    ):
        if term is not None:
            data[key] = _value(term)
    if rule.pattern is not None:
        data["pattern"] = rule.pattern
    if rule.flags is not None:
        data["flags"] = rule.flags
    if rule.message:
        data["message"] = [{"lang": m.language, "text": str(m)} for m in rule.message]
    return data


# ---------- elements <-> state ----------


def axiom_triples(turtle: str, prefixes: Mapping[str, str]) -> tuple[Any, ...]:
    return tuple(parse_fragment(turtle, prefixes))


def to_state(
    header: OntologyHeader,
    elements: Iterable[Element],
    *,
    include_deleted: bool = False,
) -> OntologyState:
    """The state of `elements` (active ones only unless `include_deleted`)."""
    chosen = [e for e in elements if include_deleted or e.status == "active"]
    iris = {e.id: e.iri for e in chosen if e.iri is not None}
    prefixes = header.prefix_map()
    state = OntologyState(
        ontology_iri=header.ontology_iri,
        name=header.name,
        description=header.description,
    )
    for element in chosen:
        if element.kind == "axiom":
            if element.status != "active" or element.turtle is None:
                continue
            state.axioms.append(
                AxiomState(
                    triples=axiom_triples(element.turtle, prefixes),
                    non_standard="non_standard" in element.flags,
                    id=str(element.id),
                ),
            )
            continue
        if element.iri is None:
            continue

        def ref(element_id: UUID | None) -> str | None:
            return iris.get(element_id) if element_id is not None else None

        rules: tuple[Rule, ...] = ()
        if element.rules:
            rules = tuple(
                rule for rule in (rule_from_api(r, iris) for r in element.rules) if rule is not None
            )
        state.elements[element.iri] = ElementState(
            kind=element.kind,
            iri=element.iri,
            label_zh=element.label_zh,
            label_en=element.label_en,
            definition_zh=element.definition_zh,
            definition_en=element.definition_en,
            synonyms=tuple((s.lang, s.text) for s in element.synonyms),
            parent=ref(element.parent_id),
            domain=ref(element.domain_id),
            range=ref(element.range_id),
            inverse=ref(element.inverse_id),
            datatype=element.datatype,
            unit=element.unit,
            required=element.required,
            multiple=element.multiple,
            auto_shape=element.auto_shape,
            rules=rules,
            active=element.status == "active",
            id=str(element.id),
        )
    return state


def build_graph(
    header: OntologyHeader,
    elements: Iterable[Element],
    *,
    version: int | None,
    created: datetime,
) -> Graph:
    """The RDF graph of the active elements. `version` is None for the working version."""
    return writer.build_graph(to_state(header, elements), version=version, created=created)


def export_turtle(
    header: OntologyHeader,
    elements: Iterable[Element],
    *,
    version: int | None,
    created: datetime,
) -> str:
    state = to_state(header, elements)
    return writer.export(state, header.prefix_map(), version=version, created=created)
