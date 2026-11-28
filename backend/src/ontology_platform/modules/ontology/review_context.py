"""Immutable input for review assistance."""

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, cast
from uuid import UUID

from rdflib import Graph, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ontology import rules, service, turtle
from ontology_platform.modules.ontology.models import (
    ChangeItem,
    ChangeSet,
    ChangeSetSource,
    Decision,
    Element,
    Evidence,
    ItemFlag,
    MatchDecision,
    MatchKind,
    Ontology,
)
from ontology_platform.modules.ontology.review_memory import MemoryEntry
from ontology_platform.modules.ontology.review_memory import _normalize as normalize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReviewItem:
    id: UUID
    seq: int
    fingerprint: str
    kind: str
    op: str
    decision: Decision
    label_zh: str | None
    label_en: str | None
    local_name: str | None
    definition: str | None
    parent: str | None
    domain: str | None
    range: str | None
    flags: tuple[ItemFlag, ...]
    confidence: float | None
    has_evidence: bool
    quotes: tuple[str, ...]
    match_kind: MatchKind | None
    match_decision: MatchDecision | None
    match_other_label: str | None
    kept_fields: tuple[str, ...]
    target_stale: bool


@dataclass(frozen=True)
class ElementBrief:
    id: UUID
    kind: str
    label_zh: str | None
    label_en: str | None
    local_name: str
    parent: str | None
    domain: str | None
    range: str | None
    disjoint: tuple[str, ...]


@dataclass(frozen=True)
class ReviewContext:
    change_set_id: UUID
    ontology_id: UUID
    status: str
    source: ChangeSetSource
    items: tuple[ReviewItem, ...]
    elements: tuple[ElementBrief, ...]
    rejected: tuple[MemoryEntry, ...]


def item_fingerprint(
    kind: str,
    op: str,
    target_element_id: UUID | None,
    proposed: Mapping[str, object],
    edited: Mapping[str, object] | None,
) -> str:
    payload = [kind, op, str(target_element_id) if target_element_id else None, proposed, edited]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def related_name(name: str, terms: Sequence[str]) -> bool:
    """The main-name part of the candidate score, kept in ontology to avoid an AI import."""
    key = normalize(name)
    return bool(key) and any(
        key == term
        or key in term
        or term in key
        or (
            len(key) > 1
            and len(term) > 1
            and SequenceMatcher(None, key, term, autojunk=False).ratio() >= 0.5
        )
        for term in terms
        if term
    )


def _label(element: Element | None) -> str | None:
    return (element.label_zh or element.label_en or element.local_name) if element else None


def disjoint_pairs(
    fragments: Sequence[str], prefixes: Mapping[str, str], active_types: Mapping[str, str]
) -> dict[str, tuple[str, ...]]:
    """Read only named class pairs from active axiom fragments."""
    found: dict[str, set[str]] = {iri: set() for iri in active_types}
    for fragment in fragments:
        try:
            triples = turtle.axiom_triples(fragment, prefixes)
            graph = Graph()
            for triple in triples:
                graph.add(triple)
            pairs = [(a, b) for a, b in graph.subject_objects(OWL.disjointWith)]
            for node in graph.subjects(RDF.type, OWL.AllDisjointClasses):
                for head in graph.objects(node, OWL.members):
                    try:
                        members = list(Collection(graph, head))
                    except (ValueError, TypeError):
                        continue
                    if all(
                        isinstance(member, URIRef) and str(member) in active_types
                        for member in members
                    ):
                        pairs.extend(
                            (left, right)
                            for index, left in enumerate(members)
                            for right in members[index + 1 :]
                        )
            for left, right in pairs:
                a, b = str(left), str(right)
                if (
                    isinstance(left, URIRef)
                    and isinstance(right, URIRef)
                    and a in found
                    and b in found
                ):
                    found[a].add(active_types[b])
                    found[b].add(active_types[a])
        except Exception as exc:
            logger.warning("Skipping invalid review axiom: %s", type(exc).__name__)
    return {iri: tuple(sorted(names)) for iri, names in found.items()}


async def review_context(
    db: AsyncSession, change_set_id: UUID, *, elements_max: int = 400, memory_max: int = 60
) -> ReviewContext:
    change_set = await db.get(ChangeSet, change_set_id)
    if change_set is None:
        raise AppError(404, "changeset.not_found", "Change set not found.")
    ontology = await db.get(Ontology, change_set.ontology_id)
    if ontology is None:
        raise AppError(404, "ontology.not_found", "Ontology not found.")
    raw_items = (
        await db.scalars(
            select(ChangeItem)
            .where(ChangeItem.change_set_id == change_set_id)
            .order_by(ChangeItem.seq)
        )
    ).all()
    chosen = [
        item for item in raw_items if item.kind in ("entity_type", "relation_type", "property")
    ]
    evidence = (
        (
            await db.scalars(
                select(Evidence)
                .where(Evidence.change_item_id.in_([item.id for item in chosen]))
                .order_by(
                    Evidence.document_id,
                    Evidence.chunk_id,
                    Evidence.char_start.nulls_last(),
                    Evidence.quote,
                    Evidence.id,
                )
            )
        ).all()
        if chosen
        else []
    )
    quotes: dict[UUID, list[str]] = {item.id: [] for item in chosen}
    has_evidence = {row.change_item_id for row in evidence}
    for row in evidence:
        if row.kind == "document" and len(quotes[row.change_item_id]) < 2:
            quotes[row.change_item_id].append(row.quote[:200])
    all_elements = (
        await db.scalars(select(Element).where(Element.ontology_id == change_set.ontology_id))
    ).all()
    by_id = {element.id: element for element in all_elements}
    match_ids = {item.match_item_id for item in chosen if item.match_item_id}
    matches = (
        {
            item.id: item
            for item in (
                await db.scalars(select(ChangeItem).where(ChangeItem.id.in_(match_ids)))
            ).all()
        }
        if match_ids
        else {}
    )
    plan = (
        await service._links(db, change_set, raw_items)
        if change_set.source == "ai_extraction"
        else service._NO_LINKS
    )
    resolutions = service._plan(change_set, ontology, all_elements, raw_items, plan).resolutions
    items: list[ReviewItem] = []
    for item in chosen:
        fields = rules.effective_fields(item.proposed, item.edited).model_dump(by_alias=True)
        target = by_id.get(item.target_element_id) if item.target_element_id else None

        def field(
            name: str,
            fields: dict[str, Any] = fields,
            target: Element | None = target,
        ) -> str | None:
            value = fields.get(name)
            if value is not None:
                return str(value)
            fallback = {
                "labelZh": target.label_zh if target else None,
                "labelEn": target.label_en if target else None,
                "localName": target.local_name if target else None,
                "definitionZh": target.definition_zh if target else None,
                "definitionEn": target.definition_en if target else None,
            }
            return fallback.get(name)

        def ref(name: str, fields: dict[str, Any] = fields) -> str | None:
            value = fields.get(name)
            if isinstance(value, str):
                try:
                    return _label(by_id.get(UUID(value))) or value
                except ValueError:
                    return value
            return None

        resolution = resolutions.get(item.id)
        items.append(
            ReviewItem(
                id=item.id,
                seq=item.seq,
                fingerprint=item_fingerprint(
                    item.kind, item.op, item.target_element_id, item.proposed, item.edited
                ),
                kind=item.kind,
                op=item.op,
                decision=cast(Decision, item.decision),
                label_zh=field("labelZh"),
                label_en=field("labelEn"),
                local_name=field("localName"),
                definition=field("definitionZh") or field("definitionEn"),
                parent=ref("parentRef"),
                domain=ref("domainRef"),
                range=ref("rangeRef"),
                flags=cast(tuple[ItemFlag, ...], tuple(item.flags)),
                confidence=item.confidence,
                has_evidence=item.id in has_evidence,
                quotes=tuple(quotes[item.id]),
                match_kind=cast(MatchKind | None, item.match_kind),
                match_decision=cast(MatchDecision | None, item.match_decision),
                match_other_label=_label(by_id.get(item.match_element_id))
                if item.match_element_id
                else (
                    (
                        matches[item.match_item_id].proposed.get("labelZh")
                        or matches[item.match_item_id].proposed.get("labelEn")
                    )
                    if item.match_item_id in matches
                    else None
                ),
                kept_fields=tuple(resolution.kept_fields) if resolution else (),
                target_stale=bool(target and item.target_revision != target.revision),
            )
        )
    active = [e for e in all_elements if e.status == "active"]
    names = {
        str(e.iri or ontology.base_iri + (e.local_name or "")): _label(e) or ""
        for e in active
        if e.kind == "entity_type"
    }
    header = turtle.OntologyHeader(
        ontology.key,
        ontology.name,
        ontology.description,
        ontology.base_iri,
        ontology.ontology_iri,
        ontology.prefixes,
    )
    disjoint = disjoint_pairs(
        [e.turtle for e in active if e.kind == "axiom" and e.turtle], header.prefix_map(), names
    )
    terms = tuple(
        normalize(name)
        for item in items
        for name in (item.label_zh, item.label_en, item.domain, item.range)
        if name
    )
    briefs = [
        ElementBrief(
            id=e.id,
            kind=e.kind,
            label_zh=e.label_zh,
            label_en=e.label_en,
            local_name=e.local_name or "",
            parent=_label(by_id.get(e.parent_id)) if e.parent_id else None,
            domain=_label(by_id.get(e.domain_id)) if e.domain_id else None,
            range=_label(by_id.get(e.range_id)) if e.range_id else None,
            disjoint=disjoint.get(str(e.iri or ontology.base_iri + (e.local_name or "")), ())
            if e.kind == "entity_type"
            else (),
        )
        for e in active
        if e.kind in ("entity_type", "relation_type", "property")
    ]
    briefs.sort(
        key=lambda e: (
            not any(
                related_name(name, terms) for name in (e.label_zh, e.label_en, e.local_name) if name
            ),
            e.label_zh or e.label_en or e.local_name,
        )
    )
    memory = await service.review_memory_for(db, change_set.ontology_id)
    rejected = [
        e
        for e in memory.entries
        if e.kind == "rejected"
        and (
            related_name(e.label, terms) or related_name(e.label_en or "", terms)
            if e.element_kind == "entity_type"
            else any(normalize(name) in terms for name in (e.domain, e.range) if name)
        )
    ]
    rejected.sort(key=lambda e: e.last_hit_at or e.created_at, reverse=True)
    return ReviewContext(
        change_set.id,
        change_set.ontology_id,
        change_set.status,
        cast(ChangeSetSource, change_set.source),
        tuple(items),
        tuple(briefs[:elements_max]),
        tuple(rejected[:memory_max]),
    )


async def item_fingerprints(db: AsyncSession, change_set_id: UUID) -> dict[UUID, str]:
    rows = (
        await db.scalars(select(ChangeItem).where(ChangeItem.change_set_id == change_set_id))
    ).all()
    return {
        row.id: item_fingerprint(row.kind, row.op, row.target_element_id, row.proposed, row.edited)
        for row in rows
    }
