"""Expert mode (spec 002, section 7): the whole working version as Turtle, and single axioms.

Saving edited Turtle works like importing a file into the ontology: the differences become a
change set, here a manual one, that always goes to review. A single axiom must stay an axiom
after an export and a fresh import; content the forms can express belongs on its element.
"""

import asyncio
from collections import Counter
from collections.abc import Hashable, Sequence
from uuid import UUID

from rdflib.namespace import DCTERMS
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import axiom_rules, importing, schemas, service
from ontology_platform.modules.ontology.models import Element, Ontology
from ontology_platform.modules.ontology.rdf import reader, writer
from ontology_platform.modules.ontology.rdf.diff import Change, diff, keep_lost_lists
from ontology_platform.modules.ontology.rdf.model import AxiomState
from ontology_platform.modules.ontology.rdf.reader import RdfInputError
from ontology_platform.modules.ontology.turtle import axiom_triples, to_state

TURTLE_EDIT_TITLE = "专家模式：编辑 Turtle"


async def save_turtle(
    db: AsyncSession,
    ontology_id: UUID,
    text: str,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.ImportResult:
    """The edited Turtle compared with the working version (422 `import.parse_error` with the
    line on a syntax error, no change set). The result has no change set when nothing changed."""
    await service._ontology_or_404(db, ontology_id)
    graph = await asyncio.to_thread(importing._parse, text.encode())
    return await importing.compare_into(
        db,
        ontology_id,
        graph,
        title=TURTLE_EDIT_TITLE,
        source="manual",
        audit_action="ontology.turtle_edited",
        actor=actor,
        ip=ip,
    )


def _signature(change: Change) -> Hashable:
    if change.axiom is not None:
        return (change.op, "axiom", change.axiom.key)
    iri = change.element.iri if change.element is not None else None
    return (change.op, change.kind, iri, change.fields)


def _added(
    ontology: Ontology,
    elements: Sequence[Element],
    turtle: str | None,
) -> Counter[Hashable]:
    """The changes an export of `elements`, plus the axiom, would bring on a fresh import."""
    header = service.header_of(ontology)
    shown = [service.element_out(element, ontology.base_iri) for element in elements]
    current = to_state(header, shown, include_deleted=True)
    exported = to_state(header, shown)
    if turtle is not None:
        # As a merged axiom would be exported: the writer also declares what it mentions.
        exported.axioms.append(AxiomState(triples=axiom_triples(turtle, header.prefix_map())))
    graph = writer.build_graph(exported, version=None, created=ontology.created_at)
    result = reader.read(
        graph,
        ontology_iri=header.ontology_iri,
        absorb={DCTERMS.created: writer.created_literal(ontology.created_at)},
        known=reader.KnownHeader(ontology.name, ontology.description, strict=True),
    )
    keep_lost_lists(current, result.state)
    found = diff(current, result.state)
    signatures = Counter(_signature(change) for change in found.changes)
    signatures.update(("kind_changed", iri) for iri in found.kind_changed)
    return signatures


def _check(
    ontology: Ontology,
    elements: Sequence[Element],
    turtle: str,
) -> axiom_rules.NormalizedAxiom:
    prefixes = service.header_of(ontology).prefix_map()
    try:
        axiom = axiom_rules.normalize_axiom(turtle, prefixes)
    except RdfInputError as error:
        raise AppError(422, "axiom.invalid", error.detail) from error
    # Compared with what the export alone brings back, so that an ontology whose round trip is
    # not perfectly quiet does not block every axiom.
    baseline = _added(ontology, elements, None)
    extra = _added(ontology, elements, axiom.turtle)
    extra.subtract(baseline)
    left = +extra
    lost = -extra
    if not left and not lost:
        raise AppError(422, "axiom.invalid", "The ontology already holds this axiom.")
    new_axioms = [key for key in left if isinstance(key, tuple) and key[:2] == ("create", "axiom")]
    if lost or len(new_axioms) != 1 or left[new_axioms[0]] != 1 or len(left) != 1:
        raise AppError(
            422,
            "axiom.maps_to_element",
            "The fragment changes elements; edit them in their forms instead.",
        )
    return axiom


async def check_axiom(
    db: AsyncSession,
    ontology: Ontology,
    turtle: str,
    *,
    replacing: UUID | None = None,
) -> axiom_rules.NormalizedAxiom:
    """The axiom as it will be stored, or 422: `axiom.invalid` when the fragment does not parse,
    is not exactly one axiom or is already there; `axiom.maps_to_element` when, after an export
    and a fresh import, it would create or change elements rather than stay one axiom.

    `replacing` is the axiom an update rewrites; it is left out of the comparison.
    """
    elements = [
        element for element in await service._elements(db, ontology.id) if element.id != replacing
    ]
    return await asyncio.to_thread(_check, ontology, elements, turtle)
