"""AI binding suggestions turned into a change set (spec 003, section 8).

This is the one way the ai module's binding suggestions enter the ontology: as an open change
set of source `ai_binding` whose items all wait for review. It applies, accepts and merges
nothing, and takes no semantic elements. It implements no binding rule either: the checks are
those of a manual save (`service`'s shape and reference checks, then `binding_rules`).

Several suggestions may be candidates for the same place (the same binding kind of the same
element under the same parent or ends): they are tried in order, and the first that passes the
checks is taken; the others go as `binding.duplicate`. An item that fails is left out with its
reason, then the items that refer to it, so that a few bad suggestions do not sink the rest.
`first_passing` makes the same choice without writing anything, for the ai module to settle
the tables of its types before it maps their columns.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ontology import binding_rules, rules, schemas, service
from ontology_platform.modules.ontology.models import BINDING_KINDS

SOURCE: Final = "ai_binding"
# Left out because an item it refers to (by temp_ref) was left out.
DEPENDENCY_DROPPED: Final = "binding.dependency_dropped"


class NotABindingProposalError(ValueError):
    """The caller passed something other than new bindings: a programming error."""


@dataclass(frozen=True, slots=True)
class Dropped:
    position: int  # in the items passed
    code: str  # a binding.* code, or DEPENDENCY_DROPPED
    message: str


@dataclass(frozen=True, slots=True)
class Selection:
    # Positions of the items taken, in order.
    taken: list[int]
    dropped: list[Dropped]


@dataclass(frozen=True, slots=True)
class BindingProposal:
    # None when no item passed the checks: then no change set was made.
    change_set_id: UUID | None
    proposed: int
    dropped: list[Dropped]


type _Place = tuple[str, str | None, str | None, str | None, str | None]


def _place(item: schemas.ProposedItem) -> _Place:
    fields = item.proposed
    return (item.kind, fields.subject_ref, fields.parent_ref, fields.domain_ref, fields.range_ref)


def _refers(item: schemas.ProposedItem, refs: set[str]) -> bool:
    return any(value in refs for _, value, _ in service.item_references(item.kind, item.proposed))


def _only_new_bindings(items: Sequence[schemas.ProposedItem]) -> None:
    for position, item in enumerate(items):
        if item.kind not in BINDING_KINDS or item.op != "create":
            raise NotABindingProposalError(
                f"Item {position}: only new bindings can be proposed here, not {item.op} "
                f"of {item.kind}."
            )
        if item.match is not None:
            raise NotABindingProposalError(f"Item {position}: a binding has no alignment.")


async def _select(
    db: AsyncSession, ontology_id: UUID, items: Sequence[schemas.ProposedItem], *, lock: bool
) -> Selection:
    """Which items to take: per place the first candidate that passes, among the others."""
    _only_new_bindings(items)
    await service._ontology_or_404(db, ontology_id, lock=lock)
    elements = {e.id: e for e in await service._elements(db, ontology_id, all_kinds=True)}

    dropped: dict[int, Dropped] = {}
    # Per place, the candidates not tried yet; the first of each is tried at once.
    waiting: dict[_Place, list[int]] = {}
    kept: dict[int, schemas.ProposedItem] = {}

    def drop(position: int, code: str, message: str) -> None:
        dropped[position] = Dropped(position, code, message)
        del kept[position]
        queue = waiting.get(_place(items[position]))
        if queue and code != DEPENDENCY_DROPPED:
            # The next candidate for the place takes its turn.
            following = queue.pop(0)
            kept[following] = items[following]

    # What create_change_set would reject the whole change set for.
    seen: set[str] = set()
    for position, item in enumerate(items):
        ref = item.temp_ref
        if ref is not None and (ref in seen or rules.parse_id(ref) is not None):
            dropped[position] = Dropped(
                position, binding_rules.INVALID, "the temp_ref is repeated or an element id"
            )
            continue
        if ref is not None:
            seen.add(ref)
        place = _place(item)
        if place in waiting:
            waiting[place].append(position)
        else:
            waiting[place] = []
            kept[position] = item

    def gone() -> set[str]:
        # The refs no item can still bring: a ref repeated by a dropped item may yet come with
        # a candidate waiting for its turn.
        alive = {item.temp_ref for item in kept.values()} | {
            items[p].temp_ref for queue in waiting.values() for p in queue
        }
        return {ref for p in dropped if (ref := items[p].temp_ref) is not None} - alive

    def dependents() -> list[int]:
        lost = gone()
        return [position for position, item in kept.items() if _refers(item, lost)]

    while kept:
        if found := dependents():
            for position in found:
                drop(position, DEPENDENCY_DROPPED, "it refers to a suggestion that was left out")
            continue
        created = {item.temp_ref: item.kind for item in kept.values() if item.temp_ref is not None}
        # Items under a candidate that has not had its turn wait for it.
        pending = {ref for queue in waiting.values() for p in queue if (ref := items[p].temp_ref)}
        checked = {p: item for p, item in kept.items() if not _refers(item, pending)}
        shape = {
            position: problem
            for position, item in checked.items()
            if (problem := service._proposal_problem(item, elements, created)) is not None
        }
        if shape:
            for position, problem in shape.items():
                drop(position, binding_rules.INVALID, problem)
            continue
        positions = sorted(checked)
        problems = await binding_rules.proposal_problems(
            db, elements.values(), [service._proposed(checked[p]) for p in positions]
        )
        if not problems:
            break
        # An item that refers to another failing one may fail only because of it: it waits for
        # the next round, where it goes as a dependent if that one went.
        failing: dict[int, binding_rules.Problem] = {}
        for index, problem in problems:
            failing.setdefault(positions[index], problem)
        failing_refs = {ref for p in failing if (ref := kept[p].temp_ref) is not None}
        first = {p: pr for p, pr in failing.items() if not _refers(kept[p], failing_refs)}
        first = first or failing
        # Two items binding the same thing both fail as duplicates: the later one goes, and the
        # earlier one is checked again without it.
        duplicates = [p for p, problem in first.items() if problem.code == binding_rules.DUPLICATE]
        for position in duplicates[:-1]:
            del first[position]
        for position, problem in first.items():
            drop(position, problem.code, problem.message)

    # The candidates never tried: their place is taken, or their parent was not (it was left out
    # or never tried either).
    never = [position for queue in waiting.values() for position in queue]
    waiting.clear()
    for position in never:
        dropped[position] = Dropped(
            position, binding_rules.DUPLICATE, "another suggestion for the same binding"
        )
    lost = gone()
    for position in never:
        if _refers(items[position], lost):
            dropped[position] = Dropped(
                position, DEPENDENCY_DROPPED, "it refers to a suggestion that was left out"
            )
    while found := dependents():
        for position in found:
            dropped[position] = Dropped(
                position, DEPENDENCY_DROPPED, "it refers to a suggestion that was left out"
            )
            del kept[position]
    return Selection(taken=sorted(kept), dropped=sorted(dropped.values(), key=lambda d: d.position))


async def first_passing(
    db: AsyncSession, ontology_id: UUID, items: Sequence[schemas.ProposedItem]
) -> Selection:
    """The choice `propose_bindings` would make for `items`, without writing anything."""
    return await _select(db, ontology_id, items, lock=False)


async def propose_bindings(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    items: Sequence[schemas.ProposedItem],
    created_by: UUID,
    title: str,
) -> BindingProposal:
    """Check `items` (new bindings only) and turn those taken into a change set waiting for
    review. Raises `NotABindingProposalError` for any other kind of item or op. Nothing is
    committed: the caller does."""
    selection = await _select(db, ontology_id, items, lock=True)
    if not selection.taken:
        return BindingProposal(change_set_id=None, proposed=0, dropped=selection.dropped)
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology_id,
        title=title,
        source=SOURCE,
        document_id=None,
        created_by=created_by,
        items=[items[p] for p in selection.taken],
    )
    return BindingProposal(
        change_set_id=change_set_id, proposed=len(selection.taken), dropped=selection.dropped
    )
