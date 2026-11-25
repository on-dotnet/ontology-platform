"""Connects the extraction to document processing: chunks in, an open change set out.

The worker registers `make_extractor` and `make_transcriber` with the documents module. The
extractor reads the document's chunks and the ontology's elements, runs the staged extraction
and writes the proposals as one change set. That is the only thing AI writes (AGENTS.md red
line): nothing reaches the ontology until a reviewer merges the change set.
"""

import base64
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast
from uuid import UUID

from annotated_types import MaxLen
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.candidates import Names
from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    Kind,
    KnownElement,
    LateCandidate,
    PendingType,
    Proposal,
    ProposedMatch,
    mark_late_candidates,
)
from ontology_platform.modules.ai.gateway import AiError, InputFile, ModelGateway
from ontology_platform.modules.ai.prompts import TRANSCRIBE_INSTRUCTIONS, TranscriptOut
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.documents.parsers import ParsedPage, ScanPart
from ontology_platform.modules.jobs.runner import LeaseCheck, RetryableJobError
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.schemas import (
    ElementCopy,
    ElementFields,
    EvidenceIn,
    ProposedItem,
)
from ontology_platform.modules.ontology.schemas import ProposedMatch as ProposedMatchIn

TITLE = "识别：{filename}"
QUOTE_MAX = 500
SYNONYMS_MAX = 100
SYNONYM_MAX = 200


def job_error(exc: AiError) -> Exception:
    """Transient model failures go back to the queue; the rest fail the document with the code."""
    if exc.retryable:
        return RetryableJobError(exc.code)
    return AppError(422, exc.code, str(exc))


def known_element(element: ElementCopy) -> KnownElement:
    return KnownElement(
        id=element.id,
        kind=cast(Kind, element.kind),  # alignment candidates are only of these kinds
        # Alignment elements are never axioms, so they have a local name; imported ones may
        # lack a Chinese label and are matched by the name the platform shows instead.
        local_name=element.local_name or "",
        label_zh=element.label_zh or element.label_en or element.local_name or "",
        label_en=element.label_en,
        synonyms=tuple(item.text for item in element.synonyms),
        definition_zh=element.definition_zh,
        domain_id=element.domain_id,
        range_id=element.range_id,
        revision=element.revision,
        parent_id=element.parent_id,
    )


def pending_types(
    candidates: Sequence[ontology.PendingCandidate], known: Sequence[KnownElement]
) -> list[PendingType]:
    """The object types other open change sets propose, as the resolve call shows them: with
    their parent's name and the names of what their change set hangs on them."""
    labels = {str(element.id): element.label_zh for element in known}
    for item in candidates:
        if item.kind == "entity_type" and item.temp_ref:
            labels[f"{item.change_set_id}/{item.temp_ref}"] = _label(item.fields)
    members: dict[str, list[str]] = {}
    for item in candidates:
        domain = item.fields.domain_ref
        if item.kind != "entity_type" and domain is not None:
            members.setdefault(f"{item.change_set_id}/{domain}", []).append(_label(item.fields))
    out: list[PendingType] = []
    for item in candidates:
        if item.kind != "entity_type":
            continue
        parent = item.fields.parent_ref
        own = f"{item.change_set_id}/{item.temp_ref}"
        out.append(
            PendingType(
                item_id=item.item_id,
                change_set_id=item.change_set_id,
                change_set_title=item.change_set_title,
                label_zh=_label(item.fields),
                label_en=item.fields.label_en,
                synonyms=tuple(synonym.text for synonym in item.fields.synonyms or []),
                definition_zh=item.fields.definition_zh,
                parent_label=(
                    labels.get(parent) or labels.get(f"{item.change_set_id}/{parent}")
                    if parent
                    else None
                ),
                members=tuple(members.get(own, [])),
            )
        )
    return out


def _label(fields: ElementFields) -> str:
    return fields.label_zh or fields.label_en or fields.local_name or ""


def late_candidates(
    before: ontology.AlignmentCandidates, now: ontology.AlignmentCandidates
) -> list[LateCandidate]:
    """Object types that appeared while the document was being identified (spec 004, 7.3)."""
    seen_elements = {element.id for element in before.active}
    seen_items = {item.item_id for item in before.pending}
    late: list[LateCandidate] = [
        (
            ProposedMatch("possible", element_id=element.id),
            Names.of(element.label_zh, element.label_en, (s.text for s in element.synonyms)),
            element.label_zh,
            element.label_en,
        )
        for element in now.active
        if element.kind == "entity_type" and element.id not in seen_elements
    ]
    late += [
        (
            ProposedMatch("possible", item_id=item.item_id),
            Names.of(
                item.fields.label_zh,
                item.fields.label_en,
                (s.text for s in item.fields.synonyms or []),
            ),
            item.fields.label_zh,
            item.fields.label_en,
        )
        for item in now.pending
        if item.kind == "entity_type" and item.item_id not in seen_items
    ]
    return late


def _limits() -> dict[str, int]:
    """Maximum lengths of the string fields, read from ElementFields so they cannot drift."""
    limits: dict[str, int] = {}
    for info in ElementFields.model_fields.values():
        for rule in info.metadata:
            if isinstance(rule, MaxLen) and info.alias:
                limits[info.alias] = rule.max_length
    return limits


_LIMITS = _limits()


def _clip(fields: dict[str, Any]) -> dict[str, Any]:
    """Model output can exceed the column limits; clip instead of failing the whole document."""
    clipped = dict(fields)
    for key, limit in _LIMITS.items():
        value = clipped.get(key)
        if isinstance(value, str) and len(value) > limit:
            clipped[key] = value[:limit]
    if isinstance(clipped.get("synonyms"), list):
        clipped["synonyms"] = [
            item for item in clipped["synonyms"] if len(item["text"]) <= SYNONYM_MAX
        ][:SYNONYMS_MAX]
    return clipped


def _quote(text: str) -> str:
    return text if len(text) <= QUOTE_MAX else text[: QUOTE_MAX - 1] + "…"


def to_item(proposal: Proposal, document_id: UUID) -> ProposedItem:
    return ProposedItem(
        op=proposal.op,
        kind=proposal.kind,
        target_element_id=proposal.target_element_id,
        target_revision=proposal.target_revision,
        temp_ref=proposal.temp_ref,
        proposed=ElementFields.model_validate(_clip(proposal.fields)),
        confidence=proposal.confidence,
        rationale=proposal.rationale,
        flags=list(proposal.flags),
        match=(
            ProposedMatchIn(
                kind=proposal.match.kind,
                element_id=proposal.match.element_id,
                item_id=proposal.match.item_id,
                temp_ref=proposal.match.temp_ref,
                reason=proposal.match.reason,
            )
            if proposal.match is not None
            else None
        ),
        evidence=[
            EvidenceIn(
                document_id=document_id,
                chunk_id=evidence.chunk_id,
                quote=_quote(evidence.quote),
                char_start=evidence.char_start,
                char_end=evidence.char_end,
            )
            for evidence in proposal.evidence
        ],
    )


def make_extractor(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    models: ExtractionModels,
) -> Callable[[UUID, LeaseCheck], Awaitable[UUID | None]]:
    extractor = Extractor(gateway, models)

    async def extract(document_id: UUID, check_lease: LeaseCheck) -> UUID | None:
        async with session_factory() as db:
            document = await documents.get(db, document_id)
            ontology_id, filename = document.ontology_id, document.filename
            uploaded_by = document.uploaded_by
            chunks = [
                ChunkText(id=c.id, seq=c.seq, text=c.text, page=c.page, heading=c.heading)
                for c in await documents.list_chunks(db, document_id)
            ]
            candidates = await ontology.list_alignment_candidates(db, ontology_id)
            known = [known_element(element) for element in candidates.active]
            deleted = [known_element(element) for element in candidates.deleted]
            pending = pending_types(candidates.pending, known)

        async def progress(step: str, done: int, total: int) -> None:
            async with session_factory.begin() as db:
                # An execution that lost its job stops here instead of overwriting the newer
                # execution's progress and paying for model calls whose result it cannot keep.
                await check_lease(db)
                await documents.set_progress(db, document_id, step, done, total)

        try:
            proposals = await extractor.run(
                document_id=document_id,
                title=filename,
                chunks=chunks,
                known=known,
                progress=progress,
                deleted=deleted,
                pending=pending,
            )
        except AiError as exc:
            raise job_error(exc) from exc

        async with session_factory.begin() as db:
            # Lost the job to a newer execution: it rebuilt the chunks this evidence points at.
            await check_lease(db)
            # The lock makes a replayed job reuse the change set instead of adding a second one.
            document = await documents.lock(db, document_id)
            if document.change_set_id is not None:
                return document.change_set_id
            await documents.set_progress(db, document_id, "changeset", 1, 1)
            if not proposals:
                return None
            # Under the ontology's lock, merges and other change sets wait: what appeared
            # since the identification started is checked once more, without a model.
            await ontology.lock_ontology(db, ontology_id)
            now = await ontology.list_alignment_candidates(db, ontology_id)
            mark_late_candidates(proposals, late_candidates(candidates, now))
            items = [to_item(proposal, document_id) for proposal in proposals]
            change_set_id = await ontology.create_change_set(
                db,
                ontology_id=ontology_id,
                title=TITLE.format(filename=filename),
                source="ai_extraction",
                document_id=document_id,
                created_by=uploaded_by,
                items=items,
            )
            await documents.set_change_set(db, document_id, change_set_id)
        return change_set_id

    return extract


def make_transcriber(
    gateway: ModelGateway, model: str
) -> Callable[[ScanPart], Awaitable[list[ParsedPage]]]:
    """Scanned PDFs: the model reads a part of a few pages and returns their text."""

    async def transcribe(part: ScanPart) -> list[ParsedPage]:
        try:
            transcript = await gateway.structured(
                purpose="transcribe",
                model=model,
                instructions=TRANSCRIBE_INSTRUCTIONS,
                text="Transcribe the attached document.",
                schema=TranscriptOut,
                files=(
                    InputFile(
                        filename="document.pdf",
                        media_type="application/pdf",
                        data_base64=base64.b64encode(part.data).decode("ascii"),
                    ),
                ),
            )
        except AiError as exc:
            raise job_error(exc) from exc
        # Page numbers count from 1 within the part; a number outside it stays unknown.
        return [
            ParsedPage(
                number=part.first_page + page.number - 1
                if 1 <= page.number <= part.page_count
                else None,
                text=page.text,
                heading=page.heading,
            )
            for page in sorted(transcript.pages, key=lambda page: page.number)
            if page.text.strip()
        ]

    return transcribe
