"""Staged extraction: terms → entity types → resolve → relations and properties → proposals.

This module is pure with respect to the database: callers pass in the document chunks and the
ontology's existing elements and receive proposals (spec 001 §4). Whether a new object type is
one that exists already is shortlisted by name (`candidates`), judged by the model (`resolve`)
and bounded by deterministic guardrails (spec 004, section 4). Reference checks and evidence
grounding are deterministic code, not model output.
"""

import re
from collections import Counter
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from ontology_platform.modules.ai.candidates import (
    PER_TYPE,
    THRESHOLD,
    Names,
    Score,
    same_main_name,
    score,
    shortlist,
)
from ontology_platform.modules.ai.candidates import normalize as normalize
from ontology_platform.modules.ai.evidence import locate_quote
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.ai.prompts import (
    RELATIONS_INSTRUCTIONS,
    RESOLVE_INSTRUCTIONS,
    TERMS_INSTRUCTIONS,
    TYPES_INSTRUCTIONS,
    EntityTypeOut,
    Quote,
    RelationsOut,
    ResolveOut,
    TermOut,
    TermsOut,
    TypesOut,
)
from ontology_platform.modules.ai.sentences import covering, split_sentences

Kind = Literal["entity_type", "relation_type", "property"]
ProgressFn = Callable[[str, int, int], Awaitable[None]]
Verdict = Literal["same", "different", "unsure"]

BATCH_CHARS = 8000
# Candidate terms per call of the types stage: a large document's terms would not fit one call.
TYPES_BATCH_TERMS = 150
MAX_QUOTES = 3
UNFOUND_PENALTY = 0.5
# Local names stay well below the 128 characters the ontology allows, leaving room for "new:".
NAME_MAX = 100
# Shorter names (one character after normalizing) occur everywhere: they do not count as naming
# a type in a relation's evidence.
MIN_NAME = 2
# Prompt sizes (spec 004, section 6): existing types per types-stage call, types per
# relations-stage call, and types judged per resolve call.
TYPES_CONTEXT_MAX = 60
RELATIONS_CATALOG_MAX = 120
RESOLVE_BATCH = 40
# Names of a candidate's relations and properties shown to the resolve call.
RESOLVE_MEMBERS = 5
REASON_MAX = 200
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
    parent_id: UUID | None = None


@dataclass(frozen=True)
class PendingType:
    """A new object type of another open change set: a candidate, never a reference."""

    item_id: UUID
    change_set_id: UUID
    change_set_title: str
    label_zh: str
    label_en: str | None = None
    synonyms: tuple[str, ...] = ()
    definition_zh: str | None = None
    parent_label: str | None = None
    # Names of the relations and properties its change set hangs on it.
    members: tuple[str, ...] = ()


@dataclass
class ProposedEvidence:
    chunk_id: UUID
    quote: str
    char_start: int | None
    char_end: int | None


@dataclass
class ProposedMatch:
    """What a new object type was aligned with (spec 004, 4.3): one of the three targets."""

    kind: Literal["same", "possible"]
    element_id: UUID | None = None  # an element of the working version
    item_id: UUID | None = None  # a create item of another open change set
    temp_ref: str | None = None  # a new type of this change set
    reason: str | None = None


@dataclass
class Proposal:
    """One change item. `fields` uses the API's camelCase element field names (api-shapes)."""

    op: Literal["create", "update", "restore"]
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
    match: ProposedMatch | None = None


@dataclass(frozen=True)
class ExtractionModels:
    standard: str
    reasoning: str


# What a candidate is: ("element", id), ("item", pending item id) or ("run", index of an
# earlier type of the types stage's output).
CandidateKey = tuple[Literal["element", "item", "run"], str]


@dataclass(frozen=True)
class Candidate:
    key: CandidateKey
    score: Score
    # Guardrail G3: only the types stage's use of the type's id made it a candidate.
    nominated: bool = False


@dataclass(frozen=True)
class ResolveRequest:
    """A new type to judge: its position in the types stage's output, and its candidates."""

    index: int
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    candidate: CandidateKey | None = None
    reason: str | None = None


Decisions = Mapping[int, Sequence[Decision]]


@dataclass(frozen=True)
class JudgedPair:
    """A pair sent to the resolve call and the model's verdict on it (None: no answer)."""

    names: tuple[str, ...]
    candidate_names: tuple[str, ...]
    score: float
    verdict: Verdict | None


@dataclass
class RunStats:
    """What the last run decided, for the evaluation."""

    requests: list[ResolveRequest] = field(default_factory=list)
    decisions: dict[int, list[Decision]] = field(default_factory=dict)
    pairs: list[JudgedPair] = field(default_factory=list)
    # Existing types left out of a stage's prompts by the size limits, per stage.
    trimmed: Counter[str] = field(default_factory=Counter)


def judged_pairs(
    types: Sequence[EntityTypeOut],
    requests: Sequence[ResolveRequest],
    decisions: Decisions,
    known: Sequence[KnownElement],
    pending: Sequence[PendingType],
) -> list[JudgedPair]:
    elements = {str(element.id): element for element in known}
    items = {str(item.item_id): item for item in pending}

    def names_of(key: CandidateKey) -> tuple[str, ...]:
        kind, value = key
        if kind == "element":
            e = elements[value]
            return (e.label_zh, e.label_en or "", *e.synonyms)
        if kind == "item":
            p = items[value]
            return (p.label_zh, p.label_en or "", *p.synonyms)
        t = types[int(value)]
        return (t.label_zh, t.label_en or "", *t.synonyms)

    pairs: list[JudgedPair] = []
    for request in requests:
        item = types[request.index]
        rows = decisions.get(request.index, [])
        for candidate in request.candidates:
            verdict = next((r.verdict for r in rows if r.candidate == candidate.key), None)
            if verdict is None and any(r.verdict == "different" for r in rows):
                verdict = "different"
            pairs.append(
                JudgedPair(
                    (item.label_zh, item.label_en or "", *item.synonyms),
                    names_of(candidate.key),
                    candidate.score.value,
                    verdict,
                )
            )
    return pairs


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
    def __init__(
        self, gateway: ModelGateway, models: ExtractionModels, threshold: float = THRESHOLD
    ) -> None:
        self.gateway = gateway
        self.models = models
        self.threshold = threshold
        self.last = RunStats()

    async def run(
        self,
        *,
        document_id: UUID,
        title: str,
        chunks: Sequence[ChunkText],
        known: Sequence[KnownElement],
        progress: ProgressFn,
        deleted: Sequence[KnownElement] = (),
        pending: Sequence[PendingType] = (),
    ) -> list[Proposal]:
        """`deleted` and `pending` are not shown to the types stage; see `build_proposals`."""
        self.last = RunStats()
        groups = batches(chunks)
        terms = await self._terms(document_id, title, groups, progress)
        types = await self._types(document_id, title, terms, known, progress)
        requests = resolve_requests(
            known, types, deleted=deleted, pending=pending, threshold=self.threshold
        )
        decisions = await self._resolve(document_id, title, types, requests, known, pending)
        self.last.requests, self.last.decisions = requests, decisions
        self.last.pairs = judged_pairs(types, requests, decisions, known, pending)
        relations = await self._relations(document_id, title, groups, types, known, progress)
        await progress("changeset", 0, 1)
        proposals = build_proposals(
            chunks,
            known,
            types,
            relations,
            deleted=deleted,
            pending=pending,
            decisions=decisions,
            threshold=self.threshold,
        )
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
            context = types_context(known, [term.name for term in group], self.threshold)
            self.last.trimmed["extract.types"] += len(existing) - len(context)
            result = await self.gateway.structured(
                purpose="extract.types",
                model=self.models.reasoning,
                instructions=TYPES_INSTRUCTIONS,
                text=f"Document: {title}\n\n" + "\n".join(_types_lines(context, found, group)),
                schema=TypesOut,
                document_id=document_id,
            )
            found = merge_types(found, result.entity_types)
            await progress("types", index, len(groups))
        return found

    async def _resolve(
        self,
        document_id: UUID,
        title: str,
        types: Sequence[EntityTypeOut],
        requests: Sequence[ResolveRequest],
        known: Sequence[KnownElement],
        pending: Sequence[PendingType],
    ) -> dict[int, list[Decision]]:
        """One call per `RESOLVE_BATCH` types to judge; none when there is nothing to judge."""
        decisions: dict[int, list[Decision]] = {}
        for start in range(0, len(requests), RESOLVE_BATCH):
            batch = requests[start : start + RESOLVE_BATCH]
            text, aliases = render_resolve(title, types, batch, known, pending)
            result = await self.gateway.structured(
                purpose="extract.resolve",
                model=self.models.standard,
                instructions=RESOLVE_INSTRUCTIONS,
                text=text,
                schema=ResolveOut,
                document_id=document_id,
            )
            for row in result.decisions:
                found = aliases.types.get(row.type.strip())
                if found is None:
                    continue  # G2: a type that was not asked about
                candidate = aliases.candidates.get((found, (row.candidate or "").strip()))
                decisions.setdefault(found, []).append(
                    Decision(row.verdict, candidate, row.reason.strip()[:REASON_MAX] or None)
                )
        return decisions

    async def _relations(
        self,
        document_id: UUID,
        title: str,
        groups: list[list[ChunkText]],
        types: list[EntityTypeOut],
        known: Sequence[KnownElement],
        progress: ProgressFn,
    ) -> RelationsOut:
        catalog = relations_catalog(types, known)
        merged = RelationsOut(relations=[], properties=[])
        await progress("relations", 0, len(groups))
        for index, group in enumerate(groups, start=1):
            lines = catalog_for(catalog, group)
            self.last.trimmed["extract.relations"] += len(catalog) - len(lines)
            header = "Entity types (ref | label | synonyms | definition):\n" + "\n".join(
                line[0] for line in lines
            )
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


# ---------------------------------------------------------------------------- prompt sizes


def types_context(
    known: Sequence[KnownElement], terms: Sequence[str], threshold: float = THRESHOLD
) -> list[KnownElement]:
    """The existing types a types-stage call shows: all of them up to `TYPES_CONTEXT_MAX`.

    Beyond that (spec 004, section 6): those the batch's terms shortlist, best first, then
    their parents, children and the types related to them, until the limit is reached.
    """
    existing = [element for element in known if element.kind == "entity_type"]
    if len(existing) <= TYPES_CONTEXT_MAX:
        return existing
    term_names = [Names.of(name, None, ()) for name in terms]
    best: list[tuple[float, int]] = []
    for position, element in enumerate(existing):
        names = _known_names(element)
        value = max((score(term, names, threshold).value for term in term_names), default=0.0)
        if value >= threshold:
            best.append((-value, position))
    chosen: dict[UUID, KnownElement] = {}
    for _, position in sorted(best):
        chosen.setdefault(existing[position].id, existing[position])
    by_id = {element.id: element for element in existing}
    for element in list(chosen.values()):
        if len(chosen) >= TYPES_CONTEXT_MAX:
            break
        neighbours = [by_id.get(element.parent_id) if element.parent_id else None]
        neighbours += [other for other in existing if other.parent_id == element.id]
        for link in known:
            if link.kind == "relation_type" and element.id in (link.domain_id, link.range_id):
                other_id = link.range_id if link.domain_id == element.id else link.domain_id
                neighbours.append(by_id.get(other_id) if other_id else None)
        for other in neighbours:
            if other is not None:
                chosen.setdefault(other.id, other)
    return list(chosen.values())[:TYPES_CONTEXT_MAX]


# One line of the relations stage's catalog of types, with the normalized names it goes by and
# whether the type belongs to this document.
CatalogLine = tuple[str, frozenset[str], bool]


def relations_catalog(
    types: Sequence[EntityTypeOut], known: Sequence[KnownElement]
) -> list[CatalogLine]:
    lines: list[CatalogLine] = [
        (
            f"- {t.ref} | {t.label_zh} | {', '.join(t.synonyms)} | {t.definition_zh or ''}",
            frozenset(_mention_keys([t.label_zh, t.label_en or "", *t.synonyms])),
            True,
        )
        for t in types
    ]
    refs = {t.ref for t in types}
    lines += [
        (
            f"- {element.id} | {element.label_zh} | {', '.join(element.synonyms)} | "
            f"{element.definition_zh or ''}",
            frozenset(_mention_keys([element.label_zh, element.label_en or "", *element.synonyms])),
            False,
        )
        for element in known
        if element.kind == "entity_type" and str(element.id) not in refs
    ]
    return lines


def catalog_for(catalog: Sequence[CatalogLine], group: Sequence[ChunkText]) -> list[CatalogLine]:
    """The types a relations-stage call shows: the whole catalog up to `RELATIONS_CATALOG_MAX`.

    Beyond that (spec 004, section 6): the types named in the batch's text or headings first,
    then this document's other types. An existing type the batch does not name cannot pass the
    direct-evidence check, so leaving it out loses no relation.
    """
    if len(catalog) <= RELATIONS_CATALOG_MAX:
        return list(catalog)
    text = normalize(" ".join(f"{chunk.heading or ''} {chunk.text}" for chunk in group))
    named = [line for line in catalog if any(name in text for name in line[1])]
    rest = [line for line in catalog if line[2] and line not in named]
    return (named + rest)[:RELATIONS_CATALOG_MAX]


def _mention_keys(names: Iterable[str]) -> set[str]:
    """Normalized names long enough to count as a mention of a type."""
    return {key for key in (normalize(name) for name in names) if len(key) >= MIN_NAME}


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
    unknown, so the type is added and `build_proposals` resolves the shared ref. Nor is a ref
    in the form of an id (a UUID): `build_proposals` checks each type given an existing type's
    id against that type's main name.
    """
    merged = list(found)
    earlier = {item.ref: index for index, item in enumerate(found)}
    shared = {ref for ref, count in Counter(item.ref for item in found).items() if count > 1}
    for item in batch:
        index = earlier.get(item.ref)
        if index is None or item.ref in shared or _as_uuid(item.ref) is not None:
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


# ---------------------------------------------------------------------------- entity resolution


@dataclass(frozen=True)
class _Fate:
    """What the deterministic part of the alignment makes of one type of the types stage.

    existing / restore: the type is that element (G1, or the model reused its id and the main
    names agree). run: the same main name as the earlier type at `root`. new: a new type, to be
    judged against its candidates unless a pending item has its main name (`pending`).
    """

    kind: Literal["existing", "restore", "run", "new"]
    element: KnownElement | None = None
    root: int = -1
    claimed: KnownElement | None = None  # an existing id given to a type of another main name
    pending: PendingType | None = None


def _known_names(element: KnownElement) -> Names:
    return Names.of(element.label_zh, element.label_en, element.synonyms)


def _type_names(item: EntityTypeOut) -> Names:
    return Names.of(item.label_zh, item.label_en, item.synonyms)


def _same(item: EntityTypeOut, label_zh: str | None, label_en: str | None) -> bool:
    return same_main_name(item.label_zh, item.label_en, label_zh, label_en)


def _fates(
    known: Sequence[KnownElement],
    types: Sequence[EntityTypeOut],
    deleted: Sequence[KnownElement],
    pending: Sequence[PendingType],
) -> list[_Fate]:
    existing = [element for element in known if element.kind == "entity_type"]
    by_id = {str(element.id): element for element in existing}
    deleted_types = [element for element in deleted if element.kind == "entity_type"]
    fates: list[_Fate] = []
    for item in types:
        claimed = by_id.get(item.ref)
        if claimed is not None and _same(item, claimed.label_zh, claimed.label_en):
            fates.append(_Fate("existing", claimed))
            continue
        same = next((e for e in existing if _same(item, e.label_zh, e.label_en)), None)
        if same is not None:
            fates.append(_Fate("existing", same))
            continue
        restored = next((e for e in deleted_types if _same(item, e.label_zh, e.label_en)), None)
        if restored is not None:
            fates.append(_Fate("restore", restored))
            continue
        root = next(
            (
                index
                for index, fate in enumerate(fates)
                if fate.kind == "new" and _same(item, types[index].label_zh, types[index].label_en)
            ),
            -1,
        )
        if root >= 0:
            fates.append(_Fate("run", root=root))
            continue
        named = next((p for p in pending if _same(item, p.label_zh, p.label_en)), None)
        fates.append(_Fate("new", claimed=claimed, pending=named))
    return fates


def resolve_requests(
    known: Sequence[KnownElement],
    types: Sequence[EntityTypeOut],
    *,
    deleted: Sequence[KnownElement] = (),
    pending: Sequence[PendingType] = (),
    threshold: float = THRESHOLD,
) -> list[ResolveRequest]:
    """The new types that have candidates, with their candidates (spec 004, 4.1 and 4.2).

    Candidates are the active object types, the pending items' object types and the earlier
    new types of this run. A type whose main name is a pending item's (G1) is not judged: the
    merge takes care of it. A type given an existing type's id that is not a candidate by name
    is judged against that type as well (G3), at the expense of its weakest candidate.
    """
    fates = _fates(known, types, deleted, pending)
    pool: list[tuple[CandidateKey, Names]] = [
        (("element", str(element.id)), _known_names(element))
        for element in known
        if element.kind == "entity_type"
    ]
    pool += [
        (("item", str(item.item_id)), Names.of(item.label_zh, item.label_en, item.synonyms))
        for item in pending
    ]
    # Names of each earlier new type, with those of the types that joined it by main name.
    run_names: dict[int, list[str]] = {}
    for index, fate in enumerate(fates):
        root = index if fate.kind == "new" else fate.root if fate.kind == "run" else -1
        if root >= 0:
            joined = types[index]
            run_names.setdefault(root, []).extend([joined.label_en or "", *joined.synonyms])
    requests: list[ResolveRequest] = []
    for index, (item, fate) in enumerate(zip(types, fates, strict=True)):
        if fate.kind != "new" or fate.pending is not None:
            continue
        earlier = [
            (("run", str(j)), Names.of(types[j].label_zh, types[j].label_en, run_names[j]))
            for j in run_names
            if j < index
        ]
        names = _type_names(item)
        found = [
            Candidate(key, value)
            for key, value in shortlist(names, [*pool, *earlier], threshold=threshold, limit=99)
        ]
        nominated = fate.claimed
        if nominated is not None:
            key: CandidateKey = ("element", str(nominated.id))
            if not any(candidate.key == key for candidate in found[:PER_TYPE]):
                found = [c for c in found if c.key != key][: PER_TYPE - 1]
                found.append(Candidate(key, score(names, _known_names(nominated), threshold), True))
        found = found[:PER_TYPE]
        if found:
            requests.append(ResolveRequest(index, tuple(found)))
    return requests


@dataclass(frozen=True)
class _Aliases:
    types: dict[str, int]
    candidates: dict[tuple[int, str], CandidateKey]


def render_resolve(
    title: str,
    types: Sequence[EntityTypeOut],
    requests: Sequence[ResolveRequest],
    known: Sequence[KnownElement],
    pending: Sequence[PendingType],
) -> tuple[str, _Aliases]:
    """The input of a resolve call; short aliases (T1, C1) stand for types and candidates."""
    elements = {str(element.id): element for element in known}
    items = {str(item.item_id): item for item in pending}
    by_ref = {item.ref: item for item in types}
    members: dict[UUID, list[str]] = {}
    for element in known:
        if element.kind != "entity_type" and element.domain_id is not None:
            members.setdefault(element.domain_id, []).append(element.label_zh)

    def label_of(ref: str | None) -> str:
        if ref is None:
            return ""
        element = elements.get(ref)
        if element is not None:
            return element.label_zh
        item = by_ref.get(ref)
        return item.label_zh if item is not None else ""

    def line(
        alias: str,
        label: str,
        synonyms: Iterable[str],
        definition: str | None,
        parent: str = "",
        related: Sequence[str] = (),
    ) -> str:
        parts = [alias, label, ", ".join(synonyms), definition or "", parent]
        parts.append(", ".join(related[:RESOLVE_MEMBERS]))
        return " | ".join(parts)

    aliases = _Aliases({}, {})
    lines = [
        f"Document: {title}",
        "",
        "Each type to judge (id | label | synonyms | definition | parent) is followed by its",
        "candidates (id | label | synonyms | definition | parent | relations and attributes).",
    ]
    counter = 0
    for number, request in enumerate(requests, start=1):
        item = types[request.index]
        alias = f"T{number}"
        aliases.types[alias] = request.index
        lines.append("")
        lines.append(
            line(alias, item.label_zh, item.synonyms, item.definition_zh, label_of(item.parent))
        )
        for candidate in request.candidates:
            counter += 1
            candidate_alias = f"C{counter}"
            aliases.candidates[(request.index, candidate_alias)] = candidate.key
            kind, value = candidate.key
            if kind == "element":
                element = elements[value]
                parent = label_of(str(element.parent_id)) if element.parent_id else ""
                text = line(
                    candidate_alias,
                    element.label_zh,
                    element.synonyms,
                    element.definition_zh,
                    parent,
                    members.get(element.id, []),
                )
            elif kind == "item":
                other = items[value]
                text = line(
                    candidate_alias,
                    other.label_zh,
                    other.synonyms,
                    other.definition_zh,
                    other.parent_label or "",
                    other.members,
                )
            else:
                earlier = types[int(value)]
                text = line(
                    candidate_alias,
                    earlier.label_zh,
                    earlier.synonyms,
                    earlier.definition_zh,
                    label_of(earlier.parent),
                )
            lines.append(f"  {text}")
    return "\n".join(lines), aliases


@dataclass(frozen=True)
class _Conclusion:
    verdict: Verdict
    candidate: Candidate | None
    reason: str | None


def _conclude(
    request: ResolveRequest,
    given: Sequence[Decision] | None,
    related: Callable[[CandidateKey], bool],
) -> _Conclusion:
    """The guardrails G2 and G4 to G7 applied to the model's answer for one type."""
    by_key = {candidate.key: candidate for candidate in request.candidates}
    rows = [row for row in given or () if row.candidate is None or row.candidate in by_key]
    best = max(request.candidates, key=lambda candidate: candidate.score.value)

    def strongest(keys: Iterable[CandidateKey]) -> Candidate:
        return max((by_key[key] for key in keys), key=lambda c: c.score.value)

    sames = list(dict.fromkeys(r.candidate for r in rows if r.verdict == "same" and r.candidate))
    unsures = [r.candidate for r in rows if r.verdict == "unsure" and r.candidate]
    reason = next((r.reason for r in rows if r.verdict != "different"), None)
    if len(sames) == 1:
        candidate = by_key[sames[0]]
        reason = next(r.reason for r in rows if r.candidate == sames[0] and r.verdict == "same")
        if candidate.score.one_character or candidate.nominated or related(candidate.key):
            return _Conclusion("unsure", candidate, reason)  # G3, G4, G7
        return _Conclusion("same", candidate, reason)
    if sames:
        return _Conclusion("unsure", strongest(sames), reason)  # G6
    if unsures:
        return _Conclusion("unsure", strongest(unsures), reason)
    if any(row.verdict == "different" for row in rows):
        return _Conclusion("different", None, None)
    return _Conclusion("unsure", best, None)  # G5: no usable answer


# ---------------------------------------------------------------------------- proposals


class _Builder:
    def __init__(
        self,
        chunks: Sequence[ChunkText],
        known: Sequence[KnownElement],
        deleted: Sequence[KnownElement] = (),
    ) -> None:
        self.by_seq = {chunk.seq: chunk for chunk in chunks}
        self.by_id = {chunk.id: chunk for chunk in chunks}
        self.chunks = list(chunks)
        self.known = list(known)
        self.known_ids = {str(element.id): element for element in known}
        self.deleted_types = [element for element in deleted if element.kind == "entity_type"]
        # A deleted element keeps its local name: a merge would find it taken.
        self.used_names = {element.local_name for element in (*known, *deleted)}
        self.proposals: list[Proposal] = []
        # The one update or restore per existing element; see `_maybe_update`.
        self.updates: dict[UUID, Proposal] = {}
        self._units: dict[UUID, list[tuple[int, int]]] = {}

    def units(self, chunk: ChunkText) -> list[tuple[int, int]]:
        if chunk.id not in self._units:
            self._units[chunk.id] = split_sentences(chunk.text)
        return self._units[chunk.id]

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
        """Whether the sentences a located quote touches name both ends (by any of their names).

        A sentence (`sentences.split_sentences`: a sentence, list item or table row, however
        the file broke its lines) is the unit of direct evidence. Only the longest mentions
        count, and the two ends need mentions that do not overlap: a name inside a longer name
        (钢种 in 钢种成分要求) is not a mention of its own, and a type related to itself has to
        be named twice.
        """
        for item in evidence:
            chunk = self.by_id.get(item.chunk_id)
            if chunk is None or item.char_start is None or item.char_end is None:
                continue
            span = covering(self.units(chunk), item.char_start, item.char_end)
            if span is None:
                continue
            line = normalize(chunk.text[span[0] : span[1]])
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
        self, kind: Kind, label: str, domain: UUID, range_: UUID | None = None
    ) -> KnownElement | None:
        """The existing relation or property of these ends and this main name (spec 004, 5.3).

        A relation of another range is another link (炉次 使用 钢包, 炉次 使用 转炉).
        """
        for element in self.known:
            if element.kind != kind or element.domain_id != domain:
                continue
            if kind == "relation_type" and element.range_id != range_:
                continue
            if same_main_name(label, None, element.label_zh, element.label_en):
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
    *,
    deleted: Sequence[KnownElement] = (),
    pending: Sequence[PendingType] = (),
    decisions: Decisions | None = None,
    threshold: float = THRESHOLD,
) -> list[Proposal]:
    """Change items from the model's output, aligned with the existing elements `known`.

    `deleted` are elements of the ontology that were deleted. A new type with the main name of
    a deleted type restores it instead (spec 004, 5.6), and their local names stay taken.
    `pending` are the object types of other open change sets, and `decisions` the resolve
    call's answers per type (keyed by position in `types`); a candidate without an answer is
    a possible duplicate (G5).
    """
    builder = _Builder(chunks, known, deleted)
    fates = _fates(known, types, deleted, pending)
    requests = {
        request.index: request
        for request in resolve_requests(
            known, types, deleted=deleted, pending=pending, threshold=threshold
        )
    }
    # Each type the model gave -> the type it is in the change set: an existing id or our
    # temp_ref. The model sometimes gives one ref to two types; see `resolve`.
    became: list[tuple[EntityTypeOut, str]] = []
    new_types: list[tuple[EntityTypeOut, Proposal]] = []
    proposal_of: dict[int, Proposal] = {}  # index of a type -> the new type it is part of
    mistaken: set[str] = set()  # existing ids given to types of another main name

    def related(item: EntityTypeOut) -> Callable[[CandidateKey], bool]:
        """G7: whether a candidate is the type's parent or child."""

        def check(key: CandidateKey) -> bool:
            kind, value = key
            if kind == "element":
                return item.parent == value
            if kind == "run":
                other = types[int(value)]
                return item.parent == other.ref or other.parent == item.ref
            return False

        return check

    for index, (item, fate) in enumerate(zip(types, fates, strict=True)):
        if fate.element is not None:
            became.append((item, str(fate.element.id)))
            op: Literal["update", "restore"] = "update" if fate.kind == "existing" else "restore"
            _maybe_update(builder, fate.element, item, item.quotes, op=op)
            continue
        if fate.kind == "run":
            _join(builder, proposal_of[fate.root], item)
            proposal_of[index] = proposal_of[fate.root]
            became.append((item, proposal_of[index].temp_ref or ""))
            continue
        if fate.claimed is not None:
            mistaken.add(item.ref)
        request = requests.get(index)
        conclusion = (
            _conclude(
                request, decisions.get(index) if decisions is not None else None, related(item)
            )
            if request is not None
            else None
        )
        target = conclusion.candidate if conclusion is not None else None
        if conclusion is not None and target is not None and conclusion.verdict == "same":
            kind, value = target.key
            if kind == "run":
                # The same concept as an earlier type of this document: one item, as for G1.
                joined = proposal_of[int(value)]
                _join(builder, joined, item)
                proposal_of[index] = joined
                became.append((item, joined.temp_ref or ""))
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
        if conclusion is not None and target is not None and conclusion.verdict != "different":
            kind, value = target.key
            match = ProposedMatch(
                "same" if conclusion.verdict == "same" else "possible", reason=conclusion.reason
            )
            if kind == "element":
                match.element_id = UUID(value)
            elif kind == "item":
                match.item_id = UUID(value)
            else:
                match.temp_ref = proposal_of[int(value)].temp_ref
            proposal.match = match
            if conclusion.verdict == "unsure":
                proposal.flags.append("possible_duplicate")
        if fate.pending is not None:
            # G1 with a pending item: recorded, so that the merge follows that item wherever it
            # goes, also into an element of another main name (spec 004, 5.3).
            proposal.match = ProposedMatch("same", item_id=fate.pending.item_id)
        proposal_of[index] = proposal
        new_types.append((item, proposal))
        builder.add(proposal, item.quotes, item.confidence)

    targets: dict[str, set[str]] = {}
    for item, target_ref in became:
        targets.setdefault(item.ref, set()).add(target_ref)

    def resolve(ref: str) -> str | None:
        """The type a ref of the model stands for, or None.

        A ref the model gave to types that stayed apart stands for none of them: which one a
        parent, relation or property meant is unknown, so the reference is dropped, while the
        types themselves are kept.
        """
        found = targets.get(ref)
        if found is None:
            return builder.known_type(ref)
        if len(found) > 1:
            return None
        return next(iter(found))

    # Parents are resolved after all types are known: a type of this run or an existing one.
    # Unknown, ambiguous or self parents are dropped. So is a mistaken id: the types stage
    # listed it with the existing type's names, while the type given it means another thing.
    for item, proposal in new_types:
        parent = resolve(item.parent) if item.parent and item.parent not in mistaken else None
        if parent and parent != proposal.temp_ref:
            proposal.fields["parentRef"] = parent

    # Every name a type goes by in this run, to check that a relation's evidence names its ends.
    # A model type's names count only for the type it became, whatever ref it shares.
    names_of: dict[str, set[str]] = {
        str(element.id): _mention_keys(
            [element.label_zh, element.label_en or "", *element.synonyms]
        )
        for element in (*known, *builder.deleted_types)
        if element.kind == "entity_type"
    }
    for item, target_ref in became:
        names_of.setdefault(target_ref, set()).update(
            _mention_keys([item.label_zh, item.label_en or "", *item.synonyms])
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
            continue  # no direct evidence: no quote's sentence names both types
        seen_relations.add(key)
        domain_uuid, range_uuid = _as_uuid(domain), _as_uuid(range_)
        if (
            domain_uuid
            and range_uuid
            and builder.match_known("relation_type", relation.label_zh, domain_uuid, range_uuid)
        ):
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
        if domain_uuid and builder.match_known("property", prop.label_zh, domain_uuid):
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


# A candidate that appeared after the identification started: the key to record and its names.
LateCandidate = tuple[ProposedMatch, Names, str | None, str | None]


def mark_late_candidates(
    proposals: Sequence[Proposal],
    late: Sequence[LateCandidate],
    threshold: float = THRESHOLD,
) -> None:
    """The write-time recheck (spec 004, 7.3): new types that a type made or proposed while the
    document was being identified shortlists are possible duplicates of it, without a model.

    `late` holds, per candidate, the match to record and the candidate's names and labels.
    Equal main names are left to the merge (G1); a type already aligned keeps its alignment.
    """
    for proposal in proposals:
        if proposal.op != "create" or proposal.kind != "entity_type" or proposal.match:
            continue
        label_zh, label_en = proposal.fields["labelZh"], proposal.fields.get("labelEn")
        names = Names.of(label_zh, label_en, (s["text"] for s in proposal.fields["synonyms"]))
        best: tuple[float, ProposedMatch] | None = None
        for match, other, other_zh, other_en in late:
            if same_main_name(label_zh, label_en, other_zh, other_en):
                continue
            value = score(names, other, threshold).value
            if value >= threshold and (best is None or value > best[0]):
                best = (value, match)
        if best is not None:
            found = best[1]
            proposal.match = ProposedMatch(
                "possible", element_id=found.element_id, item_id=found.item_id
            )
            if "possible_duplicate" not in proposal.flags:
                proposal.flags.append("possible_duplicate")


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


def _join(builder: _Builder, proposal: Proposal, item: EntityTypeOut) -> None:
    """Another type of this document is the same new type: its names and evidence join it."""
    fields = proposal.fields
    names = {normalize(fields["labelZh"]), normalize(fields.get("labelEn") or "")}
    names |= {normalize(s["text"]) for s in fields["synonyms"]}
    fields["synonyms"] += [
        s
        for s in _synonyms([item.label_zh, item.label_en or "", *item.synonyms], fields["labelZh"])
        if normalize(s["text"]) not in names
    ]
    evidence, _ = builder.ground(item.quotes)
    proposal.evidence += [e for e in evidence if e.char_start is not None]


def _maybe_update(
    builder: _Builder,
    element: KnownElement,
    item: EntityTypeOut,
    quotes: Sequence[Quote],
    op: Literal["update", "restore"] = "update",
) -> None:
    """Propose adding synonyms or a missing definition to an existing type; nothing otherwise.

    The model's Chinese label is a name the source uses for the type, so it is added as a
    synonym when it is none of the type's names yet. Several model types can land on the same
    existing type. They become one update: two updates of one element in a change set would
    make the second look stale at merge time. A deleted type is restored with the same
    additions, and restored even without any.
    """
    previous = builder.updates.get(element.id)
    known = {normalize(s) for s in (*element.synonyms, element.label_zh, element.label_en or "")}
    if previous is not None:
        known |= {normalize(s["text"]) for s in previous.fields.get("synonyms", [])}
    added = [
        s
        for s in _synonyms([item.label_zh, *item.synonyms], element.label_zh)
        if normalize(s["text"]) not in known
    ]
    fields: dict[str, Any] = {}
    if added:
        fields["synonyms"] = added
    if (
        not element.definition_zh
        and item.definition_zh
        and (previous is None or "definitionZh" not in previous.fields)
    ):
        fields["definitionZh"] = item.definition_zh
    if previous is not None:
        if fields:
            if "synonyms" in fields:
                previous.fields.setdefault("synonyms", []).extend(fields.pop("synonyms"))
            previous.fields.update(fields)
            evidence, _ = builder.ground(quotes)
            previous.evidence.extend(evidence)
        return
    if not fields and op == "update":
        return
    proposal = Proposal(
        op=op,
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
