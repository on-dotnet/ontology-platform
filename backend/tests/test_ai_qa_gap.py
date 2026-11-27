"""A Q5 gap can only create a proposal for human review."""

import asyncio
import re
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest
from httpx import Response
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from external_source import ExternalSource
from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa_gap, qa_prompts
from ontology_platform.modules.ai.assistant import OPERATIONS_MAX, to_item
from ontology_platform.modules.ai.gateway import AiError, AiInvalidOutputError, AiUnavailableError
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.prompts import AssistantOperationOut, AssistantOut
from ontology_platform.modules.ai.schemas import QaGapProposal, QaQuestion
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Element, Release
from ontology_platform.settings import Settings
from qa_support import (
    GatewayCall,
    QaDemo,
    inspection_metric_fixture,  # noqa: F401
    qa_demo_fixture,  # noqa: F401
    qa_steel_fixture,  # noqa: F401
)
from support import csrf_headers
from test_ai_assistant import operation
from test_ai_qa_prompt_safety import DOCUMENT_BODY, QUOTES, _attach_evidence
from test_ontology_support import sign_in
from test_query_support import assert_problem


@pytest.fixture
async def q5(qa_demo: QaDemo, db: AsyncSession) -> QaQuestion:
    await sign_in(qa_demo.client, db, Role.EDITOR)
    question = await qa_demo.run("Q5")
    assert question.status == "unanswerable"
    assert question.gaps is not None
    assert question.gaps.elements
    assert question.gap_proposal is None
    return question


def defect_type() -> AssistantOperationOut:
    return operation(
        "create", "entity_type", temp_ref="new:defect", label_zh="表面缺陷", local_name="Defect"
    )


def defect_relation(domain: str, target: str) -> AssistantOperationOut:
    return operation(
        "create",
        "relation_type",
        label_zh="钢卷表面缺陷",
        local_name="hasDefect",
        domain=domain,
        range=target,
        required=False,
        multiple=True,
    )


def defect_property(domain: str) -> AssistantOperationOut:
    return operation(
        "create",
        "property",
        label_zh="缺陷程度",
        local_name="severity",
        domain=domain,
        datatype="string",
        required=False,
        multiple=False,
    )


async def post_gap(demo: QaDemo, question: QaQuestion) -> Response:
    return await demo.client.post(
        f"/api/qa/questions/{question.id}/gap-proposal", headers=csrf_headers(demo.client)
    )


async def start_gap(demo: QaDemo, question: QaQuestion) -> None:
    response = await post_gap(demo, question)
    assert response.status_code == 202, response.text
    assert response.json()["id"] == str(question.id)
    assert response.json()["gapProposal"] == {
        "status": "queued",
        "changeSetId": None,
        "dropped": 0,
        "errorCode": None,
    }


async def gap_jobs(demo: QaDemo) -> list[Job]:
    async with demo.factory() as db:
        return list(await db.scalars(select(Job).where(Job.kind == "qa.gap")))


async def execute(
    demo: QaDemo,
    question: QaQuestion,
    output: AssistantOut | AiError,
    *,
    attempts: int = 1,
    actor_id: UUID | None = None,
) -> None:
    [job] = await gap_jobs(demo)
    assert job.payload == {
        "questionId": str(question.id),
        "userId": str(actor_id or question.asked_by.id),
    }
    demo.gateway.outputs["qa.gap"] = output
    handler = qa_gap.make_gap_proposer(demo.factory, demo.gateway, "scripted")
    await handler(JobContext(job.id, job.payload, demo.factory, attempts=attempts, max_attempts=3))


async def proposal(demo: QaDemo, question: QaQuestion) -> QaGapProposal:
    current = await demo.fetch(question.id)
    assert current.status == "unanswerable"
    assert current.gaps == question.gaps
    assert current.gap_proposal is not None
    return current.gap_proposal


async def change_sets(demo: QaDemo) -> set[UUID]:
    async with demo.factory() as db:
        return set(
            await db.scalars(
                select(ChangeSet.id).where(ChangeSet.ontology_id == demo.steel.ontology.id)
            )
        )


async def working_version(db: AsyncSession, ontology_id: UUID) -> tuple[dict[UUID, int], set[UUID]]:
    elements = await db.execute(
        select(Element.id, Element.revision).where(Element.ontology_id == ontology_id)
    )
    releases = await db.scalars(select(Release.id).where(Release.ontology_id == ontology_id))
    return {row.id: row.revision for row in elements}, set(releases)


async def test_q5_gap_creates_only_pending_changes(
    qa_demo: QaDemo, q5: QaQuestion, db: AsyncSession
) -> None:
    before = await working_version(db, q5.ontology_id)
    existing = await change_sets(qa_demo)
    coil = qa_demo.steel.ids["Coil"]
    output = AssistantOut(reply="", operations=[defect_type(), defect_relation(coil, "new:defect")])

    async def observe(call: GatewayCall) -> None:
        assert call.purpose == "qa.gap"
        assert (await proposal(qa_demo, q5)).status == "running"
        repeated = await post_gap(qa_demo, q5)
        assert repeated.status_code == 200
        assert repeated.json()["gapProposal"]["status"] == "running"

    await start_gap(qa_demo, q5)
    qa_demo.gateway.before_call = observe
    await execute(qa_demo, q5, output)
    result = await proposal(qa_demo, q5)
    assert (result.status, result.dropped, result.error_code) == ("done", 0, None)
    assert result.change_set_id is not None
    assert await change_sets(qa_demo) == existing | {result.change_set_id}
    change = await db.get(ChangeSet, result.change_set_id)
    assert change is not None
    assert (change.source, change.status, change.created_by) == ("ai_qa", "open", q5.asked_by.id)
    assert change.title == f"问答缺口：{q5.question[:40]}"
    items = list(await db.scalars(select(ChangeItem).where(ChangeItem.change_set_id == change.id)))
    assert sorted((i.op, i.kind, i.decision) for i in items) == [
        ("create", "entity_type", "pending"),
        ("create", "relation_type", "pending"),
    ]
    assert all(i.applied_element_id is None and i.decided_by is None for i in items)
    assert await working_version(db, q5.ontology_id) == before


async def test_gap_mixed_operations_count_every_drop(
    qa_demo: QaDemo, q5: QaQuestion, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    coil = await db.get(Element, UUID(qa_demo.steel.ids["Coil"]))
    assert coil is not None
    rejected = [
        operation("update", "entity_type", target=coil, label_zh="改名"),
        operation("delete", "entity_type", target=coil),
        operation("create", "constraint"),
        operation("create", "axiom"),
    ]
    accepted = [
        defect_type(),
        defect_property("new:defect"),
        defect_relation(str(coil.id), "new:defect"),
    ]
    malformed = operation("create", "entity_type", label_zh="过" * 201, local_name="TooLong")
    duplicate = operation("create", "entity_type", label_zh="重复名称", local_name="Defect")
    assert to_item(malformed) is None
    assert to_item(duplicate) is not None
    convert = Mock(wraps=to_item)
    monkeypatch.setattr(qa_gap, "to_item", convert)
    output = AssistantOut(reply="", operations=[*rejected, *accepted, malformed, duplicate])
    await start_gap(qa_demo, q5)
    await execute(qa_demo, q5, output)

    assert convert.call_args_list == [call(op) for op in [*accepted, malformed, duplicate]]
    result = await proposal(qa_demo, q5)
    assert (result.status, result.dropped) == ("done", len(rejected) + 1 + 1)
    items = await db.scalars(
        select(ChangeItem).where(ChangeItem.change_set_id == result.change_set_id)
    )
    assert sorted((i.op, i.kind, i.proposed["localName"]) for i in items) == [
        ("create", "entity_type", "Defect"),
        ("create", "property", "severity"),
        ("create", "relation_type", "hasDefect"),
    ]


@pytest.mark.parametrize(
    "kind", ["entity_type", "relation_type", "property", "constraint", "axiom"]
)
async def test_gap_filters_each_kind_before_conversion(
    qa_demo: QaDemo, q5: QaQuestion, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    coil = qa_demo.steel.ids["Coil"]
    allowed = {
        "entity_type": defect_type(),
        "property": defect_property(coil),
        "relation_type": defect_relation(coil, qa_demo.steel.ids["Heat"]),
    }
    op = allowed.get(kind, operation("create", kind))
    existing = await change_sets(qa_demo)
    convert = Mock(wraps=to_item)
    monkeypatch.setattr(qa_gap, "to_item", convert)
    await start_gap(qa_demo, q5)
    await execute(qa_demo, q5, AssistantOut(reply="", operations=[op]))
    result = await proposal(qa_demo, q5)
    if kind in allowed:
        convert.assert_called_once_with(op)
        assert (result.status, result.dropped) == ("done", 0)
        assert result.change_set_id is not None
    else:
        convert.assert_not_called()
        assert (result.status, result.change_set_id, result.dropped) == ("empty", None, 1)
        assert await change_sets(qa_demo) == existing


async def test_gap_caps_operations(qa_demo: QaDemo, q5: QaQuestion, db: AsyncSession) -> None:
    operations = [
        operation("create", "entity_type", label_zh=f"缺陷{i}", local_name=f"Defect{i}")
        for i in range(OPERATIONS_MAX + 2)
    ]
    await start_gap(qa_demo, q5)
    await execute(qa_demo, q5, AssistantOut(reply="", operations=operations))
    result = await proposal(qa_demo, q5)
    assert (result.status, result.dropped) == ("done", 2)
    items = await db.scalars(
        select(ChangeItem).where(ChangeItem.change_set_id == result.change_set_id)
    )
    assert sorted(i.proposed["localName"] for i in items) == sorted(
        f"Defect{i}" for i in range(OPERATIONS_MAX)
    )


@pytest.mark.parametrize("state", ["queued", "running", "answered", "failed", "bindings-only"])
async def test_gap_requires_unanswerable_and_missing_elements(
    qa_demo: QaDemo, q5: QaQuestion, db: AsyncSession, state: str
) -> None:
    row = await db.get(QaQuestionRow, q5.id)
    assert row is not None
    if state == "bindings-only":
        row.gaps = {
            "elements": [],
            "bindings": [{"typeId": qa_demo.steel.ids["Coil"], "label": "钢卷"}],
        }
    else:
        # Keep the semantic gaps so this tests the status guard independently.
        row.status = state
    await db.commit()
    assert_problem(await post_gap(qa_demo, q5), 409, "qa.not_unanswerable")
    assert await gap_jobs(qa_demo) == []
    assert (await qa_demo.fetch(q5.id)).gap_proposal is None


async def test_gap_unconfigured_model_leaves_no_job(
    qa_demo: QaDemo, q5: QaQuestion, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.openai_api_key = None
    monkeypatch.delenv("OP_OPENAI_API_KEY")
    assert_problem(await post_gap(qa_demo, q5), 409, "ai.not_configured")
    assert await gap_jobs(qa_demo) == []
    assert (await qa_demo.fetch(q5.id)).gap_proposal is None


async def test_gap_concurrent_posts_and_redelivery_are_idempotent(
    qa_demo: QaDemo, q5: QaQuestion
) -> None:
    existing = await change_sets(qa_demo)
    start = asyncio.Barrier(2)

    async def click() -> Response:
        await start.wait()
        return await post_gap(qa_demo, q5)

    a, b = await asyncio.gather(click(), click())
    assert sorted([a.status_code, b.status_code]) == [200, 202]
    assert a.json() == b.json()
    repeated = await post_gap(qa_demo, q5)
    assert repeated.status_code == 200
    assert repeated.json() == a.json()
    output = AssistantOut(reply="", operations=[defect_type()])
    await execute(qa_demo, q5, output)
    done = await proposal(qa_demo, q5)
    assert done.status == "done"
    assert done.change_set_id is not None
    await execute(qa_demo, q5, output, attempts=2)
    assert await proposal(qa_demo, q5) == done
    repeated = await post_gap(qa_demo, q5)
    assert repeated.status_code == 200
    assert repeated.json()["gapProposal"] == done.model_dump(mode="json", by_alias=True)
    assert len(await gap_jobs(qa_demo)) == 1
    assert await change_sets(qa_demo) == existing | {done.change_set_id}
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan", "qa.gap"]


async def test_gap_requires_creator_and_owner_or_admin(qa_demo: QaDemo, db: AsyncSession) -> None:
    await sign_in(qa_demo.client, db, Role.VIEWER)
    question = await qa_demo.run("Q5")
    assert_problem(await post_gap(qa_demo, question), 403, "auth.forbidden")
    await sign_in(qa_demo.client, db, Role.EDITOR)
    assert_problem(await post_gap(qa_demo, question), 404, "qa.not_found")
    assert await gap_jobs(qa_demo) == []
    await sign_in(qa_demo.client, db, Role.ADMIN)
    admin = UUID((await qa_demo.client.get("/api/auth/me")).json()["id"])
    assert admin != question.asked_by.id
    await start_gap(qa_demo, question)
    output = AssistantOut(reply="", operations=[defect_type()])
    await execute(qa_demo, question, output, actor_id=admin)
    result = await proposal(qa_demo, question)
    assert result.status == "done"
    assert result.change_set_id is not None
    change = await db.get(ChangeSet, result.change_set_id)
    assert change is not None
    assert change.created_by == admin


async def test_gap_change_set_rolls_back_if_result_commit_fails(
    qa_demo: QaDemo, q5: QaQuestion
) -> None:
    existing = await change_sets(qa_demo)
    await start_gap(qa_demo, q5)

    def reject_result(session: Session) -> None:
        # Observe the database after flush, regardless of how the handler updates the row.
        session.flush()
        status = session.scalar(select(QaQuestionRow.gap_status).where(QaQuestionRow.id == q5.id))
        if status == "done":
            raise RuntimeError("injected failure committing gap result")

    event.listen(Session, "before_commit", reject_result)
    try:
        with pytest.raises(RuntimeError, match="injected failure committing gap result"):
            await execute(qa_demo, q5, AssistantOut(reply="", operations=[defect_type()]))
    finally:
        event.remove(Session, "before_commit", reject_result)
    assert await change_sets(qa_demo) == existing
    assert (await proposal(qa_demo, q5)).change_set_id is None


async def test_gap_requeues_transient_error_then_succeeds(qa_demo: QaDemo, q5: QaQuestion) -> None:
    existing = await change_sets(qa_demo)
    await start_gap(qa_demo, q5)
    with pytest.raises(RetryableJobError) as retry:
        await execute(qa_demo, q5, AiUnavailableError("scripted outage", retryable=True))
    assert retry.value.code == "ai.unavailable"
    queued = await proposal(qa_demo, q5)
    assert (queued.status, queued.change_set_id) == ("queued", None)
    assert await change_sets(qa_demo) == existing
    await execute(qa_demo, q5, AssistantOut(reply="", operations=[defect_type()]), attempts=2)
    done = await proposal(qa_demo, q5)
    assert (done.status, done.error_code) == ("done", None)
    assert done.change_set_id is not None
    assert await change_sets(qa_demo) == existing | {done.change_set_id}


@pytest.mark.parametrize(
    ("error", "attempts"),
    [
        (AiInvalidOutputError("invalid", retryable=False), 1),
        (AiUnavailableError("busy", retryable=True), 3),
    ],
    ids=["permanent", "exhausted"],
)
async def test_gap_terminal_error_leaves_question_and_ontology_intact(
    qa_demo: QaDemo, q5: QaQuestion, error: AiError, attempts: int
) -> None:
    existing = await change_sets(qa_demo)
    await start_gap(qa_demo, q5)
    with pytest.raises(AppError) as terminal:
        await execute(qa_demo, q5, error, attempts=attempts)
    assert terminal.value.code == error.code
    failed = await proposal(qa_demo, q5)
    assert (failed.status, failed.error_code, failed.change_set_id) == ("failed", error.code, None)
    assert await change_sets(qa_demo) == existing
    repeated = await post_gap(qa_demo, q5)
    assert repeated.status_code == 200
    assert repeated.json()["gapProposal"] == failed.model_dump(mode="json", by_alias=True)
    assert len(await gap_jobs(qa_demo)) == 1


async def test_q5_gap_prompt_contains_only_semantic_context(
    qa_demo: QaDemo,
    q5: QaQuestion,
    db: AsyncSession,
    external_source: ExternalSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _attach_evidence(db, qa_demo)
    context = AsyncMock(wraps=ontology_assistant.context_for)
    monkeypatch.setattr(ontology_assistant, "context_for", context)
    await start_gap(qa_demo, q5)
    await execute(qa_demo, q5, AssistantOut(reply="", operations=[defect_type()]))
    context.assert_awaited_once()
    args = context.await_args
    assert args is not None
    message = args.kwargs["message"]
    assert args.kwargs["page"] == "explore"
    assert args.kwargs["element_id"] is None
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan", "qa.gap"]
    gap = qa_demo.gateway.calls[-1]
    assert gap.schema is AssistantOut
    assert gap.instructions is qa_prompts.QA_GAP_INSTRUCTIONS
    assert not gap.files
    assert gap.document_id is None
    assert q5.gaps is not None
    for content in (message, gap.text):
        assert q5.question in content
        for element in q5.gaps.elements:
            assert element.label_zh in content
            assert element.description in content
            assert all(ref.label in content for ref in element.near)
    assert "类型" in message
    assert "关系" in message
    assert str(qa_demo.steel.ids["Coil"]) in gap.text
    for content in (gap.text, gap.instructions):
        # Heat, Slab and Coil also name ontology types. The physical names below are distinct.
        for token in (
            "mes",
            "casting_sequence",
            "rolling_event",
            "quality_inspection",
            "slab_rolling",
            "heat_no",
            "cast_no",
            "coil_no",
            "slab_no",
            "steel_grade",
            "weight_t",
            "site_id",
            "org_id",
            "rolling_id",
            "inspection_id",
            "thickness_mm",
            "yield_mpa",
            "tensile_mpa",
            "elongation_pct",
            "impact_j",
            "inspected_on",
            external_source.host,
            str(external_source.port),
        ):
            assert not re.search(rf"(?<!\w){re.escape(token)}(?!\w)", content, re.I)
        for private in (
            qa_demo.steel.source_name,
            qa_demo.steel.source_id,
            external_source.database,
            external_source.reader,
            "H2401001",
            "W240101201",
            DOCUMENT_BODY,
            *QUOTES,
            "资料04.md",
        ):
            assert private not in content
