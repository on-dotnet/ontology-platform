"""Staged extraction: terms → entity types and hierarchy → relations and properties → proposals.

This module is pure with respect to the database: callers pass in the document chunks and the
ontology's existing elements and receive proposals (spec 001 §4). Alignment with existing
elements, reference checks and evidence grounding are deterministic code, not model output.
"""

import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from ontology_platform.modules.ai.evidence import locate_quote
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.ai.prompts import (
    RELATIONS_INSTRUCTIONS,
    TERMS_INSTRUCTIONS,
    TYPES_INSTRUCTIONS,
    EntityTypeOut,
    Quote,
    RelationsOut,
    TermOut,
    TermsOut,
    TypesOut,
)

Kind = Literal["entity_type", "relation_type", "property"]
ProgressFn = Callable[[str, int, int], Awaitable[None]]

BATCH_CHARS = 8000
MAX_QUOTES = 3
UNFOUND_PENALTY = 0.5
# Local names stay well below the 128 characters the ontology allows, leaving room for "new:".
NAME_MAX = 100
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_CAMEL = re.compile(r"^[a-z][A-Za-z0-9]*$")


@dataclass(frozen=True)
class ChunkText:
    id: UUID
    seq: int
    text: str
    page: int | None = None
    heading: str | None = None


@dataclass(frozen=True)
class KnownElement:
    id: UUID
    kind: Kind
    local_name: str
    label_zh: str
    label_en: str | None = None
    synonyms: tuple[str, ...] = ()
    definition_zh: str | None = None
    domain_id: UUID | None = None
    range_id: UUID | None = None
    revision: int = 1


@dataclass
class ProposedEvidence:
    chunk_id: UUID
    quote: str
    char_start: int | None
    char_end: int | None


@dataclass
class Proposal:
    """One change item. `fields` uses the API's camelCase element field names (api-shapes)."""

    op: Literal["create", "update"]
    kind: Kind
    fields: dict[str, Any]
    target_element_id: UUID | None = None
    temp_ref: str | None = None
    # Revision of the target the model saw, so a merge can tell whether it changed since.
    target_revision: int | None = None
    confidence: float | None = None
    rationale: str | None = None
    flags: list[str] = field(default_factory=list)
    evidence: list[ProposedEvidence] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractionModels:
    standard: str
    reasoning: str


def normalize(text: str) -> str:
    """Comparison key: NFKC (full-width → half-width), lowercase, no whitespace."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def batches(chunks: Sequence[ChunkText], limit: int = BATCH_CHARS) -> list[list[ChunkText]]:
    groups: list[list[ChunkText]] = []
    current: list[ChunkText] = []
    size = 0
    for chunk in chunks:
        if current and size + len(chunk.text) > limit:
            groups.append(current)
            current, size = [], 0
        current.append(chunk)
        size += len(chunk.text)
    if current:
        groups.append(current)
    return groups


def render_chunks(chunks: Iterable[ChunkText]) -> str:
    return "\n\n".join(f"[chunk {chunk.seq}]\n{chunk.text}" for chunk in chunks)


class Extractor:
    def __init__(self, gateway: ModelGateway, models: ExtractionModels) -> None:
        self.gateway = gateway
        self.models = models

    async def run(
        self,
        *,
        document_id: UUID,
        title: str,
        chunks: Sequence[ChunkText],
        known: Sequence[KnownElement],
        progress: ProgressFn,
    ) -> list[Proposal]:
        groups = batches(chunks)
        terms = await self._terms(document_id, title, groups, progress)
        await progress("types", 0, 1)
        types = await self._types(document_id, title, terms, known)
        await progress("types", 1, 1)
        relations = await self._relations(document_id, title, groups, types, known, progress)
        await progress("changeset", 0, 1)
        proposals = build_proposals(chunks, known, types, relations)
        await progress("changeset", 1, 1)
        return proposals

    async def _terms(
        self, document_id: UUID, title: str, groups: list[list[ChunkText]], progress: ProgressFn
    ) -> list[TermOut]:
        found: dict[str, TermOut] = {}
        await progress("terms", 0, len(groups))
        for index, group in enumerate(groups, start=1):
            result = await self.gateway.structured(
                purpose="extract.terms",
                model=self.models.standard,
                instructions=TERMS_INSTRUCTIONS,
                text=f"Document: {title}\n\n{render_chunks(group)}",
                schema=TermsOut,
                document_id=document_id,
            )
            for term in result.terms:
                key = normalize(term.name)
                if key and key not in found:
                    found[key] = term
                elif key:
                    found[key].quotes.extend(term.quotes)
            await progress("terms", index, len(groups))
        return list(found.values())

    async def _types(
        self, document_id: UUID, title: str, terms: list[TermOut], known: Sequence[KnownElement]
    ) -> list[EntityTypeOut]:
        existing = [element for element in known if element.kind == "entity_type"]
        lines = ["Existing entity types (id | label | synonyms):"]
        lines += [
            f"- {element.id} | {element.label_zh} | {', '.join(element.synonyms)}"
            for element in existing
        ] or ["- (none)"]
        lines.append("\nCandidate terms (category | name | english | definition | quotes):")
        for term in terms:
            quotes = "; ".join(f"[chunk {q.chunk}] {q.text}" for q in term.quotes[:MAX_QUOTES])
            lines.append(
                f"- {term.category} | {term.name} | {term.english or ''} | "
                f"{term.definition or ''} | {quotes}"
            )
        result = await self.gateway.structured(
            purpose="extract.types",
            model=self.models.reasoning,
            instructions=TYPES_INSTRUCTIONS,
            text=f"Document: {title}\n\n" + "\n".join(lines),
            schema=TypesOut,
            document_id=document_id,
        )
        return result.entity_types

    async def _relations(
        self,
        document_id: UUID,
        title: str,
        groups: list[list[ChunkText]],
        types: list[EntityTypeOut],
        known: Sequence[KnownElement],
        progress: ProgressFn,
    ) -> RelationsOut:
        catalog = [f"- {t.ref} | {t.label_zh} | {t.definition_zh or ''}" for t in types]
        catalog += [
            f"- {element.id} | {element.label_zh} | {element.definition_zh or ''}"
            for element in known
            if element.kind == "entity_type" and str(element.id) not in {t.ref for t in types}
        ]
        header = "Entity types (ref | label | definition):\n" + "\n".join(catalog)
        merged = RelationsOut(relations=[], properties=[])
        await progress("relations", 0, len(groups))
        for index, group in enumerate(groups, start=1):
            result = await self.gateway.structured(
                purpose="extract.relations",
                model=self.models.standard,
                instructions=RELATIONS_INSTRUCTIONS,
                text=f"Document: {title}\n\n{header}\n\n{render_chunks(group)}",
                schema=RelationsOut,
                document_id=document_id,
            )
            merged.relations.extend(result.relations)
            merged.properties.extend(result.properties)
            await progress("relations", index, len(groups))
        return merged


# ---------------------------------------------------------------------------- proposals


class _Builder:
    def __init__(self, chunks: Sequence[ChunkText], known: Sequence[KnownElement]) -> None:
        self.by_seq = {chunk.seq: chunk for chunk in chunks}
        self.chunks = list(chunks)
        self.known = list(known)
        self.known_ids = {str(element.id): element for element in known}
        self.used_names = {element.local_name for element in known}
        self.proposals: list[Proposal] = []
        self.updates: dict[UUID, Proposal] = {}

    def ground(self, quotes: Sequence[Quote]) -> tuple[list[ProposedEvidence], bool]:
        """Locate each quote; returns the evidence and whether every quote was found."""
        evidence: list[ProposedEvidence] = []
        all_found = bool(quotes)
        for quote in quotes[:MAX_QUOTES]:
            candidates = [self.by_seq[quote.chunk]] if quote.chunk in self.by_seq else []
            candidates += [chunk for chunk in self.chunks if chunk not in candidates]
            for chunk in candidates:
                located = locate_quote(quote.text, chunk.text)
                if located:
                    evidence.append(
                        ProposedEvidence(chunk.id, quote.text, located.char_start, located.char_end)
                    )
                    break
            else:
                all_found = False
                fallback = self.by_seq.get(quote.chunk) or (self.chunks[0] if self.chunks else None)
                if fallback is not None:
                    evidence.append(ProposedEvidence(fallback.id, quote.text[:500], None, None))
        return evidence, all_found

    def known_type(self, ref: str) -> str | None:
        """`ref` if it is the id of an existing object type (relations and parents need one)."""
        element = self.known_ids.get(ref)
        return ref if element is not None and element.kind == "entity_type" else None

    def unique_name(self, wanted: str, pattern: re.Pattern[str], fallback: str) -> str:
        base = wanted[:NAME_MAX] if pattern.match(wanted) else fallback
        name, counter = base, 2
        while name in self.used_names:
            name, counter = f"{base}{counter}", counter + 1
        self.used_names.add(name)
        return name

    def match_known(
        self, kind: Kind, labels: Iterable[str], domain: UUID | None = None
    ) -> KnownElement | None:
        keys = {normalize(label) for label in labels if label}
        for element in self.known:
            if element.kind != kind or (domain is not None and element.domain_id != domain):
                continue
            names = {element.label_zh, element.local_name, *element.synonyms}
            if element.label_en:
                names.add(element.label_en)
            if keys & {normalize(name) for name in names}:
                return element
        return None

    def add(self, proposal: Proposal, quotes: Sequence[Quote], confidence: float) -> None:
        evidence, all_found = self.ground(quotes)
        proposal.evidence = evidence
        proposal.confidence = max(0.0, min(1.0, confidence))
        if not all_found:
            proposal.flags.append("evidence_not_found")
            proposal.confidence = round(proposal.confidence * UNFOUND_PENALTY, 3)
        self.proposals.append(proposal)


def build_proposals(
    chunks: Sequence[ChunkText],
    known: Sequence[KnownElement],
    types: Sequence[EntityTypeOut],
    relations: RelationsOut,
) -> list[Proposal]:
    builder = _Builder(chunks, known)
    # ref (model's) -> reference usable in the change set: existing id or our temp_ref
    refs: dict[str, str] = {}
    new_types: list[tuple[EntityTypeOut, Proposal]] = []

    for item in types:
        if item.ref in builder.known_ids and builder.known_ids[item.ref].kind == "entity_type":
            refs[item.ref] = item.ref
            _maybe_update(builder, builder.known_ids[item.ref], item.synonyms, item, item.quotes)
            continue
        labels = [item.label_zh, item.label_en or "", *item.synonyms]
        existing = builder.match_known("entity_type", labels)
        if existing is not None:
            refs[item.ref] = str(existing.id)
            _maybe_update(builder, existing, item.synonyms, item, item.quotes)
            continue
        label_key = normalize(item.label_zh)
        duplicate = next(
            (p for _, p in new_types if normalize(p.fields["labelZh"]) == label_key), None
        )
        if duplicate is not None:
            refs[item.ref] = duplicate.temp_ref or ""
            continue
        local_name = builder.unique_name(item.local_name, _PASCAL, "EntityType")
        temp_ref = f"new:{local_name}"
        refs[item.ref] = temp_ref
        proposal = Proposal(
            op="create",
            kind="entity_type",
            temp_ref=temp_ref,
            rationale=item.rationale,
            fields={
                "localName": local_name,
                "labelZh": item.label_zh,
                "labelEn": item.label_en,
                "definitionZh": item.definition_zh,
                "synonyms": _synonyms(item.synonyms, item.label_zh),
                "parentRef": None,
            },
        )
        new_types.append((item, proposal))
        builder.add(proposal, item.quotes, item.confidence)

    # Parents are resolved after all types are known: a type of this run or an existing one.
    # Unknown or self parents are dropped.
    for item, proposal in new_types:
        parent = (refs.get(item.parent) or builder.known_type(item.parent)) if item.parent else None
        if parent and parent != proposal.temp_ref:
            proposal.fields["parentRef"] = parent

    seen_relations: set[tuple[str, str, str]] = set()
    for relation in relations.relations:
        domain = refs.get(relation.domain) or builder.known_type(relation.domain)
        range_ = refs.get(relation.range) or builder.known_type(relation.range)
        if domain is None or range_ is None:
            continue  # the model referenced a type that does not exist
        key = (domain, range_, normalize(relation.label_zh))
        if key in seen_relations:
            continue
        seen_relations.add(key)
        domain_uuid = _as_uuid(domain)
        if domain_uuid and builder.match_known("relation_type", [relation.label_zh], domain_uuid):
            continue
        local_name = builder.unique_name(relation.local_name, _CAMEL, "relatedTo")
        builder.add(
            Proposal(
                op="create",
                kind="relation_type",
                rationale=relation.rationale,
                fields={
                    "localName": local_name,
                    "labelZh": relation.label_zh,
                    "labelEn": relation.label_en,
                    "definitionZh": relation.definition_zh,
                    "synonyms": [],
                    "domainRef": domain,
                    "rangeRef": range_,
                    "required": relation.required,
                    "multiple": relation.multiple,
                },
            ),
            relation.quotes,
            relation.confidence,
        )

    seen_properties: set[tuple[str, str]] = set()
    for prop in relations.properties:
        domain = refs.get(prop.domain) or builder.known_type(prop.domain)
        if domain is None:
            continue
        prop_key = (domain, normalize(prop.label_zh))
        if prop_key in seen_properties:
            continue
        seen_properties.add(prop_key)
        domain_uuid = _as_uuid(domain)
        if domain_uuid and builder.match_known("property", [prop.label_zh], domain_uuid):
            continue
        local_name = builder.unique_name(prop.local_name, _CAMEL, "attribute")
        builder.add(
            Proposal(
                op="create",
                kind="property",
                rationale=prop.rationale,
                fields={
                    "localName": local_name,
                    "labelZh": prop.label_zh,
                    "labelEn": prop.label_en,
                    "definitionZh": prop.definition_zh,
                    "synonyms": [],
                    "domainRef": domain,
                    "datatype": prop.datatype,
                    "unit": prop.unit,
                    "required": prop.required,
                    "multiple": prop.multiple,
                },
            ),
            prop.quotes,
            prop.confidence,
        )
    return builder.proposals


def _synonyms(values: Iterable[str], label: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen = {normalize(label)}
    for value in values:
        key = normalize(value)
        if value and key not in seen:
            seen.add(key)
            lang = "en" if value.isascii() else "zh"
            out.append({"lang": lang, "text": value})
    return out


def _maybe_update(
    builder: _Builder,
    element: KnownElement,
    synonyms: Sequence[str],
    item: EntityTypeOut,
    quotes: Sequence[Quote],
) -> None:
    """Propose adding synonyms or a missing definition to an existing type; nothing otherwise.

    Several model types can land on the same existing type. They become one update: two
    updates of one element in a change set would make the second look stale at merge time.
    """
    previous = builder.updates.get(element.id)
    known = {normalize(s) for s in (*element.synonyms, element.label_zh, element.label_en or "")}
    if previous is not None:
        known |= {normalize(s["text"]) for s in previous.fields.get("synonyms", [])}
    added = [s for s in _synonyms(synonyms, element.label_zh) if normalize(s["text"]) not in known]
    fields: dict[str, Any] = {}
    if added:
        fields["synonyms"] = added
    if (
        not element.definition_zh
        and item.definition_zh
        and (previous is None or "definitionZh" not in previous.fields)
    ):
        fields["definitionZh"] = item.definition_zh
    if not fields:
        return
    if previous is not None:
        previous.fields.setdefault("synonyms", []).extend(fields.pop("synonyms", []))
        previous.fields.update(fields)
        evidence, _ = builder.ground(quotes)
        previous.evidence.extend(evidence)
        return
    proposal = Proposal(
        op="update",
        kind="entity_type",
        target_element_id=element.id,
        target_revision=element.revision,
        rationale=item.rationale,
        fields=fields,
    )
    builder.updates[element.id] = proposal
    builder.add(proposal, quotes, item.confidence)


def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None
