"""Ontologies, the working version, change sets (review and merge) and releases.

The HTTP operations commit their own transaction. The functions other modules call
(`get_ontology`, `list_alignment_elements`, `create_change_set`, `count_entity_types`,
`count_open_change_sets`) never commit: `create_change_set` only adds to the caller's
transaction.

Change sets are the only way the working version changes (AGENTS.md, "AI 不直接改本体").
"""

import hashlib
import re
import secrets
import string
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from ontology_platform.errors import AppError
from ontology_platform.modules.audit import service as audit
from ontology_platform.modules.ontology import rules, schemas
from ontology_platform.modules.ontology.models import (
    DATATYPES,
    ITEM_FLAGS,
    KINDS,
    ChangeItem,
    ChangeSet,
    ChangeSetSource,
    ChangeSetStatus,
    Decision,
    Element,
    Evidence,
    Kind,
    Ontology,
    Release,
)
from ontology_platform.modules.ontology.turtle import OntologyHeader, export_turtle

STALE_TARGET = "changeset.stale_target"
DEPENDENCY_SKIPPED = "changeset.dependency_skipped"
INVALID_ITEM = "changeset.invalid_item"

TITLE_MAX_LENGTH = 300
_KEY = re.compile(schemas.KEY_PATTERN)
_KEY_ALPHABET = string.ascii_lowercase + string.digits
_RANDOM_KEY_ATTEMPTS = 5


class InvalidProposalError(AppError):
    """`create_change_set` was given items that do not fit together or the ontology."""

    def __init__(self, detail: str) -> None:
        super().__init__(422, INVALID_ITEM, detail)


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


def _kind_order(element: Element) -> tuple[int, str]:
    return (KINDS.index(element.kind), element.local_name)


def _ontology_not_found() -> AppError:
    return AppError(404, "ontology.not_found", "Ontology not found.")


def _change_set_not_found() -> AppError:
    # Also used for an item id that is not part of the change set.
    return AppError(404, "changeset.not_found", "Change set or item not found.")


def _header(ontology: Ontology) -> OntologyHeader:
    return OntologyHeader(
        key=ontology.key,
        name=ontology.name,
        description=ontology.description,
        base_iri=ontology.base_iri,
    )


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


async def _elements(db: AsyncSession, ontology_id: UUID) -> list[Element]:
    statement = select(Element).where(Element.ontology_id == ontology_id)
    return sorted((await db.scalars(statement)).all(), key=_kind_order)


async def _active_elements(db: AsyncSession, ontology_id: UUID) -> list[Element]:
    return [element for element in await _elements(db, ontology_id) if element.status == "active"]


# ---------- interface for other modules ----------


async def get_ontology(db: AsyncSession, ontology_id: UUID) -> Ontology | None:
    return await db.get(Ontology, ontology_id)


async def list_alignment_elements(db: AsyncSession, ontology_id: UUID) -> list[Element]:
    """Every active element of the ontology, object types first, then by local name."""
    return await _active_elements(db, ontology_id)


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
) -> UUID:
    """Add an open change set with `items` (in order) to the caller's transaction.

    Raises `InvalidProposalError` when a temp_ref is repeated, a reference is neither an object
    type of the ontology nor the temp_ref of an object type created in this change set, or an
    update does not target an element of the ontology. Nothing is committed.
    """
    ontology = await db.get(Ontology, ontology_id)
    if ontology is None:
        raise _ontology_not_found()
    elements = {element.id: element for element in await _elements(db, ontology_id)}

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
        problem = _proposal_problem(item, elements, created_kinds)
        if problem:
            raise InvalidProposalError(f"Item {position}: {problem}.")

    change_set = ChangeSet(
        id=uuid4(),
        ontology_id=ontology_id,
        title=title.strip()[:TITLE_MAX_LENGTH],
        source=source,
        document_id=document_id,
        status="open",
        created_by=created_by,
        created_at=_now(),
    )
    db.add(change_set)
    # Explicit flushes keep parent rows ahead of child rows (there are no ORM relationships).
    await db.flush()
    audit.record(
        db,
        "changeset.created",
        # AI change sets are the platform's work, not the uploader's.
        actor_id=created_by if source == "manual" else None,
        target_type="change_set",
        target_id=str(change_set.id),
        detail={"source": source, "items": len(items)},
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
        db.add(row)
        rows.append((row, item))
    await db.flush()
    for row, item in rows:
        for evidence in item.evidence:
            db.add(
                Evidence(
                    id=uuid4(),
                    change_item_id=row.id,
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                    quote=evidence.quote,
                    char_start=evidence.char_start,
                    char_end=evidence.char_end,
                ),
            )
    return change_set.id


def _proposal_problem(
    item: schemas.ProposedItem,
    elements: dict[UUID, Element],
    created_kinds: dict[str, Kind],
) -> str | None:
    if item.op == "create":
        if item.target_element_id is not None:
            return "a create item has no target element"
    else:
        if item.temp_ref is not None:
            return "an update item has no temp_ref"
        target = elements.get(item.target_element_id) if item.target_element_id else None
        if target is None:
            return "the update target is not an element of this ontology"
        if target.kind != item.kind:
            return "the kind does not match the update target"
    unknown_flags = set(item.flags) - set(ITEM_FLAGS)
    if unknown_flags:
        return "unknown flags"
    for evidence in item.evidence:
        start, end = evidence.char_start, evidence.char_end
        if (start is None) != (end is None):
            return "evidence needs both charStart and charEnd, or neither"
        if start is not None and end is not None and end < start:
            return "evidence charEnd is before charStart"
    for name in rules.REF_FIELDS:
        value = getattr(item.proposed, name)
        if value is None:
            continue
        own_id = item.target_element_id if item.op == "update" else None
        problem = _reference_problem(
            value,
            elements,
            created_kinds,
            own_ref=item.temp_ref,
            own_id=own_id,
            require_active=False,
        )
        if problem:
            return f"{rules.wire_name(name)} {problem}"
    return None


def _reference_problem(
    value: str,
    elements: dict[UUID, Element],
    created_kinds: Mapping[str, str],
    *,
    own_ref: str | None,
    own_id: UUID | None,
    require_active: bool,
) -> str | None:
    """Why a reference cannot point at an object type, or None if it can."""
    element_id = rules.parse_id(value)
    if element_id is not None:
        element = elements.get(element_id)
        if element is None:
            return "refers to an element that is not in this ontology"
        if element.kind != "entity_type":
            return "must refer to an object type"
        if require_active and element.status != "active":
            return "refers to an element that is not active"
        if element_id == own_id:
            return "refers to the element itself"
        return None
    kind = created_kinds.get(value)
    if kind is None:
        return "refers to a temp_ref that is not in this change set"
    if kind != "entity_type":
        return "must refer to an object type"
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
                entity_type_count=counts["entity_type"],
                relation_type_count=counts["relation_type"],
                property_count=counts["property"],
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
        "iri": base_iri + element.local_name,
        "label_zh": element.label_zh,
        "label_en": element.label_en,
        "definition_zh": element.definition_zh,
        "definition_en": element.definition_en,
        "synonyms": element.synonyms,
        "parent_id": element.parent_id,
        "domain_id": element.domain_id,
        "range_id": element.range_id,
        "datatype": element.datatype,
        "unit": element.unit,
        "required": element.required,
        "multiple": element.multiple,
        "status": element.status,
        "origin": element.origin,
        "revision": element.revision,
        "created_at": element.created_at,
        "updated_at": element.updated_at,
    }


def element_out(element: Element, base_iri: str) -> schemas.Element:
    return schemas.Element.model_validate(_element_data(element, base_iri))


def _matches(element: Element, needle: str) -> bool:
    texts = [element.local_name, element.label_zh, element.label_en or ""]
    texts.extend(str(synonym.get("text", "")) for synonym in element.synonyms)
    return any(needle in text.casefold() for text in texts)


async def list_elements(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    kind: Kind | None,
    q: str | None,
) -> list[schemas.Element]:
    """All elements, optionally of one kind and matching `q` in names, labels or synonyms."""
    ontology = await _ontology_or_404(db, ontology_id)
    elements = await _elements(db, ontology_id)
    if kind is not None:
        elements = [element for element in elements if element.kind == kind]
    needle = (q or "").strip().casefold()
    if needle:
        elements = [element for element in elements if _matches(element, needle)]
    return [element_out(element, ontology.base_iri) for element in elements]


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
            label=element.label_zh,
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
                    label=element.label_zh,
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
    turtle = export_turtle(_header(ontology), elements, version=None, created=ontology.created_at)
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
                document_id=evidence.document_id,
                chunk_id=evidence.chunk_id,
                quote=evidence.quote,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
            ),
        )
    return grouped


def _before(element: Element) -> schemas.ElementFields:
    """The element's current values as item fields, with only the keys its kind uses."""
    data: dict[str, Any] = {
        "local_name": element.local_name,
        "label_zh": element.label_zh,
        "label_en": element.label_en,
        "definition_zh": element.definition_zh,
        "definition_en": element.definition_en,
        "synonyms": element.synonyms,
    }
    if element.kind == "entity_type":
        data["parent_ref"] = str(element.parent_id) if element.parent_id else None
    else:
        data["domain_ref"] = str(element.domain_id) if element.domain_id else None
        if element.kind == "relation_type":
            data["range_ref"] = str(element.range_id) if element.range_id else None
        else:
            data["datatype"] = element.datatype
            data["unit"] = element.unit
        data["required"] = element.required
        data["multiple"] = element.multiple
    return schemas.ElementFields.model_validate(data)


async def _items_out(db: AsyncSession, items: Sequence[ChangeItem]) -> list[schemas.ChangeItem]:
    evidence = await _evidence_by_item(db, [item.id for item in items])
    target_ids = {item.target_element_id for item in items if item.target_element_id}
    targets: dict[UUID, Element] = {}
    if target_ids:
        found = await db.scalars(select(Element).where(Element.id.in_(target_ids)))
        targets = {element.id: element for element in found}
    out: list[schemas.ChangeItem] = []
    for item in items:
        target = targets.get(item.target_element_id) if item.target_element_id else None
        edited = None if item.edited is None else schemas.ElementFields.model_validate(item.edited)
        out.append(
            schemas.ChangeItem.model_validate(
                {
                    "id": item.id,
                    "seq": item.seq,
                    "op": item.op,
                    "kind": item.kind,
                    "target_element_id": item.target_element_id,
                    "temp_ref": item.temp_ref,
                    "proposed": schemas.ElementFields.model_validate(item.proposed),
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


def _summary_data(change_set: ChangeSet, counts: schemas.DecisionCounts) -> dict[str, Any]:
    return {
        "id": change_set.id,
        "ontology_id": change_set.ontology_id,
        "title": change_set.title,
        "source": change_set.source,
        "document_id": change_set.document_id,
        "status": change_set.status,
        "counts": counts,
        "created_at": change_set.created_at,
        "merged_at": change_set.merged_at,
    }


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
    data = _summary_data(change_set, _counts(tallies[change_set.id]))
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
    return [
        schemas.ChangeSetSummary.model_validate(
            _summary_data(change_set, _counts(tallies[change_set.id])),
        )
        for change_set in change_sets
    ]


async def _items(db: AsyncSession, change_set: ChangeSet) -> Sequence[ChangeItem]:
    statement = select(ChangeItem).where(ChangeItem.change_set_id == change_set.id)
    return (await db.scalars(statement.order_by(ChangeItem.seq))).all()


async def _detail(db: AsyncSession, change_set: ChangeSet) -> schemas.ChangeSetDetail:
    items = await _items(db, change_set)
    counts = _counts(Counter(item.decision for item in items))
    data = _summary_data(change_set, counts)
    return schemas.ChangeSetDetail.model_validate({**data, "items": await _items_out(db, items)})


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
    elements = {element.id: element for element in await _elements(db, change_set.ontology_id)}
    target = elements.get(item.target_element_id) if item.target_element_id else None
    kind = item.kind
    problems = rules.field_problems(
        kind,
        item.op,
        fields,
        target_local_name=target.local_name if target else None,
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
    for name in rules.KIND_REFS[kind]:
        value = getattr(fields, name)
        if value is None:
            continue
        problem = _reference_problem(
            value,
            elements,
            created_kinds,
            own_ref=item.temp_ref,
            own_id=own_id,
            require_active=True,
        )
        if problem:
            reference_ok = False
            problems.append(f"{rules.wire_name(name)} {problem}")
    if kind == "entity_type" and fields.parent_ref and reference_ok:
        own_key: str | None = None
        if own_id is not None:
            own_key = f"id:{own_id}"
        elif item.temp_ref is not None:
            own_key = f"ref:{item.temp_ref}"
        if _closes_parent_loop(fields.parent_ref, own_key, elements, creates):
            problems.append("parentRef would make the type hierarchy circular")
    return problems


async def update_item(
    db: AsyncSession,
    change_set_id: UUID,
    item_id: UUID,
    patch: schemas.ItemDecisionPatch,
    *,
    actor: UUID,
) -> schemas.ChangeItem:
    """Set the decision, the reviewer's edit and/or the note of one item."""
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    item = await db.scalar(
        select(ChangeItem).where(
            ChangeItem.id == item_id,
            ChangeItem.change_set_id == change_set.id,
        ),
    )
    if item is None:
        raise _change_set_not_found()
    given = patch.model_fields_set
    if "edited" in given:
        if patch.edited is None:
            item.edited = None
        else:
            edited = rules.stored_fields(patch.edited)
            fields = rules.effective_fields(item.proposed, edited)
            problems = await _edit_problems(db, change_set, item, fields)
            if problems:
                raise AppError(422, "changeset.invalid_edit", "; ".join(problems) + ".")
            item.edited = edited
    if patch.decision is not None:
        _decide(item, patch.decision, actor, _now())
    if "note" in given:
        item.note = rules.clean_text(patch.note)
    await db.commit()
    return (await _items_out(db, [item]))[0]


async def decide_items(
    db: AsyncSession,
    change_set_id: UUID,
    body: schemas.BulkDecision,
    *,
    actor: UUID,
) -> schemas.ChangeSetDetail:
    """Apply one decision to several items; unknown item ids change nothing."""
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
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
    ip: str | None,
) -> schemas.ChangeSetSummary:
    """Close the change set without applying anything; pending items become rejected."""
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
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


# ---------- change sets: merge ----------


class _Merge:
    """Applies accepted items in order, each after the items it references.

    The outcome of an item is None when it was applied, otherwise the skip code.
    """

    def __init__(
        self,
        db: AsyncSession,
        change_set: ChangeSet,
        elements: Sequence[Element],
        items: Sequence[ChangeItem],
        now: datetime,
    ) -> None:
        self._db = db
        self._change_set = change_set
        self._elements = {element.id: element for element in elements}
        self._local_names = {element.local_name for element in elements}
        self._creates = {item.temp_ref: item for item in items if item.temp_ref is not None}
        self._visiting: set[UUID] = set()
        self._now = now
        self.outcomes: dict[UUID, str | None] = {}

    async def apply(self, item: ChangeItem) -> str | None:
        if item.id in self.outcomes:
            return self.outcomes[item.id]
        self._visiting.add(item.id)
        try:
            outcome = await self._apply(item)
        finally:
            self._visiting.discard(item.id)
        self.outcomes[item.id] = outcome
        return outcome

    async def _apply(self, item: ChangeItem) -> str | None:
        kind = item.kind
        target: Element | None = None
        if item.op == "update":
            target = self._elements.get(item.target_element_id) if item.target_element_id else None
            if target is None or target.kind != item.kind:
                return INVALID_ITEM
            if target.revision != item.target_revision:
                return STALE_TARGET
        fields = rules.effective_fields(item.proposed, item.edited)
        local_name = target.local_name if target else None
        if rules.field_problems(kind, item.op, fields, target_local_name=local_name):
            return INVALID_ITEM
        resolved: dict[str, UUID | None] = {}
        for name in rules.KIND_REFS[kind]:
            if name not in fields.model_fields_set:
                continue
            value = getattr(fields, name)
            if value is None:
                resolved[name] = None
                continue
            outcome, element_id = await self._resolve(value)
            if outcome is not None:
                return outcome
            resolved[name] = element_id
        if target is None:
            return await self._create(item, fields, resolved)
        return self._update(item, target, fields, resolved)

    async def _resolve(self, value: str) -> tuple[str | None, UUID | None]:
        element_id = rules.parse_id(value)
        if element_id is not None:
            element = self._elements.get(element_id)
            if element is None or element.kind != "entity_type" or element.status != "active":
                return INVALID_ITEM, None
            return None, element.id
        dependency = self._creates.get(value)
        if dependency is None or dependency.kind != "entity_type":
            return INVALID_ITEM, None
        if dependency.id in self._visiting:
            # The items reference each other in a loop.
            return INVALID_ITEM, None
        if dependency.decision != "accepted":
            return DEPENDENCY_SKIPPED, None
        if await self.apply(dependency) is not None:
            return DEPENDENCY_SKIPPED, None
        return None, dependency.applied_element_id

    async def _create(
        self,
        item: ChangeItem,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
    ) -> str | None:
        if fields.local_name is None or fields.label_zh is None:
            return INVALID_ITEM
        if fields.local_name in self._local_names:
            return INVALID_ITEM
        is_property = item.kind == "property"
        element = Element(
            id=uuid4(),
            ontology_id=self._change_set.ontology_id,
            kind=item.kind,
            local_name=fields.local_name,
            label_zh=fields.label_zh.strip(),
            label_en=rules.clean_text(fields.label_en),
            definition_zh=rules.clean_text(fields.definition_zh),
            definition_en=rules.clean_text(fields.definition_en),
            synonyms=rules.merge_synonyms(fields.synonyms or []),
            parent_id=resolved.get("parent_ref"),
            domain_id=resolved.get("domain_ref"),
            range_id=resolved.get("range_ref"),
            datatype=fields.datatype if is_property else None,
            unit=rules.clean_text(fields.unit) if is_property else None,
            required=bool(fields.required) and item.kind != "entity_type",
            multiple=bool(fields.multiple) and item.kind != "entity_type",
            status="active",
            origin="manual" if self._change_set.source == "manual" else "ai",
            revision=1,
            created_at=self._now,
            updated_at=self._now,
        )
        self._db.add(element)
        await self._db.flush()
        self._elements[element.id] = element
        self._local_names.add(element.local_name)
        item.applied_element_id = element.id
        return None

    def _has_ancestor(self, start: UUID, ancestor: UUID) -> bool:
        current: UUID | None = start
        seen: set[UUID] = set()
        while current is not None and current not in seen:
            if current == ancestor:
                return True
            seen.add(current)
            element = self._elements.get(current)
            current = element.parent_id if element else None
        return False

    def _update(
        self,
        item: ChangeItem,
        target: Element,
        fields: schemas.ElementFields,
        resolved: dict[str, UUID | None],
    ) -> str | None:
        given = fields.model_fields_set
        if "parent_ref" in resolved:
            parent_id = resolved["parent_ref"]
            if parent_id is not None and self._has_ancestor(parent_id, target.id):
                return INVALID_ITEM
            target.parent_id = parent_id
        if "domain_ref" in resolved:
            target.domain_id = resolved["domain_ref"]
        if "range_ref" in resolved:
            target.range_id = resolved["range_ref"]
        if "label_zh" in given and fields.label_zh is not None:
            target.label_zh = fields.label_zh.strip()
        if "label_en" in given:
            target.label_en = rules.clean_text(fields.label_en)
        if "definition_zh" in given:
            target.definition_zh = rules.clean_text(fields.definition_zh)
        if "definition_en" in given:
            target.definition_en = rules.clean_text(fields.definition_en)
        if fields.synonyms is not None:
            target.synonyms = rules.merge_synonyms(target.synonyms, fields.synonyms)
        if item.kind == "property":
            if fields.datatype is not None:
                target.datatype = fields.datatype
            if "unit" in given:
                target.unit = rules.clean_text(fields.unit)
        if item.kind != "entity_type":
            if fields.required is not None:
                target.required = fields.required
            if fields.multiple is not None:
                target.multiple = fields.multiple
        target.revision += 1
        target.updated_at = self._now
        item.applied_element_id = target.id
        return None


async def merge_change_set(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.MergeResult:
    """Apply the accepted items to the working version in one transaction.

    Skipped items: `changeset.stale_target` when an update's target changed after the item
    was proposed, `changeset.dependency_skipped` when a reference resolves to a rejected or
    skipped item (also transitively), `changeset.invalid_item` when the fields do not form a
    valid element, a reference is unusable, or the type hierarchy would become circular.
    """
    change_set = await _change_set_or_404(db, change_set_id)
    ontology = await _ontology_or_404(db, change_set.ontology_id, lock=True)
    change_set = await _change_set_or_404(db, change_set_id, lock=True)
    _ensure_open(change_set)
    items = await _items(db, change_set)
    if any(item.decision == "pending" for item in items):
        raise AppError(409, "changeset.pending_items", "Every item needs a decision first.")
    now = _now()
    merge = _Merge(db, change_set, await _elements(db, ontology.id), items, now)
    accepted = [item for item in items if item.decision == "accepted"]
    for item in accepted:
        await merge.apply(item)
    skipped = [
        schemas.MergeSkip.model_validate({"item_id": item.id, "code": merge.outcomes[item.id]})
        for item in accepted
        if merge.outcomes[item.id] is not None
    ]
    applied = len(accepted) - len(skipped)
    change_set.status = "merged"
    change_set.merged_by = actor
    change_set.merged_at = now
    ontology.updated_at = now
    audit.record(
        db,
        "changeset.merged",
        actor_id=actor,
        target_type="change_set",
        target_id=str(change_set.id),
        detail={"ontologyId": str(ontology.id), "applied": applied, "skipped": len(skipped)},
        ip=ip,
    )
    await db.commit()
    return schemas.MergeResult(applied=applied, skipped=skipped)


# ---------- releases ----------


def release_problems(elements: Sequence[Element]) -> list[schemas.ReleaseProblem]:
    """Publish checks (spec section 6) over the working version."""
    by_id = {element.id: element for element in elements}
    active = sorted((e for e in elements if e.status == "active"), key=_kind_order)
    problems: list[schemas.ReleaseProblem] = []

    def report(code: str, element: Element, message: str) -> None:
        problems.append(schemas.ReleaseProblem(code=code, element_id=element.id, message=message))

    def active_type(element_id: UUID | None) -> bool:
        target = by_id.get(element_id) if element_id is not None else None
        return target is not None and target.kind == "entity_type" and target.status == "active"

    for element in active:
        naming = rules.local_name_problem(element.kind, element.local_name)
        if naming:
            report("release.invalid_local_name", element, naming)
        if rules.is_blank(element.label_zh):
            report("release.missing_label", element, "labelZh is empty")
        if element.kind == "entity_type":
            if element.parent_id is not None and not active_type(element.parent_id):
                report("release.invalid_parent", element, "The parent type is missing or inactive")
            continue
        if not active_type(element.domain_id):
            report("release.invalid_domain", element, "The domain is missing or inactive")
        if element.kind == "relation_type" and not active_type(element.range_id):
            report("release.invalid_range", element, "The range is missing or inactive")
        if element.kind == "property" and element.datatype not in DATATYPES:
            report("release.invalid_datatype", element, "The datatype is missing or unknown")

    for element in active:
        if element.kind != "entity_type":
            continue
        current = element.parent_id
        seen: set[UUID] = set()
        while current is not None and current not in seen and current != element.id:
            seen.add(current)
            parent = by_id.get(current)
            current = parent.parent_id if parent else None
        if current == element.id:
            report("release.cyclic_hierarchy", element, "The type hierarchy loops back here")
    return problems


def _release_out(release: Release, active_release_id: UUID | None) -> schemas.ReleaseSummary:
    return schemas.ReleaseSummary(
        id=release.id,
        ontology_id=release.ontology_id,
        version=release.version,
        title=release.title,
        notes=release.notes,
        element_count=release.element_count,
        is_active=release.id == active_release_id,
        created_by=release.created_by,
        created_at=release.created_at,
    )


def _without_content() -> tuple[Any, ...]:
    return (defer(Release.snapshot), defer(Release.turtle))


async def _release_or_404(db: AsyncSession, release_id: UUID, *, content: bool = False) -> Release:
    statement = select(Release).where(Release.id == release_id)
    if not content:
        statement = statement.options(*_without_content())
    release = await db.scalar(statement)
    if release is None:
        raise AppError(404, "release.not_found", "Release not found.")
    return release


async def list_releases(db: AsyncSession, ontology_id: UUID) -> list[schemas.ReleaseSummary]:
    """Newest version first."""
    ontology = await _ontology_or_404(db, ontology_id)
    releases = await db.scalars(
        select(Release)
        .options(*_without_content())
        .where(Release.ontology_id == ontology_id)
        .order_by(Release.version.desc()),
    )
    return [_release_out(release, ontology.active_release_id) for release in releases]


async def publish_release(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.ReleaseCreate,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.ReleaseSummary:
    """Check the working version, then store an immutable snapshot as the next version and make
    it the current one. Raises `ReleaseInvalidError` when the checks fail."""
    ontology = await _ontology_or_404(db, ontology_id, lock=True)
    elements = await _elements(db, ontology_id)
    problems = release_problems(elements)
    if problems:
        raise ReleaseInvalidError(problems)
    snapshot = [
        element_out(element, ontology.base_iri)
        for element in elements
        if element.status == "active"
    ]
    latest = await db.scalar(
        select(func.max(Release.version)).where(Release.ontology_id == ontology_id),
    )
    version = (latest or 0) + 1
    now = _now()
    turtle = export_turtle(_header(ontology), snapshot, version=version, created=now)
    release = Release(
        id=uuid4(),
        ontology_id=ontology_id,
        version=version,
        title=body.title,
        notes=rules.clean_text(body.notes),
        snapshot=[element.model_dump(mode="json", by_alias=True) for element in snapshot],
        turtle=turtle,
        turtle_sha256=hashlib.sha256(turtle.encode()).hexdigest(),
        element_count=len(snapshot),
        created_by=actor,
        created_at=now,
    )
    db.add(release)
    await db.flush()
    ontology.active_release_id = release.id
    ontology.updated_at = now
    audit.record(
        db,
        "release.published",
        actor_id=actor,
        target_type="release",
        target_id=str(release.id),
        detail={"ontologyId": str(ontology_id), "version": version, "elementCount": len(snapshot)},
        ip=ip,
    )
    await db.commit()
    return _release_out(release, release.id)


async def get_release(db: AsyncSession, release_id: UUID) -> schemas.ReleaseSummary:
    release = await _release_or_404(db, release_id)
    active_id = await db.scalar(
        select(Ontology.active_release_id).where(Ontology.id == release.ontology_id),
    )
    return _release_out(release, active_id)


async def export_release(db: AsyncSession, release_id: UUID) -> tuple[str, str]:
    """The Turtle stored at publish time, and a file name for it."""
    release = await _release_or_404(db, release_id, content=True)
    key = await db.scalar(select(Ontology.key).where(Ontology.id == release.ontology_id))
    return release.turtle, f"{key}-v{release.version}.ttl"


async def activate_release(
    db: AsyncSession,
    release_id: UUID,
    *,
    actor: UUID,
    ip: str | None,
) -> schemas.ReleaseSummary:
    """Make the release the ontology's current version (also how a rollback is done)."""
    release = await _release_or_404(db, release_id)
    ontology = await _ontology_or_404(db, release.ontology_id, lock=True)
    previous = ontology.active_release_id
    ontology.active_release_id = release.id
    ontology.updated_at = _now()
    audit.record(
        db,
        "release.activated",
        actor_id=actor,
        target_type="release",
        target_id=str(release.id),
        detail={
            "ontologyId": str(ontology.id),
            "version": release.version,
            "previousReleaseId": str(previous) if previous else None,
        },
        ip=ip,
    )
    await db.commit()
    return _release_out(release, release.id)
