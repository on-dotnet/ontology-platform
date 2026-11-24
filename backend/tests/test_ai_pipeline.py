"""The extraction pipeline turns a parsed document into one open change set, and only that."""

import base64
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.extraction import ExtractionModels, Proposal, ProposedEvidence
from ontology_platform.modules.ai.gateway import (
    AiNotConfiguredError,
    AiUnavailableError,
    InputFile,
)
from ontology_platform.modules.ai.pipeline import make_extractor, make_transcriber, to_item
from ontology_platform.modules.ai.prompts import (
    PageOut,
    RelationsOut,
    TermOut,
    TermsOut,
    TranscriptOut,
    TypesOut,
)
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.jobs.runner import JobContext, JobLeaseLostError, RetryableJobError
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology
from test_ai_extraction import ScriptedGateway, entity, quote, relation
from test_ontology_support import add_elements, add_ontology, element

MODELS = ExtractionModels(standard="std", reasoning="deep")
TEXT = "每个炉次只冶炼一个钢种。一个浇次由若干个炉次的钢水连续浇铸而成。"


class FailingGateway(ScriptedGateway):
    def __init__(self, error: Exception) -> None:
        super().__init__({})
        self.error = error

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
    ) -> T:
        raise self.error


async def held(_: AsyncSession) -> None:
    """A lease check for an execution that still owns its job."""


def factory(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    return session_factory


async def add_document(db: AsyncSession, ontology: Ontology) -> tuple[Document, Chunk]:
    document = Document(
        id=uuid4(),
        ontology_id=ontology.id,
        filename="转炉规程.md",
        media_type="text/markdown",
        size_bytes=len(TEXT.encode()),
        sha256="0" * 64,
        storage_key="test",
        status="extracting",
        progress={"step": "parse", "done": 1, "total": 1},
        uploaded_by=uuid4(),
    )
    db.add(document)
    await db.flush()
    chunk = Chunk(document_id=document.id, seq=0, text=TEXT, char_count=len(TEXT))
    db.add(chunk)
    await db.commit()
    return document, chunk


def outputs(grade: Element, *, empty: bool = False) -> dict[str, list[BaseModel]]:
    term = TermOut(name="炉次", english="Heat", definition=None, category="entity", quotes=[])
    types = [
        entity("new:Heat", "炉次", "Heat", quotes=[quote(0, "每个炉次只冶炼一个钢种")]),
        entity(str(grade.id), "钢种", "SteelGrade", synonyms=["牌号", "钢级"]),
    ]
    relations = [relation("new:Heat", str(grade.id), "冶炼", [quote(0, "炉次只冶炼一个钢种")])]
    return {
        "extract.terms": [TermsOut(terms=[] if empty else [term])],
        "extract.types": [TypesOut(entity_types=[] if empty else types)],
        "extract.relations": [RelationsOut(relations=[] if empty else relations, properties=[])],
    }


async def change_set_count(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(ChangeSet)) or 0


async def test_extraction_writes_one_open_change_set(app: FastAPI, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    document, chunk = await add_document(db, ontology)
    extract = make_extractor(factory(app), ScriptedGateway(outputs(grade)), MODELS)

    change_set_id = await extract(document.id, held)

    assert change_set_id is not None
    detail = await ontology_service.get_change_set(db, change_set_id)
    assert detail.title == "识别：转炉规程.md"
    assert detail.source == "ai_extraction"
    assert detail.document_id == document.id
    assert detail.status == "open"
    assert {(item.op, item.kind) for item in detail.items} == {
        ("create", "entity_type"),
        ("update", "entity_type"),
        ("create", "relation_type"),
    }
    assert all(item.decision == "pending" for item in detail.items)
    heat = next(item for item in detail.items if item.temp_ref == "new:Heat")
    [evidence] = heat.evidence
    assert (evidence.document_id, evidence.chunk_id) == (document.id, chunk.id)
    assert TEXT[evidence.char_start : evidence.char_end] == "每个炉次只冶炼一个钢种"
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "changeset.created"))
    assert event is not None
    assert (event.actor_id, event.target_id) == (None, str(change_set_id))
    # Nothing reached the ontology itself: only the reviewer's merge does that.
    elements = await ontology_service.list_alignment_elements(db, ontology.id)
    assert [e.local_name for e in elements] == ["SteelGrade"]

    document_id = document.id
    db.expire_all()
    stored = await db.get(Document, document_id)
    assert stored is not None
    assert stored.change_set_id == change_set_id
    assert stored.progress == {"step": "changeset", "done": 1, "total": 1}


async def test_a_replayed_job_reuses_the_change_set(app: FastAPI, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    document, _ = await add_document(db, ontology)
    gateway = ScriptedGateway({k: v * 2 for k, v in outputs(grade).items()})
    extract = make_extractor(factory(app), gateway, MODELS)

    first = await extract(document.id, held)
    second = await extract(document.id, held)

    assert first == second
    assert await change_set_count(db) == 1


async def test_nothing_found_means_no_change_set(app: FastAPI, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    document, _ = await add_document(db, ontology)
    extract = make_extractor(factory(app), ScriptedGateway(outputs(grade, empty=True)), MODELS)

    assert await extract(document.id, held) is None
    assert await change_set_count(db) == 0


@pytest.mark.parametrize(
    ("error", "expected", "code"),
    [
        (AiUnavailableError("timeout", retryable=True), RetryableJobError, "ai.unavailable"),
        (AiUnavailableError("401", retryable=False), AppError, "ai.unavailable"),
        (AiNotConfiguredError(), AppError, "ai.not_configured"),
    ],
)
async def test_model_errors_become_job_errors(
    app: FastAPI, db: AsyncSession, error: Exception, expected: type[Exception], code: str
) -> None:
    ontology = await add_ontology(db)
    document, _ = await add_document(db, ontology)
    extract = make_extractor(factory(app), FailingGateway(error), MODELS)

    with pytest.raises(expected) as raised:
        await extract(document.id, held)

    assert getattr(raised.value, "code", None) == code
    assert await change_set_count(db) == 0


def test_items_are_clipped_to_the_column_limits() -> None:
    chunk_id, document_id = uuid4(), uuid4()
    proposal = Proposal(
        op="create",
        kind="entity_type",
        temp_ref="new:Heat",
        fields={
            "localName": "Heat",
            "labelZh": "炉" * 300,
            "synonyms": [{"lang": "zh", "text": "次" * 300}, {"lang": "en", "text": "Heat"}],
        },
        evidence=[ProposedEvidence(chunk_id, "引" * 800, 0, 800)],
    )

    item = to_item(proposal, document_id)

    assert item.proposed.label_zh == "炉" * 200
    assert [s.text for s in item.proposed.synonyms or []] == ["Heat"]
    assert len(item.evidence[0].quote) == 500
    assert item.evidence[0].quote.endswith("…")
    assert item.evidence[0].document_id == document_id


class TranscriptGateway(ScriptedGateway):
    def __init__(self, transcript: TranscriptOut) -> None:
        super().__init__({"transcribe": [transcript]})
        self.files: Sequence[InputFile] = ()

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
    ) -> T:
        self.files = files
        return await super().structured(
            purpose=purpose, model=model, instructions=instructions, text=text, schema=schema
        )


async def test_transcriber_returns_pages_in_order() -> None:
    transcript = TranscriptOut(
        pages=[
            PageOut(number=2, heading=None, text="第二页"),
            PageOut(number=3, heading=None, text="  "),
            PageOut(number=1, heading="总则", text="第一页"),
        ]
    )
    gateway = TranscriptGateway(transcript)

    pages = await make_transcriber(gateway, "std")(b"%PDF-1.7 scanned")

    assert [(p.number, p.heading, p.text) for p in pages] == [
        (1, "总则", "第一页"),
        (2, None, "第二页"),
    ]
    [file] = gateway.files
    assert file.media_type == "application/pdf"
    assert base64.b64decode(file.data_base64) == b"%PDF-1.7 scanned"
    assert gateway.calls == [("transcribe", "std")]


async def test_an_execution_that_lost_its_lease_writes_no_change_set(
    app: FastAPI, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    document, _ = await add_document(db, ontology)
    extract = make_extractor(factory(app), ScriptedGateway(outputs(grade)), MODELS)
    # A worker whose claim on the job was taken over by a newer execution.
    stale = JobContext(id=uuid4(), payload={}, session_factory=factory(app), worker_id="gone")

    with pytest.raises(JobLeaseLostError):
        await extract(document.id, stale.check_lease)

    assert await change_set_count(db) == 0
    document_id = document.id
    db.expire_all()
    stored = await db.get(Document, document_id)
    assert stored is not None
    assert stored.change_set_id is None
