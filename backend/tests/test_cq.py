"""Competency questions against the HTTP API, steel release and QA completion listener."""

import asyncio
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform import worker
from ontology_platform.db import get_db
from ontology_platform.modules.ai import qa, qa_run
from ontology_platform.modules.ai.gateway import AiInvalidOutputError
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.qa_plan import check_plan
from ontology_platform.modules.ai.qa_prompts import QaAnswerOut
from ontology_platform.modules.ai.schemas import QaPlan, QaQuestion
from ontology_platform.modules.cq import schemas, service
from ontology_platform.modules.cq.models import CompetencyQuestionRow, CqCheckRow
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.ontology.qa_context import qa_context
from ontology_platform.modules.query import cursor
from ontology_platform.modules.query.service import list_types
from ontology_platform.settings import Settings
from qa_support import (
    GatewayCall,
    QaDemo,
    inspection_metric_fixture,  # noqa: F401
    qa_demo_fixture,  # noqa: F401
    qa_steel_fixture,  # noqa: F401
)
from support import csrf_headers
from test_ontology_bindings_support import bindings
from test_ontology_editing import create, edit, save
from test_ontology_support import add_ontology, elements_by_name, publish, sign_in
from test_query_support import assert_problem
from test_route_protection import token_holder


def collection(ontology_id: UUID) -> str:
    return f"/api/ontologies/{ontology_id}/competency-questions"


def item(question_id: UUID) -> str:
    return f"/api/competency-questions/{question_id}"


async def post(client: AsyncClient, url: str, body: dict[str, Any] | None = None) -> Response:
    return await client.post(url, json=body, headers=csrf_headers(client))


async def new_question(
    client: AsyncClient, url: str, text: str, expect: dict[str, Any] | None = None, **fields: Any
) -> schemas.CompetencyQuestion:
    body = {"text": text, "expect": expect or {"kind": "answerable"}, **fields}
    response = await post(client, url, body)
    assert response.status_code == 201, response.text
    return schemas.CompetencyQuestion.model_validate(response.json())


async def patch(client: AsyncClient, question_id: UUID, **fields: Any) -> Response:
    return await client.patch(item(question_id), json=fields, headers=csrf_headers(client))


async def listed(
    client: AsyncClient, url: str, *, running: bool | None = None
) -> list[schemas.CompetencyQuestion]:
    response = await client.get(url)
    assert response.status_code == 200, response.text
    if running is not None:
        assert response.headers["X-Cq-Check-Running"].lower() == str(running).lower()
    return schemas.CompetencyQuestionList.model_validate(response.json()).items


async def check_one(client: AsyncClient, question_id: UUID) -> schemas.CqCheck:
    response = await post(client, item(question_id) + "/check")
    assert response.status_code == 202, response.text
    check = schemas.CqCheck.model_validate(response.json())
    assert check.question_id == question_id
    assert check.result == "pending"
    assert check.finished_at is None
    return check


async def last(demo: QaDemo, question_id: UUID) -> schemas.CqCheck:
    rows = await listed(demo.client, collection(demo.steel.ontology.id))
    [row] = [q for q in rows if q.id == question_id]
    assert row.last_check is not None
    return row.last_check


async def counts(db: AsyncSession) -> tuple[int, int, int]:
    checks = await db.scalar(select(func.count()).select_from(CqCheckRow))
    questions = await db.scalar(select(func.count()).select_from(QaQuestionRow))
    jobs = await db.scalar(select(func.count(Job.id)).where(Job.kind == qa.JOB_KIND))
    assert checks is not None
    assert questions is not None
    assert jobs is not None
    return checks, questions, jobs


@pytest.fixture
def checked_demo(qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch) -> QaDemo:
    monkeypatch.setattr(qa, "_listeners", qa._listeners.copy())
    qa.register_listener(service.record_result)
    return qa_demo


async def case_question(
    demo: QaDemo, case: str, *, expect: dict[str, Any] | None = None
) -> schemas.CompetencyQuestion:
    data = demo.questions[case]
    fields = (data["expect"] if expect is None else expect).copy()
    if "typeIri" in fields:
        fields["typeId"] = demo.steel.ids[fields.pop("typeIri").rsplit(":", 1)[1]]
    return await new_question(demo.client, collection(demo.steel.ontology.id), data["text"], fields)


async def script(demo: QaDemo, case: str) -> None:
    demo.gateway.question = demo.questions[case]["text"]
    demo.gateway.outputs = {"qa.plan": await demo.plan(case)}
    if "answer" in demo.scripts[case]:
        demo.gateway.outputs["qa.answer"] = QaAnswerOut.model_validate(demo.scripts[case]["answer"])


async def finish(
    demo: QaDemo, check: schemas.CqCheck, case: str, *, invalid_plan: bool = False
) -> tuple[schemas.CqCheck, QaQuestion]:
    await script(demo, case)
    if invalid_plan:
        demo.gateway.outputs["qa.plan"] = AiInvalidOutputError("invalid", retryable=False)
    await demo.execute(check.qa_question_id)
    [question] = [q for q in demo.completed if q.id == check.qa_question_id]
    done = await last(demo, check.question_id)
    assert done.id == check.id
    assert done.finished_at is not None
    return done, question


async def test_editor_reorders_one_row_edits_with_revision_and_archives(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    url = collection(ontology.id)
    await sign_in(client, db, Role.EDITOR)
    first, second, third = [await new_question(client, url, text) for text in ("一", "二", "三")]
    assert first.revision == 1
    assert first.last_check is None
    assert [q.id for q in await listed(client, url)] == [first.id, second.id, third.id]
    moved = await patch(client, second.id, revision=second.revision, position=first.position)
    assert moved.status_code == 200, moved.text
    rows = await listed(client, url)
    assert [q.id for q in rows] == [second.id, first.id, third.id]
    assert rows[0].position < rows[1].position < rows[2].position
    assert rows[0].revision > second.revision
    changes = {"text": "多少？", "note": "昨天", "expect": {"kind": "number", "number": "18.25"}}
    assert_problem(await patch(client, second.id, **changes), 422, "validation.failed")
    stale = await patch(client, second.id, revision=second.revision, **changes)
    assert_problem(stale, 409, "cq.stale")
    changed = await patch(client, second.id, revision=rows[0].revision, **changes)
    assert changed.status_code == 200, changed.text
    updated = schemas.CompetencyQuestion.model_validate(changed.json())
    assert (updated.text, updated.note, updated.expect.kind) == ("多少？", "昨天", "number")
    assert Decimal(updated.expect.number or "") == Decimal("18.25")
    assert Decimal(updated.expect.tolerance) == 0
    archive = item(second.id) + "/archive"
    assert_problem(await post(client, archive, {"revision": rows[0].revision}), 409, "cq.stale")
    archived = await post(client, archive, {"revision": updated.revision})
    assert archived.status_code == 200, archived.text
    assert archived.json()["archivedAt"] is not None
    assert (await post(client, item(third.id) + "/archive")).status_code == 200
    assert [q.id for q in await listed(client, url)] == [first.id]


async def test_expectation_validation_and_plain_keys_on_the_wire(
    qa_demo: QaDemo, db: AsyncSession
) -> None:
    demo = qa_demo
    url = collection(demo.steel.ontology.id)
    heat = demo.steel.ids["Heat"]
    expect = {"kind": "objects", "typeId": heat, "keys": ["H2401001", "H2401002"]}
    question = await new_question(demo.client, url, "哪些炉次？", expect)
    assert question.expect.type_id == UUID(heat)
    assert set(question.expect.keys) == {"H2401001", "H2401002"}
    stored = await db.get(CompetencyQuestionRow, question.id)
    assert stored is not None
    assert stored.expect_objects is not None
    encoded = {cursor.encode_key([k]) for k in question.expect.keys}
    assert set(stored.expect_objects["keys"]) == encoded
    invalid = [
        {"kind": "other"},
        {"kind": "objects", "keys": ["x"]},
        {**expect, "typeId": str(uuid4())},
        {**expect, "typeId": demo.steel.ids["steelGrade"]},
        {**expect, "keys": [str(i) for i in range(101)]},
        {"kind": "number"},
        {"kind": "number", "number": "NaN"},
        {"kind": "number", "number": "one"},
        {"kind": "number", "number": "1", "tolerance": "-0.01"},
    ]
    for bad in invalid:
        response = await post(demo.client, url, {"text": "能回答吗？", "expect": bad})
        assert_problem(response, 422, "validation.failed")
    for fields in ({"text": ""}, {"text": "字" * 501}, {"note": "字" * 1001}):
        body = {"text": "能回答吗？", "expect": {"kind": "answerable"}, **fields}
        assert_problem(await post(demo.client, url, body), 422, "validation.failed")
    assert_problem(
        await patch(demo.client, question.id, revision=question.revision, expect=invalid[-1]),
        422,
        "validation.failed",
    )
    assert await listed(demo.client, url) == [question]
    saved = await save(demo.client, demo.steel.ontology, create("entity_type", "Furnace", "熔炉"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"], saved.text
    furnace = (await elements_by_name(db, demo.steel.ontology))["Furnace"].id
    draft = await new_question(demo.client, url, "哪些熔炉？", {**expect, "typeId": str(furnace)})
    assert draft.expect.type_id == furnace


async def test_worker_registers_listener_and_finishes_the_queued_check(
    qa_demo: QaDemo, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = qa_demo
    question = await case_question(demo, "Q1")
    check = await check_one(demo.client, question.id)
    assert check.release.model_dump(mode="json") == demo.steel.release
    assert check.stale is False
    assert await last(demo, question.id) == check
    queued = await demo.fetch(check.qa_question_id)
    assert (queued.origin, queued.cq_question_id, queued.status) == ("cq", question.id, "queued")
    assert queued.question == question.text
    await script(demo, "Q1")

    async def run_one(
        factory: async_sessionmaker[AsyncSession],
        worker_id: str,
        *,
        stop_event: asyncio.Event,
        concurrency: int,
    ) -> None:
        async def stop_after_claim(call: GatewayCall) -> None:
            stop_event.set()

        demo.gateway.before_call = stop_after_claim
        await runner.run_worker(factory, worker_id, stop_event=stop_event, concurrency=1)

    # Start with empty process registries so another test cannot supply the CQ listener.
    monkeypatch.setattr(qa, "_listeners", [])
    registration = Mock(wraps=qa.register_listener)
    monkeypatch.setattr(qa, "register_listener", registration)
    monkeypatch.setattr(runner, "_handlers", {})
    monkeypatch.setattr(worker, "Settings", lambda: settings)
    monkeypatch.setattr(worker, "OpenAIGateway", Mock(return_value=demo.gateway))
    monkeypatch.setattr(worker, "run_worker", run_one)
    for name in ("register_extractor", "register_vision_transcriber", "register_usage_provider"):
        monkeypatch.setattr(worker, name, Mock())
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", Mock())
    monkeypatch.setattr(loop, "remove_signal_handler", Mock())
    async with asyncio.timeout(60):
        await worker.run()
    registration.assert_any_call(service.record_result)
    assert (await demo.fetch(check.qa_question_id)).status == "answered"
    done = await last(demo, question.id)
    assert (done.id, done.result, done.release) == (check.id, "pass", check.release)
    assert done.finished_at is not None


@pytest.mark.parametrize(("case", "size"), [("Q1", 18), ("Q2", 2)])
async def test_objects_use_full_keys_at_answer_position(
    checked_demo: QaDemo, monkeypatch: pytest.MonkeyPatch, case: str, size: int
) -> None:
    demo = checked_demo
    # Both answers extend beyond the single displayed row. Q2 also has a different tail type.
    monkeypatch.setattr(qa_run, "ROW_LIMIT", 1)
    expect = demo.questions[case]["expect"]
    question = await case_question(demo, case, expect={**expect, "keys": expect["keys"][::-1]})
    done, qa_result = await finish(demo, await check_one(demo.client, question.id), case)
    assert qa_result.evidence is not None
    assert len(qa_result.evidence.rows) == 1
    assert qa_result.answer_keys is not None
    assert len(qa_result.answer_keys.keys) == size
    assert done.result == "pass"


async def test_objects_return_plain_differences_and_reject_equal_keys_of_wrong_type(
    checked_demo: QaDemo,
) -> None:
    demo = checked_demo
    coil = await case_question(demo, "Q2")
    keys = ["W240101201", "W999999999"]
    fields = {"kind": "objects", "typeId": demo.steel.ids["Coil"], "keys": keys}
    changed = await patch(demo.client, coil.id, revision=coil.revision, expect=fields)
    assert changed.status_code == 200, changed.text
    mismatch, _ = await finish(demo, await check_one(demo.client, coil.id), "Q2")
    assert mismatch.result == "fail"
    assert mismatch.detail is not None
    assert mismatch.detail.missing == ["W999999999"]
    assert mismatch.detail.extra == ["W240101503"]
    assert mismatch.detail.actual == "2"

    wrong_type = {**fields, "typeId": demo.steel.ids["Heat"], "keys": coil.expect.keys}
    revision = changed.json()["revision"]
    changed = await patch(demo.client, coil.id, revision=revision, expect=wrong_type)
    assert changed.status_code == 200, changed.text
    mismatch, _ = await finish(demo, await check_one(demo.client, coil.id), "Q2")
    assert mismatch.result == "fail"


async def test_object_differences_are_capped_independently(checked_demo: QaDemo) -> None:
    demo = checked_demo
    inspection = UUID(demo.steel.ids["QualityInspection"])
    keys = [str(UUID(int=i)) for i in range(25)]
    expect = {"kind": "objects", "typeId": str(inspection), "keys": keys}
    question = await case_question(demo, "Q1", expect=expect)
    check = await check_one(demo.client, question.id)
    await script(demo, "Q1")
    plan = await demo.plan("Q1")
    plan.start = await demo.ref_for(inspection)
    plan.filters = []
    demo.gateway.outputs["qa.plan"] = plan
    await demo.execute(check.qa_question_id)
    [answered] = demo.completed
    assert answered.answer_keys is not None
    actual_keys = set(answered.answer_keys.keys)
    diff = await last(demo, question.id)
    assert diff.result == "fail"
    assert diff.detail is not None
    assert diff.detail.actual == "43"
    assert len(set(diff.detail.missing)) == len(diff.detail.missing) == 20
    assert len(set(diff.detail.extra)) == len(diff.detail.extra) == 20
    assert set(diff.detail.missing) <= set(keys)
    assert {cursor.encode_key([key]) for key in diff.detail.extra} < actual_keys


async def test_numeric_metric_uses_unrounded_value_and_count_uses_decimal_tolerance(
    checked_demo: QaDemo,
) -> None:
    demo = checked_demo
    metric = await case_question(demo, "Q3")
    done, answered = await finish(demo, await check_one(demo.client, metric.id), "Q3")
    assert done.result == "pass"
    assert answered.evidence is not None
    assert answered.evidence.metric is not None
    assert (answered.evidence.metric.matched, answered.evidence.metric.population) == (36, 39)
    changed = await patch(
        demo.client, metric.id, revision=metric.revision, expect={"kind": "number", "number": "1"}
    )
    assert changed.status_code == 200, changed.text
    failed, _ = await finish(demo, await check_one(demo.client, metric.id), "Q3")
    assert failed.result == "fail"
    assert failed.detail is not None
    assert failed.detail.actual is not None
    assert Decimal(failed.detail.actual) == Decimal(36) / 39

    expect = {
        "kind": "number",
        "number": "18.000000000000000001",
        "tolerance": "0.000000000000000001",
    }
    count = await case_question(demo, "Q1", expect=expect)
    boundary, _ = await finish(demo, await check_one(demo.client, count.id), "Q1")
    assert boundary.result == "pass"
    changed = await patch(
        demo.client, count.id, revision=count.revision, expect={**expect, "tolerance": "0"}
    )
    assert changed.status_code == 200, changed.text
    outside, _ = await finish(demo, await check_one(demo.client, count.id), "Q1")
    assert outside.result == "fail"
    assert outside.detail is not None
    assert outside.detail.actual == "18"


async def test_answerable_missing_number_unanswerable_and_qa_failure(checked_demo: QaDemo) -> None:
    demo = checked_demo
    rules = await case_question(demo, "Q4")
    ok, _ = await finish(demo, await check_one(demo.client, rules.id), "Q4")
    assert ok.result == "pass"
    changed = await patch(
        demo.client, rules.id, revision=rules.revision, expect={"kind": "number", "number": "0"}
    )
    assert changed.status_code == 200, changed.text
    missing, answer = await finish(demo, await check_one(demo.client, rules.id), "Q4")
    assert answer.answer is not None
    assert answer.answer.facts.count is None
    assert answer.answer.facts.metric is None
    assert missing.result == "fail"
    assert missing.detail is not None
    assert missing.detail.actual is None
    assert missing.detail.error_code
    gap = await case_question(demo, "Q5")
    unable, _ = await finish(demo, await check_one(demo.client, gap.id), "Q5")
    assert unable.result == "unanswerable"
    error, _ = await finish(demo, await check_one(demo.client, gap.id), "Q5", invalid_plan=True)
    assert error.result == "error"
    assert error.detail is not None
    assert error.detail.error_code == "ai.invalid_output"


async def test_completion_ignores_user_origin_and_is_idempotent(
    checked_demo: QaDemo, db: AsyncSession
) -> None:
    demo = checked_demo
    question = await case_question(demo, "Q1")
    check = await check_one(demo.client, question.id)
    queued = await demo.fetch(check.qa_question_id)
    failed = queued.model_copy(update={"status": "failed", "error_code": "qa.timeout"})
    # Keep the matching QA id: ignoring a user callback must not rely on a failed lookup.
    await service.record_result(db, failed.model_copy(update={"origin": "user"}))
    await db.commit()
    assert await last(demo, question.id) == check
    done, answered = await finish(demo, check, "Q1")
    assert done.result == "pass"
    await service.record_result(db, answered)
    await service.record_result(db, failed)
    await db.commit()
    assert await last(demo, question.id) == done
    assert await counts(db) == (1, 1, 1)


async def test_concurrent_bulk_checks_only_one_wins_and_completion_allows_restart(
    checked_demo: QaDemo, app: FastAPI, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = checked_demo
    url = collection(demo.steel.ontology.id)
    first = await case_question(demo, "Q1")
    second = await case_question(demo, "Q5")
    await check_one(demo.client, first.id)
    await listed(demo.client, url, running=False)
    gate = asyncio.Barrier(2)

    async def simultaneous_sessions() -> AsyncIterator[AsyncSession]:
        async with demo.factory() as session:
            await session.connection()
            await gate.wait()
            yield session

    # Both requests must hold their own database connection before either endpoint proceeds.
    with monkeypatch.context() as patcher:
        patcher.setitem(app.dependency_overrides, get_db, simultaneous_sessions)
        async with asyncio.timeout(30):
            responses = await asyncio.gather(*(post(demo.client, url + "/check") for _ in range(2)))
    assert sorted(r.status_code for r in responses) == [202, 409]
    accepted, conflict = sorted(responses, key=lambda r: r.status_code)
    assert_problem(conflict, 409, "cq.check_running")
    checks = schemas.CqCheckList.model_validate(accepted.json()).checks
    assert [c.question_id for c in checks] == [first.id, second.id]
    assert all(c.result == "pending" for c in checks)
    assert await counts(db) == (3, 3, 3)
    await listed(demo.client, url, running=True)
    done, _ = await finish(demo, checks[0], "Q1")
    assert done.result == "pass"
    await listed(demo.client, url, running=True)
    assert_problem(await post(demo.client, url + "/check"), 409, "cq.check_running")
    done, _ = await finish(demo, checks[1], "Q5")
    assert done.result == "unanswerable"
    await listed(demo.client, url, running=False)
    restarted = await post(demo.client, url + "/check")
    assert restarted.status_code == 202, restarted.text
    assert await counts(db) == (5, 5, 5)


async def test_bulk_selects_first_fifty_active_questions_and_preserves_user_quota(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings
) -> None:
    demo = qa_demo
    url = collection(demo.steel.ontology.id)
    questions = [await new_question(demo.client, url, f"问题 {i}") for i in range(52)]
    assert (await post(demo.client, item(questions[3].id) + "/archive")).status_code == 200
    end = questions[-1]
    moved = await patch(demo.client, end.id, revision=end.revision, position=questions[1].position)
    assert moved.status_code == 200, moved.text
    active = await listed(demo.client, url)
    assert len(active) == 51
    assert active[1].id == end.id
    settings.qa_running_max = 1
    settings.qa_questions_per_hour = 30
    response = await post(demo.client, url + "/check")
    assert response.status_code == 202, response.text
    checks = schemas.CqCheckList.model_validate(response.json()).checks
    assert [c.question_id for c in checks] == [q.id for q in active[:50]]
    assert all(c.result == "pending" and not c.stale for c in checks)
    queued = (await db.scalars(select(QaQuestionRow))).all()
    assert {(q.id, q.cq_question_id, q.origin, q.status) for q in queued} == {
        (c.qa_question_id, c.question_id, "cq", "queued") for c in checks
    }
    assert await counts(db) == (50, 50, 50)
    assert (await demo.submit("Q1")).status_code == 202
    assert_problem(await demo.submit("Q1"), 429, "qa.rate_limited")


async def test_check_preconditions_leave_no_qa_job_or_check(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = qa_demo
    empty = await add_ontology(db, key="unpublished")
    unpublished = await new_question(demo.client, collection(empty.id), "能回答吗？")
    configured = await case_question(demo, "Q1")
    settings.openai_api_key = None
    monkeypatch.delenv("OP_OPENAI_API_KEY")
    for question, code in ((unpublished, "query.no_release"), (configured, "ai.not_configured")):
        for url in (item(question.id), collection(question.ontology_id)):
            assert_problem(await post(demo.client, url + "/check"), 409, code)
        await listed(demo.client, collection(question.ontology_id), running=False)
    assert await counts(db) == (0, 0, 0)


async def test_new_release_marks_last_check_stale_without_enqueuing(
    checked_demo: QaDemo, db: AsyncSession
) -> None:
    demo = checked_demo
    question = await case_question(demo, "Q1")
    done, _ = await finish(demo, await check_one(demo.client, question.id), "Q1")
    assert done.result == "pass"
    assert not done.stale
    published = await publish(demo.client, demo.steel.ontology, "新版")
    assert published.status_code == 201, published.text
    assert published.json()["version"] > done.release.version
    old = await last(demo, question.id)
    assert old == done.model_copy(update={"stale": True})
    assert await counts(db) == (1, 1, 1)


async def test_release_coverage_reports_removed_elements_and_bindings_without_model_calls(
    qa_demo: QaDemo, db: AsyncSession
) -> None:
    demo = qa_demo
    ontology = demo.steel.ontology
    ids = demo.steel.ids
    url = collection(ontology.id)
    context = await qa_context(db, ontology.id)
    types = await list_types(db, ontology.id)

    async def record_plan(question_id: UUID, case: str) -> None:
        check = await check_one(demo.client, question_id)
        queued = await demo.fetch(check.qa_question_id)
        plan = check_plan(await demo.plan(case), context, context.model, types)
        assert isinstance(plan, QaPlan)
        values = {"status": "answered", "plan": plan, "release": check.release}
        await service.record_result(db, queued.model_copy(update=values))
        await db.commit()

    async def read_coverage(release_id: UUID) -> dict[UUID, schemas.CoverageItem]:
        response = await demo.client.get(url + "/coverage")
        assert response.status_code == 200, response.text
        report = schemas.CqCoverage.model_validate(response.json())
        assert report.release is not None
        assert report.release.id == release_id
        return {i.question_id: i for i in report.items}

    objects = await new_question(demo.client, url, "哪些钢卷？")
    metric = await new_question(demo.client, url, "合格率？")
    never = await new_question(demo.client, url, "尚未检验")
    # An earlier Q3 plan must not make the newer Q2 object plan depend on the metric.
    await record_plan(objects.id, "Q3")
    await record_plan(objects.id, "Q2")
    await record_plan(metric.id, "Q3")
    before = await read_coverage(context.metrics.release.id)
    assert before[objects.id].status == before[metric.id].status == "ok"
    assert before[never.id].status == "never_checked"
    assert not before[never.id].elements
    path = {
        "Heat",
        "CastingSequence",
        "Slab",
        "RollingEvent",
        "Coil",
        "QualityInspection",
        "castIn",
        "producesSlab",
        "rolledIn",
        "producesCoil",
        "inspects",
        "steelGrade",
    }
    for question_id, extra in ((objects.id, "passed"), (metric.id, "inspectionPassRate")):
        elements = before[question_id].elements
        assert {e.id for e in elements} == {UUID(ids[name]) for name in path | {extra}}
        assert all(e.present and e.bound and e.label for e in elements)

    passed_id = UUID(ids["passed"])
    [passed_binding] = [b for b in await bindings(db, ontology) if b.subject_id == passed_id]
    rate = (await elements_by_name(db, ontology))["inspectionPassRate"]
    edits = await save(demo.client, ontology, edit("delete", passed_binding), edit("delete", rate))
    assert edits.status_code == 200, edits.text
    assert edits.json()["merged"], edits.text
    assert await read_coverage(context.metrics.release.id) == before
    published = await publish(demo.client, ontology)
    assert published.status_code == 201, published.text
    after = await read_coverage(UUID(published.json()["id"]))
    assert after[objects.id].status == "binding_missing"
    assert after[metric.id].status == "element_missing"
    [unbound] = [e for e in after[objects.id].elements if not e.bound]
    assert unbound.id == UUID(ids["passed"])
    assert unbound.present
    [missing] = [e for e in after[metric.id].elements if not e.present]
    assert missing.id == rate.id
    assert not missing.bound
    assert await counts(db) == (3, 3, 3)
    assert demo.gateway.calls == []


async def test_roles_token_rejection_and_ontology_scoping(
    client: AsyncClient, db: AsyncSession
) -> None:
    left = await add_ontology(db)
    right = await add_ontology(db, key="second")
    await sign_in(client, db, Role.EDITOR)
    question = await new_question(client, collection(left.id), "左边的问题？")
    await sign_in(client, db, Role.REVIEWER)
    other = await new_question(client, collection(right.id), "右边的问题？")
    url = collection(left.id)
    assert [q.id for q in await listed(client, collection(right.id))] == [other.id]
    unknown = uuid4()
    assert_problem(await client.get(collection(unknown)), 404, "ontology.not_found")
    assert_problem(await patch(client, unknown, revision=1, text="更新"), 404, "cq.not_found")
    for suffix in ("/archive", "/check"):
        assert_problem(await post(client, item(unknown) + suffix), 404, "cq.not_found")
    await sign_in(client, db, Role.VIEWER)
    assert [q.id for q in await listed(client, url)] == [question.id]
    report = await client.get(url + "/coverage")
    assert report.status_code == 200, report.text
    assert [i["questionId"] for i in report.json()["items"]] == [str(question.id)]
    writes = [
        ("POST", url),
        ("PATCH", item(question.id)),
        ("POST", item(question.id) + "/archive"),
        ("POST", url + "/import"),
        ("POST", item(question.id) + "/check"),
        ("POST", url + "/check"),
    ]
    for method, path in writes:
        response = await client.request(method, path, headers=csrf_headers(client))
        assert_problem(response, 403, "auth.forbidden")
    headers = await token_holder(client)
    for method, path in [*writes, ("GET", url), ("GET", url + "/coverage")]:
        response = await client.request(method, path, headers=headers)
        assert_problem(response, 403, "auth.token_not_allowed")
