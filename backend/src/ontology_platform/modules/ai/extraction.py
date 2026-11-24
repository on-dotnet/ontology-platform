"""Staged extraction: terms → entity types and hierarchy → relations and properties → proposals.

This module is pure with respect to the database: callers pass in the document chunks and the
ontology's existing elements and receive proposals (spec 001 §4). Alignment with existing
elements, reference checks and evidence grounding are deterministic code, not model output.
"""

import re
import unicodedata
from collections import Counter
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
# Candidate terms per call of the types stage: a large document's terms would not fit one call.
TYPES_BATCH_TERMS = 150
MAX_QUOTES = 3
UNFOUND_PENALTY = 0.5
# Local names stay well below the 128 characters the ontology allows, leaving room for "new:".
NAME_MAX = 100
# Shorter names (one character after normalizing) occur everywhere: they neither merge types
# nor count as naming a type in a relation's evidence.
MIN_NAME = 2
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
        types = await self._types(document_id, title, terms, known, progress)
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
        self,
        document_id: UUID,
        title: str,
        terms: list[TermOut],
        known: Sequence[KnownElement],
        progress: ProgressFn,
    ) -> list[EntityTypeOut]:
        """Types in batches of terms; later batches see the types found so far and reuse them."""
        existing = [element for element in known if element.kind == "entity_type"]
        groups = [
            terms[start : start + TYPES_BATCH_TERMS]
            for start in range(0, len(terms), TYPES_BATCH_TERMS)
        ] or [[]]
        found: list[EntityTypeOut] = []
        await progress("types", 0, len(groups))
        for index, group in enumerate(groups, start=1):
            result = await self.gateway.structured(
                purpose="extract.types",
                model=self.models.reasoning,
                instructions=TYPES_INSTRUCTIONS,
                text=f"Document: {title}\n\n" + "\n".join(_types_lines(existing, found, group)),
                schema=TypesOut,
                document_id=document_id,
            )
            found = merge_types(found, result.entity_types)
            await progress("types", index, len(groups))
        return found

    async def _relations(
        self,
        document_id: UUID,
        title: str,
        groups: list[list[ChunkText]],
        types: list[EntityTypeOut],
        known: Sequence[KnownElement],
        progress: ProgressFn,
    ) -> RelationsOut:
        catalog = [
            f"- {t.ref} | {t.label_zh} | {', '.join(t.synonyms)} | {t.definition_zh or ''}"
            for t in types
        ]
        catalog += [
            f"- {element.id} | {element.label_zh} | {', '.join(element.synonyms)} | "
            f"{element.definition_zh or ''}"
            for element in known
            if element.kind == "entity_type" and str(element.id) not in {t.ref for t in types}
        ]
        header = "Entity types (ref | label | synonyms | definition):\n" + "\n".join(catalog)
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


def _types_lines(
    existing: Sequence[KnownElement], found: Sequence[EntityTypeOut], terms: Sequence[TermOut]
) -> list[str]:
    lines = ["Existing entity types (id | label | synonyms):"]
    lines += [
        f"- {element.id} | {element.label_zh} | {', '.join(element.synonyms)}"
        for element in existing
    ] or ["- (none)"]
    if found:
        lines.append(
            "\nEntity types proposed from earlier terms of this document; reuse their ref "
            "instead of proposing duplicates (ref | label | synonyms):"
        )
        lines += [f"- {item.ref} | {item.label_zh} | {', '.join(item.synonyms)}" for item in found]
    lines.append("\nCandidate terms (category | name | english | definition | quotes):")
    for term in terms:
        quotes = "; ".join(f"[chunk {q.chunk}] {q.text}" for q in term.quotes[:MAX_QUOTES])
        lines.append(
            f"- {term.category} | {term.name} | {term.english or ''} | "
            f"{term.definition or ''} | {quotes}"
        )
    return lines


def merge_types(
    found: Sequence[EntityTypeOut], batch: Iterable[EntityTypeOut]
) -> list[EntityTypeOut]:
    """Adds a batch's types; one reusing the ref of an earlier batch's type extends that type.

    Only earlier batches are merged into: a single batch is kept exactly as the model returned
    it, and duplicates by name are left to `build_proposals`, as before batching. A ref that
    earlier batches gave to several types is not extended either: which one is meant is
    unknown, so the type is added and `build_proposals` resolves the shared ref.
    """
    merged = list(found)
    earlier = {item.ref: index for index, item in enumerate(found)}
    shared = {ref for ref, count in Counter(item.ref for item in found).items() if count > 1}
    for item in batch:
        index = earlier.get(item.ref)
        if index is None or item.ref in shared:
            merged.append(item)
            continue
        other = merged[index]
        seen = {normalize(value) for value in other.synonyms}
        merged[index] = other.model_copy(
            update={
                "synonyms": [
                    *other.synonyms,
                    *(value for value in item.synonyms if normalize(value) not in seen),
                ],
                "quotes": [*other.quotes, *item.quotes],
                "label_en": other.label_en or item.label_en,
                "definition_zh": other.definition_zh or item.definition_zh,
                "parent": other.parent or item.parent,
            }
        )
    return merged


# ---------------------------------------------------------------------------- proposals


class _Builder:
    def __init__(self, chunks: Sequence[ChunkText], known: Sequence[KnownElement]) -> None:
        self.by_seq = {chunk.seq: chunk for chunk in chunks}
        self.by_id = {chunk.id: chunk for chunk in chunks}
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

    def states_link(
        self, evidence: Sequence[ProposedEvidence], domain: set[str], range_: set[str]
    ) -> bool:
        """Whether a located quote's line names both ends (by any of their normalized names).

        A line is the unit of direct evidence: a sentence group, list item or table row. Only
        the longest mentions count, and the two ends need mentions that do not overlap: a name
        inside a longer name (钢种 in 钢种成分要求) is not a mention of its own, and a type
        related to itself has to be named twice.
        """
        for item in evidence:
            chunk = self.by_id.get(item.chunk_id)
            if chunk is None or item.char_start is None or item.char_end is None:
                continue
            start = chunk.text.rfind("\n", 0, item.char_start) + 1
            end = chunk.text.find("\n", item.char_end)
            line = normalize(chunk.text[start : end if end != -1 else len(chunk.text)])
            mentions = [
                (span, side)
                for side, names in enumerate((domain, range_))
                for span in _mentions(line, names)
            ]
            longest = [
                (span, side)
                for span, side in mentions
                if not any(_inside(span, other) for other, _ in mentions)
            ]
            if any(
                a_side == 0 and b_side == 1 and (a[1] <= b[0] or b[1] <= a[0])
                for a, a_side in longest
                for b, b_side in longest
            ):
                return True
        return False

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
    # Each type the model gave -> the type it is in the change set: an existing id or our
    # temp_ref. The model sometimes gives one ref to two types; see `resolve`.
    became: list[tuple[EntityTypeOut, str]] = []
    new_types: list[tuple[EntityTypeOut, Proposal]] = []

    for item in types:
        labels = [item.label_zh, item.label_en or "", *item.synonyms]
        claimed = builder.known_ids.get(item.ref)
        if claimed is not None and claimed.kind != "entity_type":
            claimed = None
        # An existing type reused by its id keeps one of its names. A type given the id of an
        # existing type it shares no name with is a mistaken id, or a new name for that type:
        # it is aligned by its own names, and if it stays new a reviewer decides.
        if claimed is not None and _keys(labels) & _element_keys(claimed):
            became.append((item, item.ref))
            _maybe_update(builder, claimed, item.synonyms, item, item.quotes)
            continue
        existing = builder.match_known("entity_type", labels)
        if existing is not None:
            became.append((item, str(existing.id)))
            _maybe_update(builder, existing, item.synonyms, item, item.quotes)
            continue
        # A new type with a label that is a name of an earlier new type, or with a name that is
        # that type's label, is the same concept. Synonyms alone do not merge: two kinds of one
        # thing often share one.
        item_labels = _keys([item.label_zh, item.label_en or ""])
        item_synonyms = _keys(item.synonyms)
        duplicate = next(
            (
                p
                for _, p in new_types
                if item_labels & _type_keys(p) or item_synonyms & _label_keys(p)
            ),
            None,
        )
        if duplicate is not None:
            became.append((item, duplicate.temp_ref or ""))
            duplicate.fields["synonyms"] += [
                s
                for s in _synonyms(
                    [item.label_zh, item.label_en or "", *item.synonyms],
                    duplicate.fields["labelZh"],
                )
                if normalize(s["text"]) not in _type_keys(duplicate)
            ]
            evidence, _ = builder.ground(item.quotes)
            duplicate.evidence += [e for e in evidence if e.char_start is not None]
            continue
        local_name = builder.unique_name(item.local_name, _PASCAL, "EntityType")
        temp_ref = f"new:{local_name}"
        became.append((item, temp_ref))
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
        # Only a synonym is shared with another new type, or the model took it for an existing
        # type whose names it does not have: ask a human.
        if claimed is not None or any(item_synonyms & _type_keys(p) for _, p in new_types):
            proposal.flags.append("possible_duplicate")
        new_types.append((item, proposal))
        builder.add(proposal, item.quotes, item.confidence)

    targets: dict[str, set[str]] = {}
    for item, target in became:
        targets.setdefault(item.ref, set()).add(target)

    def resolve(ref: str) -> str | None:
        """The type a ref of the model stands for, or None.

        A ref the model gave to types that stayed apart (their names do not merge them) stands
        for none of them: which one a parent, relation or property meant is unknown, so the
        reference is dropped, while the types themselves are kept.
        """
        found = targets.get(ref)
        if found is None:
            return builder.known_type(ref)
        if len(found) > 1:
            return None
        return next(iter(found))

    # Parents are resolved after all types are known: a type of this run or an existing one.
    # Unknown, ambiguous or self parents are dropped.
    for item, proposal in new_types:
        parent = resolve(item.parent) if item.parent else None
        if parent and parent != proposal.temp_ref:
            proposal.fields["parentRef"] = parent

    # Every name a type goes by in this run, to check that a relation's evidence names its ends.
    # A model type's names count only for the type it became, whatever ref it shares.
    names_of: dict[str, set[str]] = {
        str(element.id): _element_keys(element)
        for element in known
        if element.kind == "entity_type"
    }
    for item, target in became:
        names_of.setdefault(target, set()).update(
            _keys([item.label_zh, item.label_en or "", *item.synonyms])
        )

    seen_relations: set[tuple[str, str, str]] = set()
    for relation in relations.relations:
        domain = resolve(relation.domain)
        range_ = resolve(relation.range)
        if domain is None or range_ is None:
            continue  # the model referenced a type that does not exist, or an ambiguous ref
        key = (domain, range_, normalize(relation.label_zh))
        if key in seen_relations:
            continue
        evidence, _ = builder.ground(relation.quotes)
        if not builder.states_link(
            evidence, names_of.get(domain, set()), names_of.get(range_, set())
        ):
            continue  # no direct evidence: no quote's line names both types
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
        domain = resolve(prop.domain)
        if domain is None:
            continue  # as for relations
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


def _keys(names: Iterable[str]) -> set[str]:
    """Normalized names long enough to identify a type."""
    return {key for key in (normalize(name) for name in names) if len(key) >= MIN_NAME}


def _label_keys(proposal: Proposal) -> set[str]:
    return _keys([proposal.fields["labelZh"], proposal.fields.get("labelEn") or ""])


def _type_keys(proposal: Proposal) -> set[str]:
    """Names of a proposed new type: its labels and synonyms."""
    return _label_keys(proposal) | _keys(s["text"] for s in proposal.fields["synonyms"])


def _element_keys(element: KnownElement) -> set[str]:
    return _keys([element.label_zh, element.label_en or "", *element.synonyms])


def _mentions(line: str, names: set[str]) -> list[tuple[int, int]]:
    """Spans of every occurrence of any of the names in a normalized line."""
    spans: list[tuple[int, int]] = []
    for name in names:
        start = line.find(name)
        while start != -1:
            spans.append((start, start + len(name)))
            start = line.find(name, start + 1)
    return spans


def _inside(span: tuple[int, int], other: tuple[int, int]) -> bool:
    """Whether `span` lies within the longer `other`."""
    return other[0] <= span[0] and span[1] <= other[1] and other[1] - other[0] > span[1] - span[0]


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
