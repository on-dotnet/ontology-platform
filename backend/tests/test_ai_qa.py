import asyncio
import re
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa
from ontology_platform.modules.ai.gateway import AiInvalidOutputError, AiUnavailableError
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.ai.qa_prompts import QaAnswerOut, QaPlanOut
from ontology_platform.modules.ai.schemas import QaQuestionCreate
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.statements import Rows, SelectQuery
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import RetryableJobError
from ontology_platform.modules.query import cursor, scan
from ontology_platform.modules.query import service as query
from ontology_platform.modules.query.schemas import ObjectTypeList, PathRow
from ontology_platform.settings import Settings
from qa_support import (
    GatewayCall,
    QaDemo,
    inspection_metric_fixture,  # noqa: F401
    qa_demo_fixture,  # noqa: F401
    qa_steel_fixture,  # noqa: F401
)
from query_path_support import demo_path
from support import csrf_headers
from test_ontology_editing import create, save
from test_ontology_support import add_ontology, elements_by_name, publish, sign_in
from test_query_support import assert_problem


@pytest.mark.parametrize("intent", ["objects", "count"])
async def test_q1_zero_hop_heat_facts_and_bindings(qa_demo: QaDemo, intent: str) -> None:
    plan = (await qa_demo.plan("Q1")).model_copy(update={"intent": intent})
    result = await qa_demo.run("Q1", plan=plan)
    assert result.status == "answered"
    assert result.plan is not None
    assert result.plan.hops == []
    assert result.plan.target == 0
    assert result.answer is not None
    assert result.answer.facts.count == 18
    assert result.evidence is not None
    assert result.evidence.release == result.release
    heat = UUID(qa_demo.steel.ids["Heat"])
    grade = UUID(qa_demo.steel.ids["steelGrade"])
    assert {heat, grade} <= {e.id for e in result.evidence.elements}
    assert [b.model_dump(by_alias=True) for b in result.evidence.bindings] == [
        {"schema": "mes", "table": "heat", "keyColumns": ["heat_no"]}
    ]
    [step] = result.evidence.steps
    assert (step.type_id, step.rows, step.conditions) == (heat, 18, ["钢种 = Q235B"])
    expected = {cursor.encode_key([key]) for key in qa_demo.questions["Q1"]["expect"]["keys"]}
    assert result.answer_keys is not None
    assert result.answer_keys.type_id == heat
    assert set(result.answer_keys.keys) == expected
    assert {row.key for row in result.evidence.rows} == expected
    if intent == "objects":
        assert {obj.key for obj in result.answer.facts.objects} == expected


async def test_q2_middle_target_tail_and_gateway_text(qa_demo: QaDemo) -> None:
    result = await qa_demo.run("Q2")
    assert result.status == "answered"
    assert result.plan is not None
    assert result.plan.target == 4
    ids = qa_demo.steel.ids
    assert [(hop.relation_id, hop.direction) for hop in result.plan.hops] == [
        (UUID(ids[name]), "in" if name == "inspects" else "out")
        for name in ("castIn", "producesSlab", "rolledIn", "producesCoil", "inspects")
    ]
    assert result.answer is not None
    assert result.evidence is not None
    coils = {cursor.encode_key([key]) for key in ("W240101201", "W240101503")}
    tail = {
        cursor.encode_key([f"24010000-0000-4000-8000-000000000{n}"]) for n in ("341", "342", "451")
    }
    assert result.answer.facts.count == 2
    assert {(obj.type_id, obj.key) for obj in result.answer.facts.objects} == {
        (UUID(ids["Coil"]), key) for key in coils
    }
    assert {row.key for row in result.evidence.rows} == coils
    assert {row.key for row in result.evidence.tail} == tail
    assert all(row.type_id == UUID(ids["QualityInspection"]) for row in result.evidence.tail)
    assert all(row.via[4] in coils and row.via[5] == row.key for row in result.evidence.tail)
    assert result.answer_keys is not None
    assert result.answer_keys.type_id == UUID(ids["Coil"])
    assert set(result.answer_keys.keys) == coils
    assert result.answer.counterpoints == ["W240101201 有两次检验都不合格。"]
    assert set(result.answer.cited_keys) == coils
    plan, answer = qa_demo.gateway.calls
    assert (plan.purpose, plan.schema) == ("qa.plan", QaPlanOut)
    assert (answer.purpose, answer.schema) == ("qa.answer", QaAnswerOut)


async def test_q3_metric_population_and_numerator_scans(qa_demo: QaDemo) -> None:
    result = await qa_demo.run("Q3")
    assert result.status == "answered"
    assert result.answer is not None
    assert result.evidence is not None
    fact = result.answer.facts.metric
    assert fact is not None
    assert (fact.label, fact.display) == ("检验合格率", "92.3%")
    metric = result.evidence.metric
    assert metric is not None
    assert metric.metric_id == qa_demo.metric_id
    assert (metric.matched, metric.population, metric.display) == (36, 39, "92.3%")
    assert [s.rows for s in metric.steps] == [39, 36]
    assert result.evidence.steps[-2:] == metric.steps
    assert metric.metric_id in {element.id for element in result.evidence.elements}


async def test_q4_violations_and_clause_evidence(qa_demo: QaDemo) -> None:
    result = await qa_demo.run("Q4")
    assert result.status == "answered"
    assert result.answer is not None
    assert result.evidence is not None
    assert result.answer.facts.violations == 3
    rules = result.evidence.rules
    assert rules is not None
    assert (rules.scanned, rules.checked_rules) == (39, 4)
    by_shape = {r.constraint_id: r for r in rules.results}
    ids = qa_demo.steel.ids
    assert {key: r.violations for key, r in by_shape.items()} == {
        UUID(ids["YieldStrengthShape"]): 3,
        UUID(ids["TensileStrengthShape"]): 0,
        UUID(ids["ElongationShape"]): 0,
        UUID(ids["ImpactEnergyShape"]): 0,
    }
    failed = by_shape[UUID(ids["YieldStrengthShape"])]
    assert failed.message == "资料 04 第 2 节：ReH ≥ 235 MPa。"
    assert [f.actual for row in failed.samples for f in row.failed] == [229, 230, 229]
    constraints = {e.id for e in result.evidence.elements if e.kind == "constraint"}
    assert failed.constraint_id in constraints


@pytest.mark.parametrize("case", ["model-missing", "unknown-reference", "missing-binding"])
async def test_unanswerable_skips_query_and_answer(
    qa_demo: QaDemo, db: AsyncSession, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    read = AsyncMock(wraps=query._read)
    monkeypatch.setattr(query, "_read", read)
    question = "Q5" if case == "model-missing" else "Q1"
    plan = await qa_demo.plan(question)
    unbound = None
    if case == "missing-binding":
        ontology = qa_demo.steel.ontology
        saved = await save(qa_demo.client, ontology, create("entity_type", "Furnace", "熔炉"))
        assert saved.status_code == 200
        assert saved.json()["merged"]
        assert (await publish(qa_demo.client, ontology)).status_code == 201
        unbound = (await elements_by_name(db, ontology))["Furnace"].id
        plan = plan.model_copy(update={"start": await qa_demo.ref_for(unbound), "filters": []})
    elif case == "unknown-reference":
        plan = plan.model_copy(update={"start": "T999", "filters": []})
    result = await qa_demo.run(question, plan=plan)
    assert result.status == "unanswerable"
    assert result.gaps is not None
    assert result.answer is None
    assert result.evidence is None
    if case == "model-missing":
        assert {(e.kind, e.label_zh) for e in result.gaps.elements} == {
            ("entity_type", "表面缺陷"),
            ("relation_type", "钢卷表面缺陷"),
        }
        relation = next(e for e in result.gaps.elements if e.kind == "relation_type")
        assert [r.id for r in relation.near] == [UUID(qa_demo.steel.ids["Coil"])]
        assert result.gaps.bindings == []
    elif case == "unknown-reference":
        assert [e.kind for e in result.gaps.elements] == ["entity_type"]
        assert result.gaps.bindings == []
    else:
        assert result.gaps.elements == []
        assert [(b.type_id, b.label) for b in result.gaps.bindings] == [(unbound, "熔炉")]
    read.assert_not_awaited()
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan"]


@pytest.mark.parametrize("case", ["value", "opaque-contains", "target", "six-hops", "filters"])
async def test_invalid_plan_skips_query_and_answer(
    qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    plan = await qa_demo.plan("Q2")
    if case == "value":
        plan.path[-1].filters[0].value = "perhaps"
    elif case == "opaque-contains":
        coil = await qa_demo.ref_for(UUID(qa_demo.steel.ids["Coil"]))
        status = await qa_demo.ref_for(UUID(qa_demo.steel.ids["coilStatus"]))
        condition = plan.filters[0].model_copy(update={"property": status, "op": "contains"})
        plan = plan.model_copy(
            update={"start": coil, "path": [], "target": 0, "filters": [condition]}
        )
    elif case == "target":
        plan.target = 6
    elif case == "six-hops":
        plan.path.append(plan.path[-1].model_copy(update={"direction": "out", "filters": []}))
    else:
        plan.filters = plan.filters * 11
    read = AsyncMock(wraps=query._read)
    monkeypatch.setattr(query, "_read", read)
    result = await qa_demo.run("Q2", plan=plan)
    assert (result.status, result.error_code) == ("failed", "qa.invalid_plan")
    assert result.gaps is None
    assert result.answer is None
    assert result.evidence is None
    read.assert_not_awaited()
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan"]


@pytest.mark.parametrize("case", ["answer-error", "unknown-key", "samples-off"])
async def test_answer_preserves_facts_and_maps_citations(qa_demo: QaDemo, case: str) -> None:
    answer: QaAnswerOut | AiInvalidOutputError
    answer = QaAnswerOut(answer="检测到异常。", cited_keys=["K1", "K5", "K6"], counterpoints=[])
    if case == "answer-error":
        answer = AiInvalidOutputError("scripted answer error", retryable=False)
    if case == "samples-off":
        await qa_demo.allow_samples(False)
    result = await qa_demo.run("Q2", answer=answer)
    assert result.status == "answered"
    assert result.answer is not None
    assert result.evidence is not None
    assert result.answer.facts.count == len(result.evidence.rows) == 2
    assert len(result.evidence.tail) == 3
    if case == "unknown-key":
        assert result.answer.text == "检测到异常。"
        assert result.answer.cited_keys == [
            result.evidence.rows[0].key,
            result.evidence.tail[2].key,
        ]
        assert "cited_unknown" in result.answer.notes
    else:
        assert result.answer.text is None
        assert result.answer.cited_keys == []
        assert ("answer_unavailable" if case == "answer-error" else "rows_not_shared") in (
            result.answer.notes
        )
    purposes = ["qa.plan"] if case == "samples-off" else ["qa.plan", "qa.answer"]
    assert [c.purpose for c in qa_demo.gateway.calls] == purposes


def _name(row: PathRow) -> str:
    return " / ".join(k.value for k in row.source.key)


async def test_the_conclusion_names_objects_instead_of_row_refs(qa_demo: QaDemo) -> None:
    # #128: with a real model the conclusion called the objects K1, K2, which readers cannot
    # follow; the platform puts the object names back.
    answer = QaAnswerOut(
        answer="检验不合格的钢卷有 K1 和 K2（K1、K2）。K1 有两次检验不合格（K3\u2013K4）。",
        cited_keys=["K1", "K2"],
        counterpoints=["K1 有两次检验都不合格（见 K3）。"],
    )
    result = await qa_demo.run("Q2", answer=answer)
    assert result.answer is not None
    assert result.evidence is not None
    first, second = (_name(row) for row in result.evidence.rows)
    assert result.answer.text == (
        f"检验不合格的钢卷有 {first} 和 {second}。{first} 有两次检验不合格。"
    )
    assert result.answer.counterpoints == [
        f"{first} 有两次检验都不合格（见 {_name(result.evidence.tail[0])}）。"
    ]
    for text in [result.answer.text, *result.answer.counterpoints]:
        assert not re.search(r"(?<![A-Za-z0-9])K\d+(?![A-Za-z0-9])", text)
    assert result.answer.notes == []


async def test_a_clause_with_an_unknown_row_ref_is_dropped(qa_demo: QaDemo) -> None:
    answer = QaAnswerOut(
        answer="检验不合格的钢卷共 2 个，其中 K9 需要复查。K1 有两次检验不合格。",
        cited_keys=["K1"],
        counterpoints=["K7 需要复查。", "K1 需要复检。"],
    )
    result = await qa_demo.run("Q2", answer=answer)
    assert result.answer is not None
    assert result.evidence is not None
    first = _name(result.evidence.rows[0])
    assert result.answer.text == f"检验不合格的钢卷共 2 个。{first} 有两次检验不合格。"
    assert result.answer.counterpoints == [f"{first} 需要复检。"]
    assert result.answer.notes == ["cited_unknown"]


async def test_a_conclusion_made_only_of_unknown_row_refs_is_not_shown(qa_demo: QaDemo) -> None:
    answer = QaAnswerOut(
        answer="K9 检验不合格。", cited_keys=["K1"], counterpoints=["K1 需要复检。"]
    )
    result = await qa_demo.run("Q2", answer=answer)
    assert result.answer is not None
    assert result.answer.text is None
    assert result.answer.counterpoints == []
    assert result.answer.cited_keys == []
    assert "answer_unavailable" in result.answer.notes
    assert "cited_unknown" in result.answer.notes
    assert result.answer.facts.count == 2


async def test_a_thousands_separator_does_not_split_a_clause(qa_demo: QaDemo) -> None:
    answer = QaAnswerOut(answer="K9 共 1,200 次，K1 合格。", cited_keys=["K1"], counterpoints=[])
    result = await qa_demo.run("Q2", answer=answer)
    assert result.answer is not None
    assert result.evidence is not None
    assert result.answer.text == f"{_name(result.evidence.rows[0])} 合格。"
    assert result.answer.notes == ["cited_unknown"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "牌号 Q235B 的炉次共有 18 个。结果未提供具体炉次编号，无法逐一列出。",
            "牌号 Q235B 的炉次共有 18 个。",
        ),
        # The number stays when the denial shares its sentence.
        ("共有 18 个炉次，无法逐一列出。", "共有 18 个炉次。"),
        ("共有 18 个炉次，无法给出每个炉次的编号。", "共有 18 个炉次。"),
        ("共有 18 个炉次，无法提供具体编号。", "共有 18 个炉次。"),
        ("共有 18 个炉次，没有展示编号。", "共有 18 个炉次。"),
        ("共有 18 个炉次，不便逐一列出。", "共有 18 个炉次。"),
        ("共有 18 个炉次，未列出所有炉次。", "共有 18 个炉次。"),
        (
            "共有 18 个炉次；结果不包含具体的缺陷位置。",
            "共有 18 个炉次；结果不包含具体的缺陷位置。",
        ),
        # Facts about the objects are not denials of the list.
        ("检验不合格的炉次已列出清单。", "检验不合格的炉次已列出清单。"),
        ("有 2 个炉次未包含在检验清单中。", "有 2 个炉次未包含在检验清单中。"),
        ("结果中没有给出炉次的编号清单。", None),
    ],
)
async def test_the_conclusion_does_not_deny_the_listed_objects(
    qa_demo: QaDemo, text: str, expected: str | None
) -> None:
    # #128: the facts listed all 18 heats while the conclusion said it could not list them.
    answer = QaAnswerOut(
        answer=text, cited_keys=[], counterpoints=["无法列出每个炉次。", "炉次分属两个工厂。"]
    )
    result = await qa_demo.run("Q1", answer=answer)
    assert result.answer is not None
    assert len(result.answer.facts.objects) == result.answer.facts.count == 18
    assert result.answer.text == expected
    # A conclusion that says nothing else is not shown, like a failed answer call.
    assert result.answer.counterpoints == (["炉次分属两个工厂。"] if expected else [])
    assert ("answer_unavailable" in result.answer.notes) == (expected is None)


async def test_a_truncated_input_may_say_the_list_is_not_complete(
    qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    # All 18 heats are listed, but a cut value means the model did not see all of each row.
    async def long_values(session: AsyncSession, statement: SelectQuery) -> Rows:
        rows = []
        for n in range(1, 19):
            values = {
                "heat_no": f"H24010{n:02}",
                "steel_grade": "Q235B",
                "org_id": "O" * 201,
                "site_id": "S1",
            }
            rows.append(tuple(values[column.name] for column in statement.columns))
        return Rows(tuple(rows), has_more=False)

    monkeypatch.setattr(connectors, "select", long_values)
    text = "共有 18 个炉次，结果有截断，无法全部列出。"
    result = await qa_demo.run(
        "Q1", answer=QaAnswerOut(answer=text, cited_keys=[], counterpoints=[])
    )
    assert result.answer is not None
    assert len(result.answer.facts.objects) == result.answer.facts.count == 18
    assert "rows_truncated" in result.answer.notes
    assert result.answer.text == text


async def test_one_statement_budget_across_two_reads(
    qa_demo: QaDemo, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scan, "STATEMENTS_MAX", 1)
    path = demo_path(qa_demo.steel)
    path.hops = []
    ontology_id = qa_demo.steel.ontology.id
    assert (await query.traverse(db, ontology_id, path)).total == 18
    assert len((await query.traverse_keys(db, ontology_id, path)).keys) == 18
    read = AsyncMock(wraps=query._read)
    monkeypatch.setattr(query, "_read", read)
    result = await qa_demo.run("Q1")
    assert (result.status, result.error_code) == ("failed", "qa.too_many_queries")
    read.assert_awaited_once()
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan"]


async def test_full_answer_keys_survive_evidence_truncation(
    qa_demo: QaDemo, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    heats = [f"H{i:07}" for i in range(101)]

    async def large_page(session: AsyncSession, statement: SelectQuery) -> Rows:
        assert statement.table.name == "heat"
        assert statement.limit >= len(heats)
        rows = []
        for key in heats:
            values = {"heat_no": key, "steel_grade": "Q235B", "org_id": "ORG01", "site_id": "S1"}
            rows.append(tuple(values[column.name] for column in statement.columns))
        return Rows(tuple(rows), has_more=False)

    monkeypatch.setattr(connectors, "select", large_page)
    answer = QaAnswerOut(answer="结果较多。", cited_keys=["K50", "K51"], counterpoints=[])
    result = await qa_demo.run("Q1", answer=answer)
    assert result.status == "answered"
    assert result.answer is not None
    assert result.evidence is not None
    assert result.answer.facts.count == 101
    assert result.evidence.truncated
    assert len(result.evidence.rows) == len(result.answer.facts.objects) == 50
    assert result.answer.cited_keys == [result.evidence.rows[49].key]
    assert {"rows_truncated", "cited_unknown"} <= set(result.answer.notes)
    assert result.answer_keys is not None
    assert result.answer_keys.type_id == UUID(qa_demo.steel.ids["Heat"])
    keys = {cursor.encode_key([key]) for key in heats}
    assert set(result.answer_keys.keys) == keys
    row = await db.get(QaQuestionRow, result.id)
    assert row is not None
    assert row.answer_keys is not None
    assert row.answer_keys["typeId"] == qa_demo.steel.ids["Heat"]
    assert set(row.answer_keys["keys"]) == keys


async def test_job_timeout_during_plan(qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OP_QA_JOB_TIMEOUT_SECONDS", "3")
    entered = asyncio.Event()

    async def wait_for_timeout(call: GatewayCall) -> None:
        assert call.purpose == "qa.plan"
        entered.set()
        await asyncio.Event().wait()

    qa_demo.gateway.before_call = wait_for_timeout
    async with asyncio.timeout(20):
        result = await qa_demo.run("Q1")
    assert entered.is_set()
    assert (result.status, result.error_code) == ("failed", "qa.timeout")
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan"]


async def test_worker_progress_visible_to_polling_client(
    qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch
) -> None:
    queued = await qa_demo.queue("Q1")
    qa_demo.gateway.outputs = {
        "qa.plan": await qa_demo.plan("Q1"),
        "qa.answer": QaAnswerOut.model_validate(qa_demo.scripts["Q1"]["answer"]),
    }
    seen: list[str | None] = []

    async def observe() -> None:
        current = await qa_demo.fetch(queued.id)
        assert current.status == "running"
        if not seen or seen[-1] != current.step:
            seen.append(current.step)

    list_types = query.list_types
    select_rows = connectors.select

    async def at_check(db: AsyncSession, ontology_id: UUID) -> ObjectTypeList:
        await observe()
        return await list_types(db, ontology_id)

    async def at_query(db: AsyncSession, statement: SelectQuery) -> Rows:
        await observe()
        return await select_rows(db, statement)

    async def at_model_call(call: GatewayCall) -> None:
        await observe()
        assert seen[-1] == {"qa.plan": "plan", "qa.answer": "answer"}[call.purpose]

    qa_demo.gateway.before_call = at_model_call
    monkeypatch.setattr(query, "list_types", at_check)
    monkeypatch.setattr(connectors, "select", at_query)
    await qa_demo.execute(queued.id)
    assert seen == ["plan", "check", "query", "answer"]
    done = await qa_demo.fetch(queued.id)
    assert (done.status, done.step) == ("answered", "done")


@pytest.mark.parametrize(
    ("stage", "code"),
    [
        ("qa.plan", "ai.unavailable"),
        ("qa.answer", "ai.unavailable"),
        ("query", "query.busy"),
        ("query", "query.source_unavailable"),
    ],
)
async def test_retry_requeues_and_final_attempt_fails(
    qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch, stage: str, code: str
) -> None:
    qa_demo.gateway.outputs["qa.plan"] = await qa_demo.plan("Q1")
    if stage == "query":
        monkeypatch.setattr(query, "_read", AsyncMock(side_effect=AppError(503, code, "busy")))
    else:
        qa_demo.gateway.outputs[stage] = AiUnavailableError("scripted outage", retryable=True)
    queued = await qa_demo.queue("Q1")
    with pytest.raises(RetryableJobError) as retry:
        await qa_demo.execute(queued.id)
    assert retry.value.code == code
    current = await qa_demo.fetch(queued.id)
    assert current.status == "queued"
    assert current.finished_at is None
    assert qa_demo.completed == []
    with pytest.raises(RetryableJobError) as exhausted:
        await qa_demo.execute(queued.id, attempts=3, max_attempts=3)
    assert exhausted.value.code == code
    final = await qa_demo.fetch(queued.id)
    assert (final.status, final.error_code) == ("failed", code)
    assert [q.id for q in qa_demo.completed] == [queued.id]
    calls = ["qa.plan", "qa.answer"] if stage == "qa.answer" else ["qa.plan"]
    assert [c.purpose for c in qa_demo.gateway.calls] == calls * 2


@pytest.mark.parametrize("code", ["ai.invalid_output", "query.timeout"])
async def test_terminal_errors_keep_original_code(
    qa_demo: QaDemo, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    if code == "ai.invalid_output":
        result = await qa_demo.run("Q1", plan=AiInvalidOutputError("invalid", retryable=False))
    else:
        monkeypatch.setattr(scan, "QUERY_SECONDS", 0)
        result = await qa_demo.run("Q1")
    assert (result.status, result.error_code) == ("failed", code)
    assert [call.purpose for call in qa_demo.gateway.calls] == ["qa.plan"]


async def test_release_pinned_before_model_returns(qa_demo: QaDemo) -> None:
    ontology = qa_demo.steel.ontology

    async def publish_revision(call: GatewayCall) -> None:
        assert call.purpose == "qa.plan"
        saved = await save(qa_demo.client, ontology, create("entity_type", "Furnace", "熔炉"))
        assert saved.status_code == 200
        assert saved.json()["merged"]
        assert (await publish(qa_demo.client, ontology)).status_code == 201

    qa_demo.gateway.before_call = publish_revision
    result = await qa_demo.run("Q1")
    assert (result.status, result.error_code) == ("failed", "query.release_changed")
    assert result.release is not None
    assert result.release.model_dump(mode="json") == qa_demo.steel.release
    assert [call.purpose for call in qa_demo.gateway.calls] == ["qa.plan"]


async def test_listener_errors_and_idempotent_redelivery(qa_demo: QaDemo) -> None:
    qa_demo.break_listener = True
    result = await qa_demo.run("Q1")
    assert result.status == "answered"
    assert result.answer_keys is not None
    assert len(result.answer_keys.keys) == 18
    assert qa_demo.broken_calls == [result.id]
    with pytest.raises(ValidationError, match="frozen"):
        result.status = "failed"
    await qa_demo.execute(result.id, attempts=2)
    assert qa_demo.completed == [result]
    assert qa_demo.broken_calls == [result.id]
    assert [c.purpose for c in qa_demo.gateway.calls] == ["qa.plan", "qa.answer"]
    assert (await qa_demo.fetch(result.id)).finished_at == result.finished_at


async def counts(db: AsyncSession) -> tuple[int | None, int | None]:
    rows = await db.scalar(select(func.count()).select_from(QaQuestionRow))
    jobs = await db.scalar(select(func.count()).select_from(Job).where(Job.kind == qa.JOB_KIND))
    return rows, jobs


def assert_limited(response: Response) -> None:
    assert_problem(response, 429, "qa.rate_limited")
    assert int(response.headers["Retry-After"]) > 0


@pytest.mark.parametrize(("hourly", "running"), [(2, 10), (10, 2)])
async def test_concurrent_submissions_enforce_user_limits(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings, hourly: int, running: int
) -> None:
    settings.qa_questions_per_hour = hourly
    settings.qa_running_max = running
    start = asyncio.Barrier(6)

    async def submit() -> Response:
        await start.wait()
        return await qa_demo.submit("Q1")

    responses = await asyncio.gather(*(submit() for _ in range(6)))
    admitted = [r for r in responses if r.status_code == 202]
    assert len(admitted) == 2
    for response in responses:
        if response.status_code != 202:
            assert_limited(response)
    assert await counts(db) == (2, 2)
    await sign_in(qa_demo.client, db, Role.VIEWER)
    assert (await qa_demo.submit("Q1")).status_code == 202


async def test_hour_window_and_running_count_are_independent(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings
) -> None:
    settings.qa_questions_per_hour = settings.qa_running_max = 1
    completed = await qa_demo.run("Q1")
    assert_limited(await qa_demo.submit("Q1"))
    row = await db.get(QaQuestionRow, completed.id)
    assert row is not None
    row.created_at = datetime.now(UTC) - timedelta(hours=2)
    await db.commit()
    queued = await qa_demo.queue("Q1")
    row = await db.get(QaQuestionRow, queued.id)
    assert row is not None
    row.created_at = datetime.now(UTC) - timedelta(hours=2)
    row.status = "running"
    await db.commit()
    assert_limited(await qa_demo.submit("Q2"))
    assert await counts(db) == (2, 2)


async def test_cq_questions_neither_consume_nor_obey_user_limits(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.qa_questions_per_hour = settings.qa_running_max = 1
    monkeypatch.setenv("OP_QA_QUESTIONS_PER_HOUR", "1")
    monkeypatch.setenv("OP_QA_RUNNING_MAX", "1")
    owner = UUID((await qa_demo.client.get("/api/auth/me")).json()["id"])

    async def create_cq() -> None:
        cq_id = uuid4()
        result = await qa.create_question(
            db,
            qa_demo.steel.ontology.id,
            QaQuestionCreate(question="能力问题"),
            user_id=owner,
            origin="cq",
            cq_question_id=cq_id,
        )
        assert (result.origin, result.cq_question_id, result.status) == ("cq", cq_id, "queued")

    await create_cq()
    assert (await qa_demo.submit("Q1")).status_code == 202
    assert_limited(await qa_demo.submit("Q2"))
    await create_cq()
    assert await counts(db) == (3, 3)


async def test_preconditions_leave_no_question_or_job(
    qa_demo: QaDemo, db: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = await add_ontology(db, key="unreleased")
    response = await qa_demo.client.post(
        f"/api/ontologies/{empty.id}/qa/questions",
        json={"question": "哪些钢卷？"},
        headers=csrf_headers(qa_demo.client),
    )
    assert_problem(response, 409, "query.no_release")
    settings.openai_api_key = None
    monkeypatch.delenv("OP_OPENAI_API_KEY")
    assert_problem(await qa_demo.submit("Q1"), 409, "ai.not_configured")
    assert await counts(db) == (0, 0)


async def test_ownership_pagination_and_internal_fields(
    qa_demo: QaDemo, db: AsyncSession, client: AsyncClient
) -> None:
    own = await qa_demo.run("Q1")
    await sign_in(client, db, Role.VIEWER)
    assert_problem(await client.get(f"/api/qa/questions/{own.id}"), 404, "qa.not_found")
    assert_problem(await client.get(qa_demo.url, params={"askedBy": "all"}), 403, "auth.forbidden")
    assert (await client.get(qa_demo.url)).json() == {"items": [], "nextCursor": None}
    other = await qa_demo.queue("Q2")
    assert (await qa_demo.fetch(other.id)).id == other.id
    await sign_in(client, db, Role.ADMIN)
    assert (await qa_demo.fetch(other.id)).id == other.id
    mine = (await client.get(qa_demo.url, params={"askedBy": "me"})).json()
    [item] = mine["items"]
    assert item["id"] == str(own.id)
    assert item["evidence"] is None
    assert "answerKeys" not in item
    assert mine["nextCursor"] is None
    page = (await client.get(qa_demo.url, params={"askedBy": "all", "limit": 1})).json()
    assert [q["id"] for q in page["items"]] == [str(other.id)]
    assert page["nextCursor"]
    page = (
        await client.get(
            qa_demo.url, params={"askedBy": "all", "limit": 1, "cursor": page["nextCursor"]}
        )
    ).json()
    assert [q["id"] for q in page["items"]] == [str(own.id)]
    assert page["nextCursor"] is None
