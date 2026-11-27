"""Ontologies, the working version, change sets (review and merge) and releases.

The HTTP operations commit their own transaction. The functions other modules call
(`get_ontology`, `list_alignment_elements`, `create_change_set`, `count_entity_types`,
`count_open_change_sets`, `plan_merge`) never commit: `create_change_set` only adds to the
caller's transaction, and `plan_merge` touches no database at all.

Change sets are the only way the working version changes (AGENTS.md, "AI 不直接改本体").
"""

import asyncio
import re
import secrets
import string
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.identity import service as identity
from ontology_platform.modules.ontology import (
    binding_rules,
    mergeplan,
    metric_rules,
    rules,
    schemas,
)
from ontology_platform.modules.ontology.axiom_rules import axiom_problem
from ontology_platform.modules.ontology.models import (
    BINDING_KINDS,
    ELEMENT_FLAGS,
    ITEM_FLAGS,
    KINDS,
    SEMANTIC_KINDS,
    ChangeItem,
    ChangeSet,
    ChangeSetSource,
    ChangeSetStatus,
    Decision,
    Element,
    ElementStatus,
    Evidence,
    EvidenceKind,
    Kind,
    Ontology,
    Release,
)
from ontology_platform.modules.ontology.rdf.axiom_categories import (
    Prefixes,
    classify_axiom,
    declared_annotations,
)
from ontology_platform.modules.ontology.schemas import ReviewMode
from ontology_platform.modules.ontology.turtle import OntologyHeader, export_turtle

STALE_TARGET = "changeset.stale_target"
DEPENDENCY_SKIPPED = "changeset.dependency_skipped"
INVALID_ITEM = "changeset.invalid_item"
HAS_DEPENDENTS = "changeset.has_dependents"
RESOLUTION_CHANGED = "changeset.resolution_changed"
NO_MATCH = "changeset.no_match"
# The kinds M1's AI extraction aligns its proposals with.
_ALIGNMENT_KINDS = ("entity_type", "relation_type", "property")

TITLE_MAX_LENGTH = 300
_KEY = re.compile(schemas.KEY_PATTERN)
_KEY_ALPHABET = string.ascii_lowercase + string.digits
_RANDOM_KEY_ATTEMPTS = 5


class InvalidProposalError(AppError):
    """`create_change_set` was given items that do not fit together or the ontology."""

    def __init__(self, detail: str) -> None:
        super().__init__(422, INVALID_ITEM, detail)


class InvalidBindingError(InvalidProposalError):
    """A binding item fails the binding rules (spec 003, 6.2): its own `binding.*` code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = binding_rules.STATUS[code]
        self.code = code


class ReleaseInvalidError(AppError):
    """The working version failed the publish checks; `problems` lists why."""

    def __init__(self, problems: list[schemas.ReleaseProblem]) -> None:
        super().__init__(422, "release.invalid", "The working version failed the publish checks.")
        self.problems = problems

    def body(self) -> dict[str, Any]:
        """The problem+json body, with the `problems` extension member."""
        return {
            "type": "about:blank",
            "title": HTTPStatus(self.status).phrase,
            "status": self.status,
            "detail": self.detail,
            "code": self.code,
            "problems": [
                problem.model_dump(mode="json", by_alias=True) for problem in self.problems
            ],
        }


def _now() -> datetime:
    return datetime.now(UTC)


def _kind_order(element: Element) -> tuple[int, str, str]:
    return (KINDS.index(element.kind), element.local_name or "", element.turtle or "")


def iri_of(element: Element, base_iri: str) -> str | None:
    """The element's IRI: the one it was imported with, else base + local name (none for
    axioms)."""
    if element.iri is not None:
        return element.iri
    return base_iri + element.local_name if element.local_name else None


def _ontology_not_found() -> AppError:
    return AppError(404, "ontology.not_found", "Ontology not found.")


def _change_set_not_found() -> AppError:
    # Also used for an item id that is not part of the change set.
    return AppError(404, "changeset.not_found", "Change set or item not found.")


def header_of(ontology: Ontology) -> OntologyHeader:
    return OntologyHeader(
        key=ontology.key,
        name=ontology.name,
        description=ontology.description,
        base_iri=ontology.base_iri,
        iri=ontology.ontology_iri,
        prefixes=dict(ontology.prefixes or {}),
    )


_header = header_of


async def _ontology_or_404(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    lock: bool = False,
) -> Ontology:
    statement = select(Ontology).where(Ontology.id == ontology_id)
    if lock:
        # Serializes merges, publishes and activations of one ontology. NO KEY UPDATE still lets
        # other transactions insert rows that reference the ontology (new change sets).
        statement = statement.with_for_update(key_share=True).execution_options(
            populate_existing=True
        )
    ontology = await db.scalar(statement)
    if ontology is None:
        raise _ontology_not_found()
    return ontology


async def _elements(
    db: AsyncSession, ontology_id: UUID, *, all_kinds: bool = False, include_metrics: bool = False
) -> list[Element]:
    """The ontology's elements, semantic kinds only unless `all_kinds`.

    Bindings (spec 003, 6.1) are seen only where a caller asks for them: merging, publishing,
    comparing, impact and change set checks. Export, diffing, the graph, alignment and the
    assistant's context keep the default, so they cannot pick up bindings by accident.
    """
    statement = select(Element).where(Element.ontology_id == ontology_id)
    if not all_kinds:
        kinds = (*SEMANTIC_KINDS, "metric") if include_metrics else SEMANTIC_KINDS
        statement = statement.where(Element.kind.in_(kinds))
    return sorted((await db.scalars(statement)).all(), key=_kind_order)


async def _active_elements(db: AsyncSession, ontology_id: UUID) -> list[Element]:
    return [element for element in await _elements(db, ontology_id) if element.status == "active"]


# ---------- interface for other modules ----------


async def count_mcp_change_sets(db: AsyncSession, token_id: UUID, *, since: datetime) -> int:
    """Change sets proposed through one access token since `since` (spec 003, 9.4)."""
    statement = (
        select(func.count())
        .select_from(ChangeSet)
        .where(ChangeSet.token_id == token_id, ChangeSet.created_at >= since)
    )
    return await db.scalar(statement) or 0


async def count_open_mcp_change_sets(db: AsyncSession, user_id: UUID) -> int:
    """Open change sets one user proposed over MCP (spec 003, 9.4)."""
    statement = (
        select(func.count())
        .select_from(ChangeSet)
        .where(
            ChangeSet.source == "mcp",
            ChangeSet.status == "open",
            ChangeSet.created_by == user_id,
        )
    )
    return await db.scalar(statement) or 0


# What a merge of an AI-extracted change set does with each item, as a pure function of plain
# data (spec 004, 5.2): the evaluation applies proposals with it, without a database.
plan_merge = mergeplan.plan_merge
PlanItem = mergeplan.PlanItem
PlanElement = mergeplan.PlanElement
Resolution = mergeplan.Resolution
PlanMatch = mergeplan.PlanMatch
PlanMatchedBy = mergeplan.PlanMatchedBy
RecordedItem = mergeplan.RecordedItem
link_records = mergeplan.link_records


async def ontology_exists(db: AsyncSession, ontology_id: UUID) -> bool:
    return await db.get(Ontology, ontology_id) is not None


async def list_alignment_elements(db: AsyncSession, ontology_id: UUID) -> list[schemas.ElementCopy]:
    """Active object types, relations and properties, object types first, then by local name."""
    ontology = await db.get(Ontology, ontology_id)
    if ontology is None:
        return []
    return [
        schemas.ElementCopy.model_validate(_element_data(element, ontology.base_iri))
        for element in await _active_elements(db, ontology_id)
        if element.kind in _ALIGNMENT_KINDS
    ]


@dataclass(frozen=True, slots=True)
class PendingCandidate:
    """A create item of another open change set (spec 004, 4.1), with its effective fields."""

    item_id: UUID
    change_set_id: UUID
    change_set_title: str
    kind: str
    temp_ref: str | None
    fields: schemas.ElementFields


@dataclass(frozen=True, slots=True)
class AlignmentCandidates:
    """What an extraction aligns with: `active` as `list_alignment_elements`; `deleted` object
    types, relations and properties, which a new type of the same main name restores and whose
    local names stay taken; `pending` create items of the open change sets that are not
    rejected, which an extraction judges against but never references."""

    active: list[schemas.ElementCopy]
    deleted: list[schemas.ElementCopy]
    pending: list[PendingCandidate]


async def list_alignment_candidates(db: AsyncSession, ontology_id: UUID) -> AlignmentCandidates:
    ontology = await db.get(Ontology, ontology_id)
    if ontology is None:
        return AlignmentCandidates([], [], [])
    copies = [
        schemas.ElementCopy.model_validate(_element_data(element, ontology.base_iri))
        for element in await _elements(db, ontology_id)
        if element.kind in _ALIGNMENT_KINDS
    ]
    rows = await db.execute(
        select(ChangeItem, ChangeSet)
        .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .where(
            ChangeSet.ontology_id == ontology_id,
            ChangeSet.status == "open",
            ChangeItem.op == "create",
            ChangeItem.kind.in_(_ALIGNMENT_KINDS),
            ChangeItem.decision != "rejected",
        )
        .order_by(ChangeSet.created_at, ChangeSet.id, ChangeItem.seq)
    )
    pending = [
        PendingCandidate(
            item_id=item.id,
            change_set_id=change_set.id,
            change_set_title=change_set.title,
            kind=item.kind,
            temp_ref=item.temp_ref,
            fields=rules.effective_fields(item.proposed, item.edited),
        )
        for item, change_set in rows
    ]
    return AlignmentCandidates(
        active=[copy for copy in copies if copy.status == "active"],
        deleted=[copy for copy in copies if copy.status != "active"],
        pending=pending,
    )


async def lock_ontology(db: AsyncSession, ontology_id: UUID) -> None:
    """Hold the ontology's lock for the rest of the caller's transaction.

    Merges take the same lock: an extraction that checks for late candidates and writes its
    change set under it sees every merge and change set written before it (spec 004, 7.3).
    """
    await _ontology_or_404(db, ontology_id, lock=True)


async def count_entity_types(db: AsyncSession) -> int:
    """Active object types across all ontologies."""
    statement = (
        select(func.count())
        .select_from(Element)
        .where(Element.kind == "entity_type", Element.status == "active")
    )
    return await db.scalar(statement) or 0


async def count_open_change_sets(db: AsyncSession) -> int:
    """Change sets waiting for review across all ontologies."""
    statement = select(func.count()).select_from(ChangeSet).where(ChangeSet.status == "open")
    return await db.scalar(statement) or 0


async def create_change_set(
    db: AsyncSession,
    *,
    ontology_id: UUID,
    title: str,
    source: ChangeSetSource,
    document_id: UUID | None,
    created_by: UUID | None,
    items: list[schemas.ProposedItem],
    token_id: UUID | None = None,
) -> UUID:
    """Add an open change set with `items` (in order) to the caller's transaction.

    `token_id` is the access token an MCP proposal came through (source `mcp`).

    Raises `InvalidProposalError` when a temp_ref is repeated, a reference is neither an object
    type of the ontology nor the temp_ref of an object type created in this change set, or an
    update does not target an element of the ontology; for a binding item these and the binding
    rules (including the cached catalog) raise `InvalidBindingError`, a subclass with the
    `binding.*` codes. Nothing is committed.
    """
    ontology = await db.get(Ontology, ontology_id)
    if ontology is None:
        raise _ontology_not_found()
    elements = {element.id: element for element in await _elements(db, ontology_id, all_kinds=True)}

    created_kinds: dict[str, Kind] = {}
    for position, item in enumerate(items, start=1):
        if item.op != "create" or item.temp_ref is None:
            continue
        if rules.parse_id(item.temp_ref) is not None:
            raise InvalidProposalError(f"Item {position}: a temp_ref must not be an element id.")
        if item.temp_ref in created_kinds:
            raise InvalidProposalError(f"Item {position}: the temp_ref is used twice.")
        created_kinds[item.temp_ref] = item.kind
    for position, item in enumerate(items, start=1):
        problem = _proposal_problem(item, elements, created_kinds, manual=source == "manual")
        if problem and item.kind == "metric" and source == "manual":
            raise AppError(422, metric_rules.INVALID, f"Item {position}: {problem}.")
        if problem and item.kind in BINDING_KINDS:
            # The binding error codes cover bad references too (spec 003 appendix).
            raise InvalidBindingError(binding_rules.INVALID, f"Item {position}: {problem}.")
        if problem:
            raise InvalidProposalError(f"Item {position}: {problem}.")
    await _check_matches(db, ontology_id, items, elements, created_kinds)
    if any(item.kind == "metric" and item.op != "delete" for item in items):
        proposed = [_proposed(item) for item in items]
        for index, problem in metric_rules.proposal_problems(elements, proposed):
            raise AppError(422, metric_rules.INVALID, f"Item {index + 1}: {problem}.")
    if any(item.kind in BINDING_KINDS for item in items):
        found = await binding_rules.proposal_problems(
            db, elements.values(), [_proposed(item) for item in items]
        )
        if found:
            index, broken = found[0]
            raise InvalidBindingError(broken.code, f"Item {index + 1}: {broken.message}.")

    change_set = ChangeSet(
        id=uuid4(),
        ontology_id=ontology_id,
        title=title.strip()[:TITLE_MAX_LENGTH],
        source=source,
        document_id=document_id,
        status="open",
        created_by=created_by,
        token_id=token_id,
        created_at=_now(),
    )
    db.add(change_set)
    # Explicit flushes keep parent rows ahead of child rows (there are no ORM relationships).
    await db.flush()
    audit.record(
        db,
        "changeset.created",
        # AI change sets are the platform's work, not the uploader's; an MCP proposal is the
        # token owner's, made through that token.
        actor_id=created_by if source in ("manual", "import", "mcp") else None,
        target_type="change_set",
        target_id=str(change_set.id),
        detail={"source": source, "items": len(items)}
        | ({"tokenId": str(token_id)} if token_id is not None else {}),
    )
    rows: list[tuple[ChangeItem, schemas.ProposedItem]] = []
    for seq, item in enumerate(items, start=1):
        target = elements[item.target_element_id] if item.target_element_id else None
        row = ChangeItem(
            id=uuid4(),
            change_set_id=change_set.id,
            seq=seq,
            op=item.op,
            kind=item.kind,
            target_element_id=target.id if target else None,
            target_revision=(item.target_revision or target.revision) if target else None,
            temp_ref=item.temp_ref,
            proposed=rules.stored_fields(item.proposed),
            edited=None,
            decision="pending",
            confidence=item.confidence,
            rationale=item.rationale,
            flags=list(dict.fromkeys(item.flags)),
        )
        if item.match is not None:
            row.match_kind = item.match.kind
            row.match_element_id = item.match.element_id
            row.match_item_id = item.match.item_id
            row.match_reason = rules.clean_text(item.match.reason)
        db.add(row)
        rows.append((row, item))
    await db.flush()
    # A record of an object type of this change set points at its row, now that it has one.
    ids = {row.temp_ref: row.id for row, _ in rows if row.temp_ref is not None}
    for row, item in rows:
        if item.match is not None and item.match.temp_ref is not None:
            row.match_item_id = ids[item.match.temp_ref]
    for row, item in rows:
        for evidence in item.evidence:
            db.add(
                Evidence(
                    id=uuid4(),
                    change_item_id=row.id,
                    kind=evidence.kind,
                    document_id=evidence.document_id,
                    source=(
                        evidence.source.model_dump(mode="json", by_alias=True)
                        if evidence.source is not None
                        else None
                    ),
                    chunk_id=evidence.chunk_id,
                    quote=evidence.quote,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                ),
            )
    return change_set.id


async def _check_matches(
    db: AsyncSession,
    ontology_id: UUID,
    items: Sequence[schemas.ProposedItem],
    elements: Mapping[UUID, Element],
    created_kinds: Mapping[str, Kind],
) -> None:
    """Alignment records only on new object types, pointing at exactly one object type."""
    wanted = {item.match.item_id for item in items if item.match and item.match.item_id}
    others: set[UUID] = set()
    if wanted:
        statement = (
            select(ChangeItem.id)
            .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
            .where(
                ChangeItem.id.in_(wanted),
                ChangeItem.kind == "entity_type",
                ChangeItem.op == "create",
                ChangeSet.ontology_id == ontology_id,
            )
        )
        others = set((await db.scalars(statement)).all())
    for position, item in enumerate(items, start=1):
        match = item.match
        if match is None:
            continue
        given = [match.element_id, match.item_id, match.temp_ref]
        element = elements.get(match.element_id) if match.element_id else None
        if item.op != "create" or item.kind != "entity_type":
            problem = "only a new object type has an alignment record"
        elif sum(value is not None for value in given) != 1:
            problem = "an alignment record names exactly one other side"
        elif match.element_id is not None and (element is None or element.kind != "entity_type"):
            problem = "the aligned element is not an object type of the ontology"
        elif match.item_id is not None and match.item_id not in others:
            problem = "the aligned item is not a new object type of the ontology"
        elif match.temp_ref is not None and (
            created_kinds.get(match.temp_ref) != "entity_type" or match.temp_ref == item.temp_ref
        ):
            problem = "the aligned temp_ref is not another object type of the change set"
        else:
            continue
        raise InvalidProposalError(f"Item {position}: {problem}.")


def _proposed(item: schemas.ProposedItem) -> binding_rules.Proposed:
    return binding_rules.Proposed(
        op=item.op,
        kind=item.kind,
        target_id=item.target_element_id,
        temp_ref=item.temp_ref,
        fields=item.proposed,
    )


def item_references(
    kind: str, fields: schemas.ElementFields
) -> list[tuple[str, str, tuple[str, ...]]]:
    """(name for messages, reference, kinds it may point at) for every reference given."""
    found: list[tuple[str, str, tuple[str, ...]]] = []
    for name in rules.KIND_REFS[kind]:
        value = getattr(fields, name)
        if value is not None:
            found.append((rules.wire_name(name), value, rules.ref_targets(kind, name)))
    for index, rule in enumerate(fields.rules or []):
        found.append((f"rules[{index}].pathRef", rule.path_ref, rules.RULE_PATH_KINDS))
        if rule.class_ref is not None:
            found.append((f"rules[{index}].classRef", rule.class_ref, ("entity_type",)))
    if fields.metric is not None:
        found.extend(
            ("propertyRef", ref, ("property",)) for ref in metric_rules.property_refs(fields.metric)
        )
    return found


def _proposal_problem(
    item: schemas.ProposedItem,
    elements: dict[UUID, Element],
    created_kinds: dict[str, Kind],
    *,
    manual: bool = False,
) -> str | None:
    if item.kind == "metric" and not manual:
        return "metric changes require a manual edit"
    if item.op == "create":
        if item.target_element_id is not None:
            return "a create item has no target element"
    else:
        if item.temp_ref is not None:
            return f"an {item.op} item has no temp_ref"
        target = elements.get(item.target_element_id) if item.target_element_id else None
        if target is None:
            return f"the {item.op} target is not an element of this ontology"
        if target.kind != item.kind:
            return f"the kind does not match the {item.op} target"
    unknown_flags = set(item.flags) - set(ITEM_FLAGS)
    if unknown_flags:
        return "unknown flags"
    for evidence in item.evidence:
        start, end = evidence.char_start, evidence.char_end
        if (start is None) != (end is None):
            return "evidence needs both charStart and charEnd, or neither"
        if start is not None and end is not None and end < start:
            return "evidence charEnd is before charStart"
    if item.kind in BINDING_KINDS:
        target = elements.get(item.target_element_id) if item.target_element_id else None
        shape = rules.field_problems(
            item.kind,
            item.op,
            item.proposed,
            target_binding=target.binding if target else None,
        )
        if shape:
            return ", ".join(shape)
    own_id = item.target_element_id if item.op != "create" else None
    for name, value, kinds in item_references(item.kind, item.proposed):
        problem = _reference_problem(
            value,
            elements,
            created_kinds,
            own_ref=item.temp_ref,
            own_id=own_id,
            require_active=False,
            kinds=kinds,
        )
        if problem:
            return f"{name} {problem}"
    return None


_KIND_NAMES = {
    ("entity_type",): "an object type",
    ("relation_type",): "a relation",
    ("relation_type", "property"): "a relation or property",
    ("property",): "a property",
    ("type_binding",): "a type binding",
}


def _reference_problem(
    value: str,
    elements: dict[UUID, Element],
    created_kinds: Mapping[str, str],
    *,
    own_ref: str | None,
    own_id: UUID | None,
    require_active: bool,
    kinds: tuple[str, ...] = ("entity_type",),
) -> str | None:
    """Why a reference cannot point at an element of `kinds`, or None if it can."""
    element_id = rules.parse_id(value)
    kind_name = _KIND_NAMES.get(kinds, "an element of the right kind")
    if element_id is not None:
        element = elements.get(element_id)
        if element is None:
            return "refers to an element that is not in this ontology"
        if element.kind not in kinds:
            return f"must refer to {kind_name}"
        if require_active and element.status != "active":
            return "refers to an element that is not active"
        if element_id == own_id:
            return "refers to the element itself"
        return None
    kind = created_kinds.get(value)
    if kind is None:
        return "refers to a temp_ref that is not in this change set"
    if kind not in kinds:
        return f"must refer to {kind_name}"
    if value == own_ref:
        return "refers to the item itself"
    return None


# ---------- ontologies ----------


def _slug(name: str) -> str | None:
    if not name.isascii():
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if slug[:1].isdigit():
        slug = f"ontology-{slug}"
    slug = slug[:63].rstrip("-")
    return slug if _KEY.fullmatch(slug) else None


def _random_key() -> str:
    return "ontology-" + "".join(secrets.choice(_KEY_ALPHABET) for _ in range(6))


def default_base_iri(key: str) -> str:
    return f"https://example.org/ontology/{key}#"


async def _key_taken(db: AsyncSession, key: str) -> bool:
    return await db.scalar(select(Ontology.id).where(Ontology.key == key)) is not None


async def _choose_key(db: AsyncSession, body: schemas.OntologyCreate) -> str:
    key = body.key or _slug(body.name)
    if key is not None:
        if await _key_taken(db, key):
            raise AppError(409, "ontology.key_taken", "The ontology key is already in use.")
        return key
    for _ in range(_RANDOM_KEY_ATTEMPTS):
        key = _random_key()
        if not await _key_taken(db, key):
            return key
    raise AppError(409, "ontology.key_taken", "Could not find a free ontology key.")


async def create_ontology(
    db: AsyncSession,
    body: schemas.OntologyCreate,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.OntologySummary:
    key = await _choose_key(db, body)
    now = _now()
    ontology = Ontology(
        id=uuid4(),
        key=key,
        name=body.name,
        description=rules.clean_text(body.description),
        base_iri=default_base_iri(key),
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    db.add(ontology)
    try:
        await db.flush()
    except IntegrityError as exc:
        # A concurrent request took the key between the check and the insert.
        await db.rollback()
        raise AppError(409, "ontology.key_taken", "The ontology key is already in use.") from exc
    audit.record(
        db,
        "ontology.created",
        actor_id=actor,
        target_type="ontology",
        target_id=str(ontology.id),
        detail={"key": key, "name": ontology.name},
        ip=ip,
    )
    await db.commit()
    return (await _summaries(db, [ontology]))[0]


async def list_ontologies(db: AsyncSession) -> list[schemas.OntologySummary]:
    ontologies = (await db.scalars(select(Ontology).order_by(Ontology.created_at))).all()
    return await _summaries(db, ontologies)


async def get_ontology_summary(db: AsyncSession, ontology_id: UUID) -> schemas.OntologySummary:
    return (await _summaries(db, [await _ontology_or_404(db, ontology_id)]))[0]


async def _summaries(
    db: AsyncSession,
    ontologies: Sequence[Ontology],
) -> list[schemas.OntologySummary]:
    ids = [ontology.id for ontology in ontologies]
    if not ids:
        return []
    element_counts: dict[UUID, Counter[str]] = defaultdict(Counter)
    element_rows = await db.execute(
        select(Element.ontology_id, Element.kind, func.count())
        .where(Element.ontology_id.in_(ids), Element.status == "active")
        .group_by(Element.ontology_id, Element.kind),
    )
    for ontology_id, kind, count in element_rows:
        element_counts[ontology_id][kind] = count
    open_rows = await db.execute(
        select(ChangeSet.ontology_id, func.count())
        .where(ChangeSet.ontology_id.in_(ids), ChangeSet.status == "open")
        .group_by(ChangeSet.ontology_id),
    )
    open_counts: dict[UUID, int] = {}
    for ontology_id, count in open_rows:
        open_counts[ontology_id] = count
    release_ids = [ontology.active_release_id for ontology in ontologies]
    active_ids = [release_id for release_id in release_ids if release_id is not None]
    versions: dict[UUID, int] = {}
    if active_ids:
        version_rows = await db.execute(
            select(Release.id, Release.version).where(Release.id.in_(active_ids)),
        )
        for release_id, version in version_rows:
            versions[release_id] = version
    summaries: list[schemas.OntologySummary] = []
    for ontology in ontologies:
        counts = element_counts[ontology.id]
        active_id = ontology.active_release_id
        summaries.append(
            schemas.OntologySummary(
                id=ontology.id,
                key=ontology.key,
                name=ontology.name,
                description=ontology.description,
                base_iri=ontology.base_iri,
                ontology_iri=header_of(ontology).ontology_iri,
                entity_type_count=counts["entity_type"],
                relation_type_count=counts["relation_type"],
                property_count=counts["property"],
                constraint_count=counts["constraint"],
                axiom_count=counts["axiom"],
                open_change_set_count=open_counts.get(ontology.id, 0),
                active_release_id=active_id,
                active_release_version=versions.get(active_id) if active_id else None,
                created_at=ontology.created_at,
                updated_at=ontology.updated_at,
            ),
        )
    return summaries


# ---------- working version ----------


def _element_data(element: Element, base_iri: str) -> dict[str, Any]:
    return {
        "id": element.id,
        "ontology_id": element.ontology_id,
        "kind": element.kind,
        "local_name": element.local_name,
        "iri": iri_of(element, base_iri),
        "explicit_iri": element.iri is not None,
        "label_zh": element.label_zh,
        "label_en": element.label_en,
        "definition_zh": element.definition_zh,
        "definition_en": element.definition_en,
        "synonyms": element.synonyms,
        "parent_id": element.parent_id,
        "domain_id": element.domain_id,
        "range_id": element.range_id,
        "inverse_id": element.inverse_id,
        "datatype": element.datatype,
        "unit": element.unit,
        "required": element.required,
        "multiple": element.multiple,
        "auto_shape": element.auto_shape,
        "rules": element.rules,
        "turtle": element.turtle,
        "subject_id": element.subject_id,
        "flags": [flag for flag in element.flags if flag in ELEMENT_FLAGS],
        "binding": element.binding,
        "metric": element.metric,
        "status": element.status,
        "origin": element.origin,
        "revision": element.revision,
        "created_at": element.created_at,
        "updated_at": element.updated_at,
    }


def element_out(element: Element, base_iri: str) -> schemas.Element:
    return schemas.SnapshotElement.model_validate(_element_data(element, base_iri))


async def _axiom_vocabulary(
    db: AsyncSession, ontology: Ontology, items: Sequence[ChangeItem] = ()
) -> tuple[Prefixes, frozenset[str], frozenset[str]]:
    prefixes = tuple(sorted(header_of(ontology).prefix_map().items()))
    stored = await db.scalars(
        select(Element.turtle).where(
            Element.ontology_id == ontology.id,
            Element.kind == "axiom",
            Element.status == "active",
            # Only declarations matter here; reading every fragment is slow on large ontologies.
            Element.turtle.contains("AnnotationProperty", autoescape=True),
        )
    )
    annotations = declared_annotations((text for text in stored if text), prefixes)
    stored_properties = await db.scalars(
        select(func.coalesce(Element.iri, ontology.base_iri + Element.local_name)).where(
            Element.ontology_id == ontology.id,
            Element.kind.in_(("property", "relation_type")),
            Element.status == "active",
        )
    )
    properties = {iri for iri in stored_properties if iri is not None}
    proposals: list[str] = []
    for item in items:
        if item.kind == "axiom":
            turtle = (item.edited or {}).get("turtle", item.proposed.get("turtle"))
            if isinstance(turtle, str):
                proposals.append(turtle)
        elif item.op == "create" and item.kind in ("property", "relation_type"):
            fields = item.proposed | (item.edited or {})
            if isinstance(iri := fields.get("iri"), str):
                properties.add(iri)
            elif isinstance(local_name := fields.get("localName"), str) and local_name:
                properties.add(ontology.base_iri + local_name)
    return prefixes, annotations | declared_annotations(proposals, prefixes), frozenset(properties)


def _axiom_fields(
    kind: str,
    turtle: str | None,
    prefixes: Prefixes,
    annotations: frozenset[str],
    properties: frozenset[str],
) -> dict[str, str | None]:
    category, note = (
        classify_axiom(turtle, prefixes, annotations, properties)
        if kind == "axiom" and turtle
        else (None, None)
    )
    return {"axiom_category": category, "axiom_note": note}


def _matches(element: Element, needle: str) -> bool:
    texts = [
        element.local_name or "",
        element.label_zh or "",
        element.label_en or "",
        element.iri or "",
        element.turtle or "",
    ]
    texts.extend(str(synonym.get("text", "")) for synonym in element.synonyms)
    return any(needle in text.casefold() for text in texts)


async def list_elements(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    kind: Kind | None,
    q: str | None,
    status: ElementStatus | Literal["all"] = "active",
) -> list[schemas.Element]:
    """Elements of one status (active by default), optionally of one kind and matching `q` in
    names, labels, synonyms, the IRI or an axiom's text."""
    ontology = await _ontology_or_404(db, ontology_id)
    elements = await _elements(
        db, ontology_id, all_kinds=kind in BINDING_KINDS, include_metrics=kind in (None, "metric")
    )
    if status != "all":
        elements = [element for element in elements if element.status == status]
    if kind is not None:
        elements = [element for element in elements if element.kind == kind]
    needle = (q or "").strip().casefold()
    if needle:
        elements = [element for element in elements if _matches(element, needle)]
    vocabulary = (
        await _axiom_vocabulary(db, ontology)
        if any(element.kind == "axiom" for element in elements)
        else ((), frozenset(), frozenset())
    )
    return [
        schemas.Element.model_validate(
            {
                **_element_data(element, ontology.base_iri),
                **_axiom_fields(element.kind, element.turtle, *vocabulary),
            }
        )
        for element in elements
    ]


async def get_element(
    db: AsyncSession,
    ontology_id: UUID,
    element_id: UUID,
) -> schemas.ElementDetail:
    """The element and the merged change items (with evidence) that created or changed it."""
    ontology = await _ontology_or_404(db, ontology_id)
    element = await db.scalar(
        select(Element).where(Element.id == element_id, Element.ontology_id == ontology_id),
    )
    if element is None:
        raise AppError(404, "element.not_found", "Element not found.")
    rows = await db.execute(
        select(ChangeItem, ChangeSet)
        .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .where(ChangeItem.applied_element_id == element.id, ChangeSet.status == "merged")
        .order_by(ChangeSet.merged_at, ChangeItem.seq),
    )
    sources = rows.all()
    evidence = await _evidence_by_item(db, [item.id for item, _ in sources])
    provenance = [
        {
            "change_set_id": change_set.id,
            "change_set_title": change_set.title,
            "item_id": item.id,
            "op": item.op,
            "merged_at": change_set.merged_at,
            "evidence": evidence.get(item.id, []),
        }
        for item, change_set in sources
    ]
    data = _element_data(element, ontology.base_iri)
    if element.kind == "axiom":
        vocabulary = await _axiom_vocabulary(db, ontology)
        data.update(_axiom_fields(element.kind, element.turtle, *vocabulary))
    return schemas.ElementDetail.model_validate({**data, "provenance": provenance})


async def get_graph(db: AsyncSession, ontology_id: UUID) -> schemas.Graph:
    """Active object types as nodes; relations and parent links between them as edges."""
    await _ontology_or_404(db, ontology_id)
    elements = await _active_elements(db, ontology_id)
    types = {element.id: element for element in elements if element.kind == "entity_type"}
    property_counts = Counter(
        element.domain_id
        for element in elements
        if element.kind == "property" and element.domain_id in types
    )
    nodes = [
        schemas.GraphNode(
            id=element.id,
            label=rules.display_label(element.label_zh, element.label_en, element.local_name),
            local_name=element.local_name,
            parent_id=element.parent_id if element.parent_id in types else None,
            property_count=property_counts[element.id],
        )
        for element in types.values()
    ]
    edges: list[schemas.GraphEdge] = []
    for element in elements:
        if element.kind != "relation_type":
            continue
        source, target = element.domain_id, element.range_id
        if source is not None and target is not None and source in types and target in types:
            edges.append(
                schemas.GraphEdge(
                    id=str(element.id),
                    source=source,
                    target=target,
                    kind="relation",
                    label=rules.display_label(
                        element.label_zh,
                        element.label_en,
                        element.local_name,
                    ),
                ),
            )
    for element in types.values():
        if element.parent_id is not None and element.parent_id in types:
            edges.append(
                schemas.GraphEdge(
                    id=f"subclass:{element.id}",
                    source=element.id,
                    target=element.parent_id,
                    kind="subclass",
                    label=None,
                ),
            )
    return schemas.Graph(nodes=nodes, edges=edges)


async def export_working_version(db: AsyncSession, ontology_id: UUID) -> tuple[str, str]:
    """Turtle of the active elements, and a file name for it."""
    ontology = await _ontology_or_404(db, ontology_id)
    elements = [
        element_out(element, ontology.base_iri)
        for element in await _active_elements(db, ontology_id)
    ]
    # Parsing axioms and writing Turtle is CPU work; keep it off the event loop.
    turtle = await asyncio.to_thread(
        export_turtle,
        _header(ontology),
        elements,
        version=None,
        created=ontology.created_at,
    )
    return turtle, f"{ontology.key}.ttl"


# ---------- change sets: reading ----------


async def _change_set_or_404(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    lock: bool = False,
) -> ChangeSet:
    statement = select(ChangeSet).where(ChangeSet.id == change_set_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    change_set = await db.scalar(statement)
    if change_set is None:
        raise _change_set_not_found()
    return change_set


def _ensure_not_own(change_set: ChangeSet, actor: UUID, review_mode: ReviewMode) -> None:
    """In separate review mode nobody decides or merges a change set they created (spec 002,
    section 8); AI change sets belong to whoever uploaded the document or asked."""
    if review_mode == "separate" and change_set.created_by == actor:
        raise AppError(
            403,
            "changeset.self_review",
            "In separate review mode another reviewer must decide this change set.",
        )


def _ensure_open(change_set: ChangeSet) -> None:
    if change_set.status != "open":
        raise AppError(409, "changeset.closed", "The change set is already merged or rejected.")


async def _evidence_by_item(
    db: AsyncSession,
    item_ids: Sequence[UUID],
) -> dict[UUID, list[schemas.Evidence]]:
    if not item_ids:
        return {}
    rows = await db.scalars(
        select(Evidence)
        .where(Evidence.change_item_id.in_(item_ids))
        .order_by(
            Evidence.document_id,
            Evidence.chunk_id,
            Evidence.char_start.nulls_last(),
            Evidence.quote,
            Evidence.id,
        ),
    )
    grouped: dict[UUID, list[schemas.Evidence]] = defaultdict(list)
    for evidence in rows:
        grouped[evidence.change_item_id].append(
            schemas.Evidence(
                id=evidence.id,
                kind=cast(EvidenceKind, evidence.kind),
                document_id=evidence.document_id,
                source=(
                    schemas.CatalogEvidenceSource.model_validate(evidence.source)
                    if evidence.source is not None
                    else None
                ),
                chunk_id=evidence.chunk_id,
                quote=evidence.quote,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
            ),
        )
    return grouped


def _ref(element_id: UUID | None) -> str | None:
    return str(element_id) if element_id else None


def stored_rule_fields(rule: dict[str, Any]) -> dict[str, Any]:
    """A stored rule (ids) as change item fields (references)."""
    data = {key: value for key, value in rule.items() if key not in ("pathId", "classId")}
    data["pathRef"] = rule["pathId"]
    if rule.get("classId"):
        data["classRef"] = rule["classId"]
    return data


def _before(element: Element) -> schemas.ElementFields:
    """The element's current values as item fields, with only the keys its kind uses."""
    if element.kind == "axiom":
        return schemas.ElementFields.model_validate({"turtle": element.turtle})
    if element.kind in BINDING_KINDS:
        references = {
            "subject_ref": _ref(element.subject_id),
            "parent_ref": _ref(element.parent_id),
            "domain_ref": _ref(element.domain_id),
            "range_ref": _ref(element.range_id),
        }
        values = {name: references[name] for name in rules.KIND_REFS[element.kind]}
        return schemas.ElementFields.model_validate({**values, "binding": element.binding})
    data: dict[str, Any] = {
        "local_name": element.local_name,
        "label_zh": element.label_zh,
        "label_en": element.label_en,
        "definition_zh": element.definition_zh,
        "definition_en": element.definition_en,
        "synonyms": element.synonyms,
    }
    if element.kind == "entity_type":
        data["parent_ref"] = _ref(element.parent_id)
        data["auto_shape"] = element.auto_shape
    elif element.kind == "constraint":
        data["domain_ref"] = _ref(element.domain_id)
        data["rules"] = [stored_rule_fields(rule) for rule in element.rules or []]
    elif element.kind == "metric":
        data["subject_ref"] = _ref(element.subject_id)
        data["unit"] = element.unit
        data["metric"] = metric_rules.as_fields(element.metric or {})
    else:
        data["domain_ref"] = _ref(element.domain_id)
        if element.kind == "relation_type":
            data["range_ref"] = _ref(element.range_id)
            data["inverse_ref"] = _ref(element.inverse_id)
        else:
            data["datatype"] = element.datatype
            data["unit"] = element.unit
        data["required"] = element.required
        data["multiple"] = element.multiple
        data["auto_shape"] = element.auto_shape
    return schemas.ElementFields.model_validate(data)


def _plan_elements(elements: Sequence[Element], base_iri: str) -> list[mergeplan.PlanElement]:
    return [
        mergeplan.PlanElement(
            id=element.id,
            kind=element.kind,
            status=element.status,
            local_name=element.local_name,
            iri=iri_of(element, base_iri),
            label_zh=element.label_zh,
            label_en=element.label_en,
            definition_zh=element.definition_zh,
            definition_en=element.definition_en,
            parent_id=element.parent_id,
            domain_id=element.domain_id,
            range_id=element.range_id,
            datatype=element.datatype,
            unit=element.unit,
            required=element.required,
            multiple=element.multiple,
            revision=element.revision,
            created_at=element.created_at,
        )
        for element in elements
    ]


def _plan_items(items: Sequence[ChangeItem], links: "_Links") -> list[mergeplan.PlanItem]:
    return [
        mergeplan.PlanItem(
            id=item.id,
            seq=item.seq,
            op=item.op,
            kind=item.kind,
            decision=item.decision,
            temp_ref=item.temp_ref,
            target_element_id=item.target_element_id,
            target_revision=item.target_revision,
            fields=rules.effective_fields(item.proposed, item.edited),
            edited=item.edited is not None,
            match=links.matches.get(item.id),
            match_decision=item.match_decision,
            matched_by=links.matched_by.get(item.id, ()),
        )
        for item in items
    ]


@dataclass(frozen=True, slots=True)
class _Links:
    """The alignment records around a change set's items (spec 004, 5.3 and 5.5).

    `others` are the items the records point at, with their change sets; `reverse` the items
    of other change sets whose records point at an item here.
    """

    others: Mapping[UUID, tuple[ChangeItem, ChangeSet]]
    reverse: Mapping[UUID, Sequence[tuple[ChangeItem, ChangeSet]]]
    matches: Mapping[UUID, mergeplan.PlanMatch]
    matched_by: Mapping[UUID, tuple[mergeplan.PlanMatchedBy, ...]]


_NO_LINKS = _Links({}, {}, {}, {})


def _counts_for(other: ChangeItem, item: ChangeItem) -> bool:
    """Whether the other item's reviewer decided about this pair: about its own record of this
    item, or (without a record of its own) about the record shown from this side."""
    return other.match_item_id == item.id or other.match_kind is None


def _merged_into(other: ChangeItem, change_set: ChangeSet) -> UUID | None:
    if change_set.status != "merged" or other.decision != "accepted":
        return None
    return other.applied_element_id


async def _links(db: AsyncSession, change_set: ChangeSet, items: Sequence[ChangeItem]) -> _Links:
    # A metric cannot be either side of an alignment record.
    items = [item for item in items if item.kind != "metric"]
    ids = [item.id for item in items]
    wanted = {item.match_item_id for item in items if item.match_item_id}
    others: dict[UUID, tuple[ChangeItem, ChangeSet]] = {}
    joined = (
        select(ChangeItem, ChangeSet)
        .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .where(ChangeItem.kind != "metric")
    )
    if wanted:
        rows = await db.execute(joined.where(ChangeItem.id.in_(wanted)))
        others = {item.id: (item, owner) for item, owner in rows}
    reverse: dict[UUID, list[tuple[ChangeItem, ChangeSet]]] = defaultdict(list)
    if ids:
        rows = await db.execute(
            joined.where(
                ChangeItem.match_item_id.in_(ids), ChangeItem.change_set_id != change_set.id
            ).order_by(ChangeSet.merged_at, ChangeItem.seq)
        )
        for other, owner in rows:
            if other.match_item_id is not None:
                reverse[other.match_item_id].append((other, owner))
    # The same resolution of records as the evaluation's (spec 004, 5.2): one pure function.
    matches, matched_by = mergeplan.link_records(
        [_recorded(item, change_set) for item in items],
        {item_id: _recorded(other, owner) for item_id, (other, owner) in others.items()},
        [_recorded(other, owner) for entries in reverse.values() for other, owner in entries],
    )
    return _Links(others, reverse, matches, matched_by)


def _recorded(item: ChangeItem, change_set: ChangeSet) -> mergeplan.RecordedItem:
    fields = rules.effective_fields(item.proposed, item.edited)
    return mergeplan.RecordedItem(
        id=item.id,
        change_set_id=change_set.id,
        match_kind=item.match_kind,
        match_element_id=item.match_element_id,
        match_item_id=item.match_item_id,
        match_decision=item.match_decision,
        label_zh=fields.label_zh,
        label_en=fields.label_en,
        merged_into=_merged_into(item, change_set),
        merged_at=change_set.merged_at,
    )


@dataclass(frozen=True, slots=True)
class _Plan:
    """The merge plan of a change set against the working version, and its token."""

    resolutions: Mapping[UUID, mergeplan.Resolution]
    token: str
    # Whether merging needs the token: the plan does what merges did not do before.
    needs_token: bool


_NO_PLAN = _Plan({}, mergeplan.plan_token([], [], {}), needs_token=False)


def _plan(
    change_set: ChangeSet,
    ontology: Ontology,
    elements: Sequence[Element],
    items: Sequence[ChangeItem],
    links: _Links = _NO_LINKS,
) -> _Plan:
    """Only what the extraction proposes is planned; other sources say exactly what they do."""
    if change_set.source != "ai_extraction":
        return _NO_PLAN
    # Historical extraction metrics cannot be applied or aligned. Manual metrics use no AI plan.
    plan_items = _plan_items([item for item in items if item.kind != "metric"], links)
    plan_elements = _plan_elements(elements, ontology.base_iri)
    resolutions = mergeplan.plan_merge(plan_items, plan_elements, base_iri=ontology.base_iri)
    return _Plan(
        resolutions,
        mergeplan.plan_token(plan_items, plan_elements, resolutions),
        mergeplan.changes_the_merge(plan_items, resolutions),
    )


def _resolution_out(
    mode: str,
    element: Element | None = None,
    local_name: str | None = None,
    kept_fields: Sequence[str] = (),
    label: str | None = None,
) -> schemas.ItemResolution:
    if element is not None:
        label = rules.display_label(element.label_zh, element.label_en, element.local_name)
    return schemas.ItemResolution.model_validate(
        {
            "mode": mode,
            "element_id": element.id if element is not None else None,
            "element_label": label,
            "local_name": local_name,
            "kept_fields": list(kept_fields),
        }
    )


def _applied_resolutions(
    change_set: ChangeSet,
    items: Sequence[ChangeItem],
    elements: Mapping[UUID, Element],
) -> dict[UUID, schemas.ItemResolution]:
    """What a merge did with the items it created elements for, read back from the result.

    An item went into an element it did not create: one older than the merge, or one that an
    earlier item of the change set created. Otherwise a local name other than the proposed
    one means it was renamed. Which fields an element kept is not recorded.
    """
    out: dict[UUID, schemas.ItemResolution] = {}
    if change_set.merged_at is None:
        return out
    made_here: set[UUID] = set()
    for item in sorted(items, key=lambda item: item.seq):
        if item.op != "create" or item.kind not in mergeplan.PLANNED_KINDS:
            continue
        element = elements.get(item.applied_element_id) if item.applied_element_id else None
        if element is None:
            continue
        wanted = rules.effective_fields(item.proposed, item.edited).local_name
        # Elements a merge creates carry the merge's own timestamp, so older means strictly.
        if element.created_at < change_set.merged_at or element.id in made_here:
            out[item.id] = _resolution_out("into", element)
        elif element.local_name != wanted:
            out[item.id] = _resolution_out("rename", local_name=element.local_name)
        else:
            out[item.id] = _resolution_out("create")
        made_here.add(element.id)
    return out


def _item_label(item: ChangeItem) -> str:
    fields = rules.effective_fields(item.proposed, item.edited)
    return rules.display_label(fields.label_zh, fields.label_en, fields.local_name)


async def _resolutions(
    db: AsyncSession,
    change_set: ChangeSet,
    items: Sequence[ChangeItem],
) -> tuple[dict[UUID, schemas.ItemResolution], str, _Links]:
    """The resolution of each item for the API, the token of the plan (spec 004, 5.4), and the
    alignment records around the items."""
    if change_set.source != "ai_extraction" or change_set.status == "rejected":
        return {}, _NO_PLAN.token, await _links(db, change_set, items)
    ontology = await _ontology_or_404(db, change_set.ontology_id)
    elements = await _elements(db, ontology.id, all_kinds=True)
    by_id = {element.id: element for element in elements}
    links = await _links(db, change_set, items)
    if change_set.status == "merged":
        return _applied_resolutions(change_set, items, by_id), _NO_PLAN.token, links
    plan = _plan(change_set, ontology, elements, items, links)
    by_item = {item.id: item for item in items}
    out: dict[UUID, schemas.ItemResolution] = {}
    for item_id, resolution in plan.resolutions.items():
        element = by_id.get(resolution.element_id) if resolution.element_id else None
        joined = by_item.get(resolution.item_id) if resolution.item_id else None
        out[item_id] = _resolution_out(
            resolution.mode,
            element,
            resolution.local_name,
            resolution.kept_fields,
            label=_item_label(joined) if joined is not None else None,
        )
    return out, plan.token, links


async def _matches_out(
    db: AsyncSession, items: Sequence[ChangeItem], links: _Links
) -> dict[UUID, schemas.ItemMatch]:
    """Each item's own alignment record, or one made from a merged item that recorded it."""
    element_ids = {item.match_element_id for item in items if item.match_element_id}
    element_ids |= {
        other.applied_element_id
        for entries in links.reverse.values()
        for other, _ in entries
        if other.applied_element_id
    }
    elements: dict[UUID, Element] = {}
    if element_ids:
        rows = await db.scalars(select(Element).where(Element.id.in_(element_ids)))
        elements = {element.id: element for element in rows}

    def element_label(element_id: UUID | None) -> str | None:
        element = elements.get(element_id) if element_id else None
        if element is None:
            return None
        return rules.display_label(element.label_zh, element.label_en, element.local_name)

    out: dict[UUID, schemas.ItemMatch] = {}
    for item in items:
        data: dict[str, Any] | None = None
        if item.match_kind is not None:
            found = links.others.get(item.match_item_id) if item.match_item_id else None
            other, owner = found if found is not None else (None, None)
            label = element_label(item.match_element_id)
            if other is not None:
                label = _item_label(other)
            if label is None:
                continue  # the other side is gone (a deleted change set)
            if (
                other is not None
                and owner is not None
                and owner.id != item.change_set_id
                and (other.decision == "rejected" or owner.status == "rejected")
            ):
                continue  # the plan does not follow a rejected item either
            data = {
                "kind": item.match_kind,
                "element_id": item.match_element_id,
                "item_id": other.id if other is not None else None,
                "change_set_id": owner.id if owner is not None else None,
                "change_set_title": owner.title if owner is not None else None,
                "label": label,
                "reason": item.match_reason,
                "kept_apart": other is not None
                and _counts_for(other, item)
                and other.match_decision == "different",
            }
        else:
            merged = [
                (other, owner)
                for other, owner in links.reverse.get(item.id, ())
                if _merged_into(other, owner) is not None and other.match_kind is not None
            ]
            if merged:
                other, owner = merged[0]
                data = {
                    "kind": other.match_kind,
                    "element_id": other.applied_element_id,
                    "item_id": other.id,
                    "change_set_id": owner.id,
                    "change_set_title": owner.title,
                    "label": element_label(other.applied_element_id) or _item_label(other),
                    "reason": other.match_reason,
                    "kept_apart": other.match_decision == "different",
                }
        if data is not None:
            data["decision"] = item.match_decision
            out[item.id] = schemas.ItemMatch.model_validate(data)
    return out


def _review_fields(kind: str, raw: object) -> schemas.ElementFields:
    if kind != "metric":
        return schemas.ElementFields.model_validate(raw)
    try:
        return schemas.ElementFields.model_validate(raw)
    except AppError as exc:
        if exc.code != metric_rules.INVALID:
            raise
    except ValidationError:
        return schemas.ElementFields(metric=None)
    # Preserve the reviewer's access to other items and their resolution token in a legacy set.
    # An explicit null denotes the unreadable definition in this view only.
    if isinstance(raw, dict):
        try:
            return schemas.ElementFields.model_validate({**raw, "metric": None})
        except ValidationError:
            pass
    return schemas.ElementFields(metric=None)


async def _items_out(
    db: AsyncSession,
    change_set: ChangeSet,
    items: Sequence[ChangeItem],
    resolutions: Mapping[UUID, schemas.ItemResolution],
    links: _Links,
    *,
    all_items: Sequence[ChangeItem] | None = None,
) -> list[schemas.ChangeItem]:
    evidence = await _evidence_by_item(db, [item.id for item in items])
    matches = await _matches_out(db, items, links)
    target_ids = {item.target_element_id for item in items if item.target_element_id}
    targets: dict[UUID, Element] = {}
    if target_ids:
        found = await db.scalars(select(Element).where(Element.id.in_(target_ids)))
        targets = {element.id: element for element in found}
    out: list[schemas.ChangeItem] = []
    vocabulary: tuple[Prefixes, frozenset[str], frozenset[str]] = ((), frozenset(), frozenset())
    if any(item.kind == "axiom" for item in items):
        ontology = await _ontology_or_404(db, change_set.ontology_id)
        vocabulary = await _axiom_vocabulary(
            db, ontology, all_items if all_items is not None else items
        )
    for item in items:
        target = targets.get(item.target_element_id) if item.target_element_id else None
        edited = None if item.edited is None else _review_fields(item.kind, item.edited)
        proposed = _review_fields(item.kind, item.proposed)
        turtle = (
            edited.turtle if edited and "turtle" in edited.model_fields_set else proposed.turtle
        )
        out.append(
            schemas.ChangeItem.model_validate(
                {
                    "id": item.id,
                    "seq": item.seq,
                    "op": item.op,
                    "kind": item.kind,
                    "target_element_id": item.target_element_id,
                    "temp_ref": item.temp_ref,
                    "proposed": proposed,
                    **_axiom_fields(item.kind, turtle, *vocabulary),
                    "edited": edited,
                    "before": _before(target) if target else None,
                    "decision": item.decision,
                    "confidence": item.confidence,
                    "rationale": item.rationale,
                    "flags": item.flags,
                    "note": item.note,
                    "decided_by": item.decided_by,
                    "decided_at": item.decided_at,
                    "applied_element_id": item.applied_element_id,
                    "evidence": evidence.get(item.id, []),
                    "resolution": resolutions.get(item.id),
                    "match": matches.get(item.id),
                },
            ),
        )
    return out


def _counts(decisions: Counter[str]) -> schemas.DecisionCounts:
    return schemas.DecisionCounts(
        total=sum(decisions.values()),
        pending=decisions["pending"],
        accepted=decisions["accepted"],
        rejected=decisions["rejected"],
    )


def _summary_data(
    change_set: ChangeSet, counts: schemas.DecisionCounts, names: Mapping[UUID, str]
) -> dict[str, Any]:
    return {
        "id": change_set.id,
        "ontology_id": change_set.ontology_id,
        "title": change_set.title,
        "source": change_set.source,
        "document_id": change_set.document_id,
        "status": change_set.status,
        "counts": counts,
        "created_by": change_set.created_by,
        "created_by_name": names.get(change_set.created_by) if change_set.created_by else None,
        "created_at": change_set.created_at,
        "merged_at": change_set.merged_at,
    }


async def _names(db: AsyncSession, change_sets: Sequence[ChangeSet]) -> dict[UUID, str]:
    """Display names of the change sets' submitters, read in one go from identity."""
    return await identity.display_names(
        db, {change_set.created_by for change_set in change_sets if change_set.created_by}
    )


async def _decision_counts(
    db: AsyncSession,
    change_set_ids: Sequence[UUID],
) -> dict[UUID, Counter[str]]:
    tallies: dict[UUID, Counter[str]] = defaultdict(Counter)
    if not change_set_ids:
        return tallies
    rows = await db.execute(
        select(ChangeItem.change_set_id, ChangeItem.decision, func.count())
        .where(ChangeItem.change_set_id.in_(change_set_ids))
        .group_by(ChangeItem.change_set_id, ChangeItem.decision),
    )
    for change_set_id, decision, count in rows:
        tallies[change_set_id][decision] = count
    return tallies


async def _summary(db: AsyncSession, change_set: ChangeSet) -> schemas.ChangeSetSummary:
    tallies = await _decision_counts(db, [change_set.id])
    names = await _names(db, [change_set])
    data = _summary_data(change_set, _counts(tallies[change_set.id]), names)
    return schemas.ChangeSetSummary.model_validate(data)


async def list_change_sets(
    db: AsyncSession,
    *,
    ontology_id: UUID | None,
    status: ChangeSetStatus | None,
) -> list[schemas.ChangeSetSummary]:
    """Newest first, with the number of items per decision."""
    statement = select(ChangeSet).order_by(ChangeSet.created_at.desc(), ChangeSet.id)
    if ontology_id is not None:
        statement = statement.where(ChangeSet.ontology_id == ontology_id)
    if status is not None:
        statement = statement.where(ChangeSet.status == status)
    change_sets = (await db.scalars(statement)).all()
    tallies = await _decision_counts(db, [change_set.id for change_set in change_sets])
    names = await _names(db, change_sets)
    return [
        schemas.ChangeSetSummary.model_validate(
            _summary_data(change_set, _counts(tallies[change_set.id]), names),
        )
        for change_set in change_sets
    ]


async def _items(db: AsyncSession, change_set: ChangeSet) -> Sequence[ChangeItem]:
    statement = select(ChangeItem).where(ChangeItem.change_set_id == change_set.id)
    return (await db.scalars(statement.order_by(ChangeItem.seq))).all()


async def _detail(db: AsyncSession, change_set: ChangeSet) -> schemas.ChangeSetDetail:
    items = await _items(db, change_set)
    counts = _counts(Counter(item.decision for item in items))
    data = _summary_data(change_set, counts, await _names(db, [change_set]))
    resolutions, token, links = await _resolutions(db, change_set, items)
    return schemas.ChangeSetDetail.model_validate(
        {
            **data,
            "items": await _items_out(db, change_set, items, resolutions, links),
            "resolution_token": token,
        }
    )


async def get_change_set(db: AsyncSession, change_set_id: UUID) -> schemas.ChangeSetDetail:
    return await _detail(db, await _change_set_or_404(db, change_set_id))


# ---------- change sets: review ----------


def _decide(item: ChangeItem, decision: Decision, actor: UUID, now: datetime) -> None:
    item.decision = decision
    if decision == "pending":
        item.decided_by = None
        item.decided_at = None
    else:
        item.decided_by = actor
        item.decided_at = now


def _ref_key(value: str) -> str:
    element_id = rules.parse_id(value)
    return f"id:{element_id}" if element_id is not None else f"ref:{value}"


def _closes_parent_loop(
    start: str,
    own_key: str | None,
    elements: dict[UUID, Element],
    creates: dict[str, ChangeItem],
) -> bool:
    """Whether walking up from `start` (a reference) leads back to the item being edited."""
    key: str | None = _ref_key(start)
    seen: set[str] = set()
    while key is not None and key not in seen:
        if key == own_key:
            return True
        seen.add(key)
        kind, _, value = key.partition(":")
        if kind == "id":
            element = elements.get(UUID(value))
            parent = element.parent_id if element else None
            key = f"id:{parent}" if parent else None
        else:
            sibling = creates.get(value)
            fields = rules.effective_fields(sibling.proposed, sibling.edited) if sibling else None
            key = _ref_key(fields.parent_ref) if fields and fields.parent_ref else None
    return False


async def _edit_problems(
    db: AsyncSession,
    change_set: ChangeSet,
    item: ChangeItem,
    fields: schemas.ElementFields,
) -> list[str]:
    elements = {
        element.id: element
        for element in await _elements(db, change_set.ontology_id, all_kinds=True)
    }
    target = elements.get(item.target_element_id) if item.target_element_id else None
    kind = item.kind
    problems = rules.field_problems(
        kind,
        item.op,
        fields,
        target_local_name=target.local_name if target else None,
        target_imported=target is not None and target.iri is not None,
        target_binding=target.binding if target else None,
    )
    siblings = await _items(db, change_set)
    creates = {
        sibling.temp_ref: sibling
        for sibling in siblings
        if sibling.op == "create" and sibling.temp_ref is not None
    }
    created_kinds = {temp_ref: sibling.kind for temp_ref, sibling in creates.items()}
    own_id = target.id if target else None
    reference_ok = True
    for name, value, kinds in item_references(kind, fields):
        problem = _reference_problem(
            value,
            elements,
            created_kinds,
            own_ref=item.temp_ref,
            own_id=own_id,
            require_active=kind != "metric",
            kinds=kinds,
        )
        if problem:
            reference_ok = False
            problems.append(f"{name} {problem}")
    if kind == "axiom" and fields.turtle:
        ontology = await _ontology_or_404(db, change_set.ontology_id)
        problem = axiom_problem(fields.turtle, header_of(ontology).prefix_map())
        if problem:
            problems.append(problem)
    if kind == "entity_type" and fields.parent_ref and reference_ok:
        own_key: str | None = None
        if own_id is not None:
            own_key = f"id:{own_id}"
        elif item.temp_ref is not None:
            own_key = f"ref:{item.temp_ref}"
        if _closes_parent_loop(fields.parent_ref, own_key, elements, creates):
            problems.append("parentRef would make the type hierarchy circular")
    if kind in BINDING_KINDS and not problems and item.op != "delete":
        found = await binding_rules.edit_problems(
            db,
            elements.values(),
            [
                binding_rules.Sibling(
                    id=sibling.id,
                    rejected=sibling.decision == "rejected",
                    item=binding_rules.Proposed(
                        op=sibling.op,
                        kind=sibling.kind,
                        target_id=sibling.target_element_id,
                        temp_ref=sibling.temp_ref,
                        fields=rules.effective_fields(sibling.proposed, sibling.edited),
                    ),
                )
                for sibling in siblings
            ],
            item.id,
            fields,
        )
        problems.extend(problem.message for problem in found)
    if kind == "metric" and not problems and item.op != "delete":
        relevant = [s for s in siblings if s.id == item.id or s.decision != "rejected"]
        index = next(i for i, s in enumerate(relevant) if s.id == item.id)
        proposals = [
            binding_rules.Proposed(
                op=s.op,
                kind=s.kind,
                target_id=s.target_element_id,
                temp_ref=s.temp_ref,
                fields=fields if s.id == item.id else rules.effective_fields(s.proposed, s.edited),
            )
            for s in relevant
        ]
        issues = metric_rules.proposal_problems(elements, proposals, only=index)
        problems.extend(message for _, message in issues)
    return problems


async def update_item(
    db: AsyncSession,
    change_set_id: UUID,
    item_id: UUID,
    patch: schemas.ItemDecisionPatch,
    *,
    actor: UUID,
    review_mode: ReviewMode,
) -> schemas.ChangeItem:
    """Set the decision, the reviewer's edit, the alignment decision and/or the note of one item.

    The alignment decision (spec 004, 5.5) is written on this item only, never on the other
    side, whose change set may be merged already.
    """
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    given = patch.model_fields_set
    if patch.decision is not None or "edited" in given or "match_decision" in given:
        _ensure_not_own(change_set, actor, review_mode)
    item = await db.scalar(
        select(ChangeItem).where(
            ChangeItem.id == item_id,
            ChangeItem.change_set_id == change_set.id,
        ),
    )
    if item is None:
        raise _change_set_not_found()
    if "edited" in given:
        if item.kind == "metric" and change_set.source != "manual":
            raise InvalidProposalError("Metric changes require a manual edit.")
        if patch.edited is None:
            item.edited = None
        else:
            edited = rules.stored_fields(patch.edited)
            fields = rules.effective_fields(item.proposed, edited)
            problems = await _edit_problems(db, change_set, item, fields)
            if problems:
                code = metric_rules.INVALID if item.kind == "metric" else "changeset.invalid_edit"
                raise AppError(422, code, "; ".join(problems) + ".")
            item.edited = edited
    if "match_decision" in given:
        if patch.match_decision is not None and not await _has_match(db, item):
            raise AppError(422, NO_MATCH, "The item has no alignment record to decide on.")
        if patch.match_decision is not None and item.match_kind == mergeplan.NAME:
            # The same main name leaves nothing to decide; renaming one of the two undoes it.
            raise AppError(422, NO_MATCH, "A record of the same main name takes no decision.")
        item.match_decision = patch.match_decision
    if patch.decision is not None:
        _decide(item, patch.decision, actor, _now())
    if "note" in given:
        item.note = rules.clean_text(patch.note)
    await db.commit()
    # The plan covers the whole change set: editing one item can change how others resolve.
    items = await _items(db, change_set)
    resolutions, _, links = await _resolutions(db, change_set, items)
    return (await _items_out(db, change_set, [item], resolutions, links, all_items=items))[0]


async def _has_match(db: AsyncSession, item: ChangeItem) -> bool:
    """Whether the item has an alignment record, or a merged item of another change set has
    one of it (spec 004, 5.5)."""
    if item.match_kind is not None:
        return True
    statement = (
        select(func.count())
        .select_from(ChangeItem)
        .join(ChangeSet, ChangeSet.id == ChangeItem.change_set_id)
        .where(ChangeItem.match_item_id == item.id, ChangeSet.status == "merged")
    )
    return bool(await db.scalar(statement))


async def decide_items(
    db: AsyncSession,
    change_set_id: UUID,
    body: schemas.BulkDecision,
    *,
    actor: UUID,
    review_mode: ReviewMode,
) -> schemas.ChangeSetDetail:
    """Apply one decision to several items; unknown item ids change nothing."""
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    _ensure_not_own(change_set, actor, review_mode)
    item_ids = set(body.item_ids)
    if item_ids:
        items = [item for item in await _items(db, change_set) if item.id in item_ids]
        if len(items) != len(item_ids):
            raise _change_set_not_found()
        now = _now()
        for item in items:
            _decide(item, body.decision, actor, now)
        await db.commit()
    return await _detail(db, change_set)


async def reject_change_set(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    actor: UUID,
    may_reject_any: bool,
    ip: str | None,
) -> schemas.ChangeSetSummary:
    """Close the change set without applying anything; pending items become rejected.

    Reviewers may reject any change set; others only withdraw their own.
    """
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    if not may_reject_any and change_set.created_by != actor:
        raise AppError(403, "auth.forbidden", "Only reviewers reject change sets of others.")
    now = _now()
    for item in await _items(db, change_set):
        if item.decision == "pending":
            _decide(item, "rejected", actor, now)
    change_set.status = "rejected"
    audit.record(
        db,
        "changeset.rejected",
        actor_id=actor,
        target_type="change_set",
        target_id=str(change_set.id),
        detail={"ontologyId": str(change_set.ontology_id)},
        ip=ip,
    )
    await db.commit()
    return await _summary(db, change_set)
