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
from ontology_platform.modules.ontology.models import ChangeSetSource, Element, Kind, Ontology

# Above this many elements the model only sees those the message names and their neighbours.
CONTEXT_ELEMENTS_MAX = 400
TITLE_PREFIX = "助手："
TITLE_MESSAGE_LENGTH = 60
# How many subjects of constraints and axioms are named; the rest are only counted.
ABOUT_MAX = 40
_SUMMARY_KINDS = ("entity_type", "relation_type", "property")

type _AxiomCache = dict[tuple[str, UUID | None], str | None]


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


def _some(names: list[str]) -> str:
    if not names:
        return "-"
    rest = len(names) - ABOUT_MAX
    return ", ".join(names[:ABOUT_MAX]) + (f" and {rest} more" if rest > 0 else "")


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
        note + ("\n".join(_line(element) for element in summary) if summary else "(none)"),
        f"Constraints: {len(constraints)} (on: {_some(about('constraint'))})",
        f"Advanced axioms: {len(axioms)} (about: {_some(about('axiom'))})",
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


def _problem(
    ontology: Ontology,
    item: schemas.ProposedItem,
    elements: dict[UUID, Element],
    created_kinds: dict[str, Kind],
    names: set[str],
    iris: set[str],
) -> str | None:
    """Why the item fails the checks of a manual save, or None. Axioms are checked apart."""
    if item.kind == "constraint" and item.op != "delete":
        # Rules are too intricate to write from a sentence: the form is for them (section 10).
        return "constraints can only be deleted"
    target = elements.get(item.target_element_id) if item.target_element_id else None
    if item.op != "create":
        if target is None or target.kind != item.kind or target.status != "active":
            return "the target is not an active element of this kind"
        if item.op == "update" and not item.proposed.model_fields_set:
            return "the update changes nothing"
    elif item.proposed.iri is not None:
        return "an explicit IRI is for imports only"
    elif item.temp_ref is not None and rules.parse_id(item.temp_ref) is not None:
        return "a temp_ref must not be an element id"
    problems = rules.field_problems(
        item.kind,
        item.op,
        item.proposed,
        target_local_name=target.local_name if target else None,
        target_imported=target is not None and target.iri is not None,
    )
    if problems:
        return ", ".join(problems)
    local_name = item.proposed.local_name
    if (
        item.op == "create"
        and local_name is not None
        and (local_name in names or ontology.base_iri + local_name in iris)
    ):
        return "the name is in use"
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
    return None


async def _axiom(
    db: AsyncSession,
    ontology: Ontology,
    item: schemas.ProposedItem,
    cache: _AxiomCache,
) -> str | None:
    """The axiom's fragment as it will be stored, or None when it fails the checks."""
    turtle = item.proposed.turtle
    if turtle is None:
        return None
    key = (turtle, item.target_element_id)
    if key not in cache:
        # Each check exports and re-reads the whole ontology: the rounds of `_checked` reuse it.
        try:
            axiom = await expert.check_axiom(db, ontology, turtle, replacing=item.target_element_id)
        except AppError:
            cache[key] = None
        else:
            cache[key] = axiom.turtle
            cache[(axiom.turtle, item.target_element_id)] = axiom.turtle
    return cache[key]


async def _checked(
    db: AsyncSession,
    ontology: Ontology,
    elements: Sequence[Element],
    items: Sequence[schemas.ProposedItem],
    cache: _AxiomCache,
) -> list[schemas.ProposedItem]:
    """The items that pass, as they will be stored, dropping those whose references lead to a
    dropped item too."""
    by_id = {element.id: element for element in elements}
    taken = {element.local_name for element in elements if element.local_name}
    iris = {iri for element in elements if (iri := service.iri_of(element, ontology.base_iri))}
    kept = list(items)
    while True:
        created: dict[str, Kind] = {}
        for item in kept:
            if item.op == "create" and item.temp_ref and rules.parse_id(item.temp_ref) is None:
                created.setdefault(item.temp_ref, item.kind)
        names = set(taken)
        targets: set[UUID] = set()
        refs: set[str] = set()
        axioms: set[str] = set()
        passing: list[schemas.ProposedItem] = []
        for item in kept:
            # Only a passing operation claims its element, temp_ref or axiom: a second one on
            # the same is dropped.
            if item.target_element_id in targets or item.temp_ref in refs:
                continue
            if _problem(ontology, item, by_id, created, names, iris) is not None:
                continue
            if item.kind == "axiom" and item.op != "delete":
                turtle = await _axiom(db, ontology, item, cache)
                if turtle is None or turtle in axioms:
                    continue
                axioms.add(turtle)
                proposed = item.proposed.model_copy(update={"turtle": turtle})
                item = item.model_copy(update={"proposed": proposed})
            if item.target_element_id is not None:
                targets.add(item.target_element_id)
            if item.op == "create" and item.temp_ref is not None:
                refs.add(item.temp_ref)
            if item.op == "create" and item.proposed.local_name:
                names.add(item.proposed.local_name)
            passing.append(item)
        if len(passing) == len(kept):
            return passing
        kept = passing


def _with_cascade(
    ontology: Ontology,
    elements: Sequence[Element],
    items: Sequence[schemas.ProposedItem],
) -> list[schemas.ProposedItem]:
    """The items followed by the cascade of their deletes. Raises `CascadeConflictError` when
    an item keeps or edits what the deletes remove."""
    # Copies: the cascade rewrites the update of an element that it changes too.
    checked = editing._Checked(items=[item.model_copy() for item in items])
    for index, item in enumerate(items):
        if item.target_element_id is not None:
            checked.targets[item.target_element_id] = index
            if item.op == "delete":
                checked.deletes.append(item.target_element_id)
    if checked.deletes:
        editing._add_cascade(ontology, elements, checked)
    return checked.items


async def propose(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    message: str,
    created_by: UUID,
    items: Sequence[schemas.ProposedItem],
    source: ChangeSetSource = "ai_assistant",
    title: str | None = None,
    token_id: UUID | None = None,
) -> Proposal:
    """Check the assistant's operations and turn those that pass into a change set waiting for
    review. Nothing is committed: the caller does.

    MCP proposals (spec 003, 9.4) go through the same checks with `source="mcp"`, their own
    `title` and the access token they came through."""
    ontology = await service._ontology_or_404(db, ontology_id, lock=True)
    elements = await service._elements(db, ontology_id)
    by_id = {element.id: element for element in elements}
    revised = [
        item.model_copy(update={"target_revision": by_id[item.target_element_id].revision})
        if item.target_element_id in by_id
        else item
        for item in items
    ]
    cache: _AxiomCache = {}
    kept = list(revised)
    while True:
        kept = await _checked(db, ontology, elements, kept, cache)
        try:
            with_cascade = _with_cascade(ontology, elements, kept)
        except editing.CascadeConflictError as error:
            if not 1 <= error.seq <= len(kept):
                raise
            # Leave out the item in conflict, then check again what depended on it.
            kept = [item for seq, item in enumerate(kept, start=1) if seq != error.seq]
            continue
        break
    dropped = len(items) - len(kept)
    if not with_cascade:
        return Proposal(change_set_id=None, dropped=dropped)
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology_id,
        title=title if title is not None else _title(message),
        source=source,
        document_id=None,
        created_by=created_by,
        items=with_cascade,
        token_id=token_id,
    )
    return Proposal(change_set_id=change_set_id, dropped=dropped)
