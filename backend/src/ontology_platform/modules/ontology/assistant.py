"""What the AI assistant may see of an ontology, and how its proposals become a change set
(spec 002, section 10). The ai module calls these; it never reads the ontology tables.

Deterministic code checks every proposed operation the way a manual save is checked (fields,
references, names, axioms); an operation that fails is left out instead of failing the whole
request, and so is any operation that depends on it. Deletes bring their cascade along. What
remains becomes a change set with source `ai_assistant` whose items all wait for review.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import editing, expert, rules, schemas, service
from ontology_platform.modules.ontology.models import Element, Kind, Ontology

# Above this many elements the model only sees those the message names and their neighbours.
CONTEXT_ELEMENTS_MAX = 400
TITLE_PREFIX = "助手："
TITLE_MESSAGE_LENGTH = 60
_SUMMARY_KINDS = ("entity_type", "relation_type", "property")


@dataclass(frozen=True, slots=True)
class Proposal:
    change_set_id: UUID | None
    # Proposed operations left out because they failed the checks.
    dropped: int


def _names(element: Element) -> str:
    return " / ".join(
        value or "-" for value in (element.label_zh, element.label_en, element.local_name)
    )


def _line(element: Element) -> str:
    details: list[str] = []
    for key, value in (
        ("parent", element.parent_id),
        ("domain", element.domain_id),
        ("range", element.range_id),
        ("inverse", element.inverse_id),
    ):
        if value is not None:
            details.append(f"{key}={value}")
    if element.kind == "property":
        details.append(f"datatype={element.datatype or '-'}")
        if element.unit:
            details.append(f"unit={element.unit}")
    if element.kind in ("relation_type", "property"):
        details.append(f"required={'yes' if element.required else 'no'}")
        details.append(f"multiple={'yes' if element.multiple else 'no'}")
    synonyms = ", ".join(str(item.get("text", "")) for item in element.synonyms or [])
    return f"{element.id} | {element.kind} | {_names(element)} | {synonyms} | {' '.join(details)}"


def _mentioned(element: Element, message: str) -> bool:
    lowered = message.lower()
    names = [element.label_zh, element.label_en, element.local_name]
    names += [str(item.get("text", "")) for item in element.synonyms or []]
    return any(name and len(name) > 1 and name.lower() in lowered for name in names)


def _neighbours(element: Element) -> set[UUID]:
    refs = (element.parent_id, element.domain_id, element.range_id, element.inverse_id)
    return {ref for ref in refs if ref is not None}


def _selected(element: Element, base_iri: str) -> str:
    data = service.element_out(element, base_iri).model_dump(
        mode="json",
        by_alias=True,
        exclude={"ontology_id", "created_at", "updated_at", "revision", "origin", "flags"},
    )
    return json.dumps(data, ensure_ascii=False)


async def context_for(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    message: str,
    page: str,
    element_id: UUID | None,
) -> str:
    """The ontology as the model sees it: a summary line per type, relation and property;
    constraints and axioms only counted with what they are about; the selected element in
    full. Large ontologies are cut to what the message names and its direct neighbours."""
    ontology = await service._ontology_or_404(db, ontology_id)
    elements = [e for e in await service._elements(db, ontology_id) if e.status == "active"]
    by_id = {element.id: element for element in elements}
    summary = [element for element in elements if element.kind in _SUMMARY_KINDS]
    note = ""
    if len(summary) > CONTEXT_ELEMENTS_MAX:
        named = {element.id for element in summary if _mentioned(element, message)}
        around = set(named)
        for element in summary:
            if element.id in named:
                around |= _neighbours(element)
            elif _neighbours(element) & named:
                around.add(element.id)
        listed = [element for element in summary if element.id in around]
        note = (
            f"Only the {len(listed)} of {len(summary)} elements that the request names, and "
            "their direct neighbours, are listed. Do not refer to elements that are not listed.\n"
        )
        summary = listed
    summary.sort(key=service._kind_order)

    def about(kind: str) -> list[str]:
        refs = (
            e.domain_id if kind == "constraint" else e.subject_id
            for e in elements
            if e.kind == kind
        )
        return sorted({_names(by_id[ref]) for ref in refs if ref is not None and ref in by_id})

    constraints = [e for e in elements if e.kind == "constraint"]
    axioms = [e for e in elements if e.kind == "axiom"]
    prefixes = service.header_of(ontology).prefix_map()
    parts = [
        f'Ontology "{ontology.name}", base IRI {ontology.base_iri}',
        "Prefixes for axioms: " + ", ".join(f"{name}: <{iri}>" for name, iri in prefixes.items()),
        "Elements (id | kind | label_zh / label_en / local_name | synonyms | details):",
        note + "\n".join(_line(element) for element in summary) if summary else "(none)",
        f"Constraints: {len(constraints)} (on: {', '.join(about('constraint')) or '-'})",
        f"Advanced axioms: {len(axioms)} (about: {', '.join(about('axiom')) or '-'})",
        f"The user is on the {page} page.",
    ]
    selected = by_id.get(element_id) if element_id else None
    if selected is not None:
        parts.append("Selected element: " + _selected(selected, ontology.base_iri))
    return "\n".join(parts)


def _title(message: str) -> str:
    text = " ".join(message.split())
    if len(text) > TITLE_MESSAGE_LENGTH:
        text = text[:TITLE_MESSAGE_LENGTH] + "…"
    return TITLE_PREFIX + text


async def _problem(
    db: AsyncSession,
    ontology: Ontology,
    item: schemas.ProposedItem,
    elements: dict[UUID, Element],
    created_kinds: dict[str, Kind],
    names: set[str],
) -> str | None:
    target = elements.get(item.target_element_id) if item.target_element_id else None
    if item.op != "create":
        if target is None or target.kind != item.kind or target.status != "active":
            return "the target is not an active element of this kind"
    elif item.proposed.iri is not None:
        return "an explicit IRI is for imports only"
    problems = rules.field_problems(
        item.kind,
        item.op,
        item.proposed,
        target_local_name=target.local_name if target else None,
        target_imported=target is not None and target.iri is not None,
    )
    if problems:
        return ", ".join(problems)
    if item.op == "create" and item.proposed.local_name in names:
        return "the local name is in use"
    for _, value, kinds in service.item_references(item.kind, item.proposed):
        problem = service._reference_problem(
            value,
            elements,
            created_kinds,
            own_ref=item.temp_ref,
            own_id=target.id if target else None,
            require_active=True,
            kinds=kinds,
        )
        if problem:
            return problem
    if item.kind == "axiom" and item.op != "delete" and item.proposed.turtle is not None:
        try:
            await expert.check_axiom(
                db, ontology, item.proposed.turtle, replacing=item.target_element_id
            )
        except AppError as error:
            return error.code
    return None


async def _checked(
    db: AsyncSession,
    ontology: Ontology,
    elements: Sequence[Element],
    items: Sequence[schemas.ProposedItem],
) -> list[schemas.ProposedItem]:
    """The items that pass, dropping those whose references lead to a dropped item too."""
    by_id = {element.id: element for element in elements}
    taken = {element.local_name for element in elements if element.local_name}
    kept = list(items)
    while True:
        created: dict[str, Kind] = {}
        for item in kept:
            if item.op == "create" and item.temp_ref and rules.parse_id(item.temp_ref) is None:
                created.setdefault(item.temp_ref, item.kind)
        names = set(taken)
        targets: set[UUID] = set()
        passing: list[schemas.ProposedItem] = []
        for item in kept:
            # Only a passing operation claims its element: a second one on it is dropped.
            if item.target_element_id in targets:
                continue
            if await _problem(db, ontology, item, by_id, created, names) is not None:
                continue
            if item.target_element_id is not None:
                targets.add(item.target_element_id)
            if item.op == "create" and item.proposed.local_name:
                names.add(item.proposed.local_name)
            passing.append(item)
        if len(passing) == len(kept):
            return passing
        kept = passing


def _with_cascade(
    ontology: Ontology,
    elements: Sequence[Element],
    items: list[schemas.ProposedItem],
) -> tuple[list[schemas.ProposedItem], int]:
    """Drop items that keep or edit what the deletes remove, then add the cascade. Returns the
    items and how many of them are the assistant's own (the cascade comes after them)."""
    while True:
        checked = editing._Checked(items=list(items))
        for index, item in enumerate(items):
            if item.target_element_id is not None:
                checked.targets[item.target_element_id] = index
                if item.op == "delete":
                    checked.deletes.append(item.target_element_id)
        if not checked.deletes:
            return items, len(items)
        try:
            editing._add_cascade(ontology, elements, checked)
        except editing.CascadeConflictError as error:
            items = [item for index, item in enumerate(items, start=1) if index != error.seq]
            continue
        return checked.items, len(items)


async def propose(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    message: str,
    created_by: UUID,
    items: Sequence[schemas.ProposedItem],
) -> Proposal:
    """Check the assistant's operations and turn those that pass into a change set waiting for
    review. Nothing is committed: the caller does."""
    ontology = await service._ontology_or_404(db, ontology_id, lock=True)
    elements = await service._elements(db, ontology_id)
    by_id = {element.id: element for element in elements}
    revised = [
        item.model_copy(update={"target_revision": by_id[item.target_element_id].revision})
        if item.target_element_id in by_id
        else item
        for item in items
    ]
    kept, own = _with_cascade(ontology, elements, await _checked(db, ontology, elements, revised))
    dropped = len(items) - own
    if not kept:
        return Proposal(change_set_id=None, dropped=dropped)
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology_id,
        title=_title(message),
        source="ai_assistant",
        document_id=None,
        created_by=created_by,
        items=kept,
    )
    return Proposal(change_set_id=change_set_id, dropped=dropped)
