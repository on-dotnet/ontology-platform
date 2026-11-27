"""Steel quality acceptance, spec 007 section 13.3. Only the model is scripted."""

import json
import re
from collections import Counter
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.ai.prompts import AssistantOut
from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.cq.schemas import CqCheckList
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.schemas import ReleaseRef
from ontology_platform.modules.query.cursor import encode_key
from qa_support import (
    GatewayCall,
    QaDemo,
    inspection_metric_fixture,  # noqa: F401
    qa_demo_fixture,  # noqa: F401
    qa_steel_fixture,  # noqa: F401
)
from test_ai_assistant import operation
from test_ai_qa_gap import execute as execute_gap
from test_ai_qa_gap import proposal, start_gap
from test_ai_qa_prompt_safety import DOCUMENT_BODY, QUOTES, _attach_evidence
from test_connectors_support import cache_table
from test_cq import checked_demo, collection, finish, listed, post  # noqa: F401
from test_cq_import import upload
from test_ontology_bindings_support import (
    foreign_key,
    property_binding,
    relation_binding,
    save,
    table,
    type_binding,
)
from test_ontology_support import accept_and_merge, publish, sign_in
from test_qa_demo_import import FIXTURES
from test_query_paging import SteelObjects

DEFECT_COLUMNS = {
    "defectKind": "defect_type",
    "defectPosition": "position_m",
    "defectSeverity": "severity",
}


async def test_step_1_import_bind_and_publish_v1(
    qa_steel: SteelObjects, client: AsyncClient
) -> None:
    # qa_steel imports the TTL, merges it, submits the fixture bindings and publishes.
    assert qa_steel.release["version"] == 1
    response = await qa_steel.search(client, "QualityInspection", limit=50)
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["release"] == qa_steel.release
    assert len(page["items"]) == 43
    assert page["nextCursor"] is None


@pytest.fixture
def output_texts(qa_demo: QaDemo) -> list[str]:
    outputs: list[str] = []

    async def record_output(call: GatewayCall) -> None:
        result = qa_demo.gateway.outputs[call.purpose]
        assert isinstance(result, call.schema)
        outputs.append(result.model_dump_json())

    qa_demo.gateway.before_call = record_output
    return outputs


@pytest.fixture
async def v2_questions(
    qa_demo: QaDemo, db: AsyncSession, output_texts: list[str]
) -> dict[str, QaQuestion]:
    # Step 1 continues in inspection_metric: submit metrics.toml and publish v2.
    assert qa_demo.steel.release["version"] == 2
    await _attach_evidence(db, qa_demo)
    await sign_in(qa_demo.client, db, Role.EDITOR)
    # Step 2: run the real question jobs with the per-release references and scripts.
    return {case: await qa_demo.run(case) for case in ("Q1", "Q2", "Q3", "Q4", "Q5")}


def _assert_objects(question: QaQuestion, type_id: UUID, keys: list[str]) -> None:
    assert question.answer is not None
    assert question.evidence is not None
    assert question.answer_keys is not None
    expected = {encode_key([key]) for key in keys}
    assert question.answer.facts.count == len(expected)
    assert question.answer_keys.type_id == type_id
    assert set(question.answer_keys.keys) == expected
    objects = {(type_id, key) for key in expected}
    assert {(obj.type_id, obj.key) for obj in question.answer.facts.objects} == objects
    assert {(row.type_id, row.key) for row in question.evidence.rows} == objects


async def test_step_3_five_questions_on_v2(
    qa_demo: QaDemo, v2_questions: dict[str, QaQuestion]
) -> None:
    demo = qa_demo
    ids = {name: UUID(value) for name, value in demo.steel.ids.items()}
    q1, q2, q3, q4, q5 = v2_questions.values()
    for case, question in v2_questions.items():
        assert question.release == ReleaseRef.model_validate(demo.steel.release)
        if case != "Q5":
            assert question.status == "answered", (case, question.error_code)
            assert question.answer is not None
            assert question.answer.text == demo.scripts[case]["answer"]["answer"]
            assert question.evidence is not None
            assert question.evidence.release == question.release

    _assert_objects(q1, ids["Heat"], demo.questions["Q1"]["expect"]["keys"])
    assert q1.answer is not None
    assert q1.answer.facts.count == 18
    assert q1.plan is not None
    assert (q1.plan.hops, q1.plan.target) == ([], 0)
    assert q1.evidence is not None
    heat, grade = ids["Heat"], ids["steelGrade"]
    evidence = {e.id: e for e in q1.evidence.elements}
    assert {heat, grade} <= evidence.keys()
    assert [doc.quote for doc in evidence[heat].documents] == list(QUOTES[:2])
    [step] = q1.evidence.steps
    assert (step.type_id, step.conditions, step.rows) == (heat, ["钢种 = Q235B"], 18)
    # Inspect the wire representation so an extra API field cannot be lost in parsing.
    response = await demo.client.get(f"/api/qa/questions/{q1.id}")
    assert response.status_code == 200, response.text
    sources = response.json()["evidence"]["bindings"]
    assert sources == [{"schema": "mes", "table": "heat", "keyColumns": ["heat_no"]}]
    assert "steel_grade" not in json.dumps(sources)

    _assert_objects(q2, ids["Coil"], ["W240101201", "W240101503"])
    assert q2.plan is not None
    assert q2.plan.target == 4
    assert q2.evidence is not None
    chain = [
        ("castIn", "out", "CastingSequence"),
        ("producesSlab", "out", "Slab"),
        ("rolledIn", "out", "RollingEvent"),
        ("producesCoil", "out", "Coil"),
        ("inspects", "in", "QualityInspection"),
    ]
    assert [(h.relation_id, h.direction, h.target_type_id) for h in q2.plan.hops] == [
        (ids[relation], direction, ids[dest]) for relation, direction, dest in chain
    ]
    assert len(q2.evidence.tail) == 3
    assert all(row.type_id == ids["QualityInspection"] for row in q2.evidence.tail)
    assert len({row.key for row in q2.evidence.tail}) == 3
    assert Counter(row.via[4] for row in q2.evidence.tail) == {
        encode_key(["W240101201"]): 2,
        encode_key(["W240101503"]): 1,
    }

    assert q3.answer is not None
    assert q3.answer.facts.metric is not None
    assert (q3.answer.facts.metric.label, q3.answer.facts.metric.display) == ("检验合格率", "92.3%")
    assert q3.evidence is not None
    assert q3.evidence.metric is not None
    metric = q3.evidence.metric
    assert metric.metric_id == demo.metric_id
    assert metric.metric_id in {e.id for e in q3.evidence.elements}
    assert (metric.matched, metric.population, metric.display) == (36, 39, "92.3%")
    assert [step.rows for step in metric.steps] == [39, 36]

    assert q4.answer is not None
    assert q4.answer.facts.violations == 3
    assert q4.evidence is not None
    assert q4.evidence.rules is not None
    rules = {r.constraint_id: r for r in q4.evidence.rules.results}
    assert {id_: r.violations for id_, r in rules.items()} == {
        ids["YieldStrengthShape"]: 3,
        ids["TensileStrengthShape"]: 0,
        ids["ElongationShape"]: 0,
        ids["ImpactEnergyShape"]: 0,
    }
    failed = rules[ids["YieldStrengthShape"]]
    assert failed.constraint_id in {e.id for e in q4.evidence.elements if e.kind == "constraint"}
    assert failed.message == "资料 04 第 2 节：ReH ≥ 235 MPa。"
    assert Counter(f.actual for s in failed.samples for f in s.failed) == {229: 2, 230: 1}

    assert q5.status == "unanswerable"
    assert q5.answer is None
    assert q5.gaps is not None
    assert {(e.kind, e.label_zh) for e in q5.gaps.elements} == {
        ("entity_type", "表面缺陷"),
        ("relation_type", "钢卷表面缺陷"),
    }
    relation = next(e for e in q5.gaps.elements if e.kind == "relation_type")
    assert ids["Coil"] in {ref.id for ref in relation.near}


def _assistant_output(demo: QaDemo) -> AssistantOut:
    script = demo.scripts["Q5"]["proposal"]
    ops = []
    for entry in script["operations"]:
        fields = entry["fields"].copy()
        if fields.get("domain") == "T2":
            fields["domain"] = demo.steel.ids[demo.scripts["refs"]["T2"]]
        ops.append(operation(entry["op"], entry["kind"], temp_ref=entry.get("temp_ref"), **fields))
    return AssistantOut(reply=script["reply"], operations=ops)


async def _pending_proposal(demo: QaDemo, db: AsyncSession, q5: QaQuestion) -> UUID:
    await start_gap(demo, q5)
    await execute_gap(demo, q5, _assistant_output(demo))
    gap = await proposal(demo, q5)
    assert (gap.status, gap.dropped, gap.error_code) == ("done", 0, None)
    assert gap.change_set_id is not None
    response = await demo.client.get(f"/api/change-sets/{gap.change_set_id}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert (detail["source"], detail["status"], detail["createdBy"]) == (
        "ai_qa",
        "open",
        str(q5.asked_by.id),
    )
    items = detail["items"]
    assert len(items) == 5
    assert all(i["op"] == "create" and i["decision"] == "pending" for i in items)
    assert {(i["kind"], i["proposed"]["labelZh"]) for i in items} == {
        ("entity_type", "表面缺陷"),
        ("property", "缺陷类型"),
        ("property", "位置"),
        ("property", "严重程度"),
        ("relation_type", "钢卷表面缺陷"),
    }
    draft = await demo.client.get(f"/api/ontologies/{q5.ontology_id}/elements")
    assert draft.status_code == 200, draft.text
    assert "表面缺陷" not in {e["labelZh"] for e in draft.json()}
    active = await bindings.released_ontology(db, q5.ontology_id)
    assert active is not None
    assert str(active.release_id) == demo.steel.release["id"]
    assert "表面缺陷" not in {e.label_zh for e in active.elements}
    return gap.change_set_id


async def _review_bind_publish(
    demo: QaDemo, db: AsyncSession, external: ExternalSource, change_id: UUID
) -> ReleaseRef:
    client, steel = demo.client, demo.steel
    await sign_in(client, db, Role.REVIEWER)
    assert (await accept_and_merge(client, change_id))["skipped"] == []
    working = await client.get(f"/api/ontologies/{steel.ontology.id}/elements")
    assert working.status_code == 200, working.text
    ids = {row["localName"]: row["id"] for row in working.json() if row["localName"]}
    model = await bindings.bound_model(db, steel.ontology.id)
    assert model is not None
    coil = model.type(UUID(ids["Coil"]))
    assert coil is not None
    source_id = UUID(steel.source_id)
    await cache_table(db, source_id, external, "mes", "surface_defect")
    edits = [
        type_binding(
            ids["SurfaceDefect"], table(source_id, "surface_defect", ["defect_id"]), "defect"
        ),
        *(property_binding(ids[name], "defect", column) for name, column in DEFECT_COLUMNS.items()),
        relation_binding(
            ids["hasSurfaceDefect"],
            str(coil.binding_id),
            "defect",
            foreign_key(["coil_no"], ["coil_no"], side="target"),
        ),
    ]
    await sign_in(client, db, Role.EDITOR)
    saved = await save(client, steel.ontology, edits, apply=False)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"] is False
    await sign_in(client, db, Role.REVIEWER)
    assert (await accept_and_merge(client, UUID(saved.json()["changeSetId"])))["skipped"] == []
    result = await publish(client, steel.ontology, "v3")
    assert result.status_code == 201, result.text
    release = ReleaseRef(id=UUID(result.json()["id"]), version=result.json()["version"])
    assert release.version == 3
    await sign_in(client, db, Role.EDITOR)
    # Keep the original Q5 text. Its script now refers to the newly published elements.
    steel.ids.update(ids)
    after = demo.scripts["Q5_after"]
    demo.scripts["refs"].update(after["refs"])
    demo.scripts["Q5"] = after
    return release


async def _all_checks(demo: QaDemo, release: ReleaseRef) -> None:
    url = collection(demo.steel.ontology.id)
    content = (FIXTURES / "questions.toml").read_bytes()
    imported = await upload(demo.client, url + "/import", content)
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"created": 5, "skipped": 0}
    rows = await listed(demo.client, url)
    cases = {q["text"]: case for case, q in demo.questions.items()}
    assert {row.text for row in rows} == cases.keys()
    by_id = {row.id: cases[row.text] for row in rows}
    response = await post(demo.client, url + "/check")
    assert response.status_code == 202, response.text
    checks = CqCheckList.model_validate(response.json()).checks
    assert len(checks) == 5
    assert {c.question_id for c in checks} == by_id.keys()
    for check in checks:
        done, answer = await finish(demo, check, by_id[check.question_id])
        assert (answer.origin, answer.cq_question_id) == ("cq", check.question_id)
        assert done.release == answer.release == release
    final = await listed(demo.client, url, running=False)
    assert len(final) == 5
    for row in final:
        assert row.last_check is not None
        assert row.last_check.result == "pass", (row.text, row.last_check.detail)
        assert row.last_check.release == release
        assert not row.last_check.stale


async def _assert_private_inputs(
    demo: QaDemo, db: AsyncSession, external: ExternalSource, outputs: list[str]
) -> None:
    ontology = await bindings.released_ontology(db, demo.steel.ontology.id)
    model = await bindings.bound_model(db, demo.steel.ontology.id)
    assert ontology is not None
    assert model is not None
    english = {e.id: e.label_en or e.local_name or "" for e in ontology.elements}
    columns = {
        p.column
        for t in model.types
        for p in t.properties
        if p.column.casefold() != english[p.property_id].casefold()
    }
    assert {"steel_grade", "defect_type", "position_m"} <= columns
    tokens = {"mes", *columns, external.host, str(external.port)}
    private_text = (
        demo.steel.source_name,
        external.database,
        external.reader,
        DOCUMENT_BODY,
        *QUOTES,
    )
    calls = demo.gateway.calls
    assert Counter(c.purpose for c in calls) == {"qa.plan": 11, "qa.answer": 10, "qa.gap": 1}
    contents = list(outputs)
    for call in calls:
        assert not call.files
        assert call.document_id is None
        contents.extend((call.instructions, call.text))
        if call.purpose in ("qa.plan", "qa.answer"):
            payload = json.loads(call.text)
            assert payload["question"] in {q["text"] for q in demo.questions.values()}
            contents.append(json.dumps(payload, ensure_ascii=False))
    for content in contents:
        # The word boundary catches mes.heat and "mes"."heat" but allows "message".
        for token in tokens:
            assert not re.search(rf"(?<!\w){re.escape(token)}(?!\w)", content, re.I)
        for private in private_text:
            assert private.casefold() not in content.casefold()


@pytest.mark.usefixtures("checked_demo")
async def test_steps_2_to_7_review_reask_and_check_all(
    qa_demo: QaDemo,
    v2_questions: dict[str, QaQuestion],
    output_texts: list[str],
    db: AsyncSession,
    external_source: ExternalSource,
) -> None:
    demo = qa_demo
    q5 = v2_questions["Q5"]
    # Step 4: generating the proposal leaves both the working and active ontology alone.
    change_id = await _pending_proposal(demo, db, q5)
    # Step 5: human review, binding review, release and re-ask with identical wording.
    release = await _review_bind_publish(demo, db, external_source, change_id)
    again = await demo.run("Q5")
    assert (again.question, again.release, again.status) == (q5.question, release, "answered")
    assert again.id != q5.id
    _assert_objects(again, UUID(demo.steel.ids["SurfaceDefect"]), ["2401000003", "2401000004"])
    assert again.evidence is not None
    assert again.answer is not None
    kind, severity = (UUID(demo.steel.ids[n]) for n in ("defectKind", "defectSeverity"))
    assert {(r.values[kind], r.values[severity]) for r in again.evidence.rows} == {
        ("边裂", "严重"),
        ("结疤", "一般"),
    }
    assert again.answer.text == demo.scripts["Q5"]["answer"]["answer"]
    # Step 6 runs the real completion listener registered by checked_demo.
    await _all_checks(demo, release)
    # Step 7 covers the original questions, proposal, re-ask and every CQ job.
    assert len(output_texts) == len(demo.gateway.calls)
    await _assert_private_inputs(demo, db, external_source, output_texts)
