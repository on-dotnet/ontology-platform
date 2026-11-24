"""Connects the extraction to document processing: chunks in, an open change set out.

The worker registers `make_extractor` and `make_transcriber` with the documents module. The
extractor reads the document's chunks and the ontology's elements, runs the staged extraction
and writes the proposals as one change set. That is the only thing AI writes (AGENTS.md red
line): nothing reaches the ontology until a reviewer merges the change set.
"""

import base64
from collections.abc import Awaitable, Callable
from typing import Any, cast
from uuid import UUID

from annotated_types import MaxLen
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    Kind,
    KnownElement,
    Proposal,
)
from ontology_platform.modules.ai.gateway import AiError, InputFile, ModelGateway
from ontology_platform.modules.ai.prompts import TRANSCRIBE_INSTRUCTIONS, TranscriptOut
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.documents.parsers import ParsedPage
from ontology_platform.modules.jobs.runner import RetryableJobError
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.schemas import (
    ElementCopy,
    ElementFields,
    EvidenceIn,
    ProposedItem,
)

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
        kind=cast(Kind, element.kind),  # list_alignment_elements returns only these kinds
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
    )


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
) -> Callable[[UUID], Awaitable[UUID | None]]:
    extractor = Extractor(gateway, models)

    async def extract(document_id: UUID) -> UUID | None:
        async with session_factory() as db:
            document = await documents.get(db, document_id)
            ontology_id, filename = document.ontology_id, document.filename
            uploaded_by = document.uploaded_by
            chunks = [
                ChunkText(id=c.id, seq=c.seq, text=c.text, page=c.page, heading=c.heading)
                for c in await documents.list_chunks(db, document_id)
            ]
            known = [
                known_element(element)
                for element in await ontology.list_alignment_elements(db, ontology_id)
            ]

        async def progress(step: str, done: int, total: int) -> None:
            async with session_factory.begin() as db:
                await documents.set_progress(db, document_id, step, done, total)

        try:
            proposals = await extractor.run(
                document_id=document_id,
                title=filename,
                chunks=chunks,
                known=known,
                progress=progress,
            )
        except AiError as exc:
            raise job_error(exc) from exc
        items = [to_item(proposal, document_id) for proposal in proposals]

        async with session_factory.begin() as db:
            # The lock makes a replayed job reuse the change set instead of adding a second one.
            document = await documents.lock(db, document_id)
            if document.change_set_id is not None:
                return document.change_set_id
            await documents.set_progress(db, document_id, "changeset", 1, 1)
            if not items:
                return None
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
) -> Callable[[bytes], Awaitable[list[ParsedPage]]]:
    """Scanned PDFs: the model reads the pages and returns their text."""

    async def transcribe(data: bytes) -> list[ParsedPage]:
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
                        data_base64=base64.b64encode(data).decode("ascii"),
                    ),
                ),
            )
        except AiError as exc:
            raise job_error(exc) from exc
        return [
            ParsedPage(number=page.number, text=page.text, heading=page.heading)
            for page in sorted(transcript.pages, key=lambda page: page.number)
            if page.text.strip()
        ]

    return transcribe
