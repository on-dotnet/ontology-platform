"""Inspect both model calls with real bindings, business rows and document evidence."""

import json
import re
import tomllib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.ai import qa_answer
from ontology_platform.modules.ai.qa_prompts import QaAnswerOut, QaPlanOut
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.models import ChangeItem, Evidence
from ontology_platform.modules.ontology.qa_context import qa_context
from qa_support import (
    QaDemo,
    inspection_metric_fixture,  # noqa: F401
    qa_demo_fixture,  # noqa: F401
    qa_steel_fixture,  # noqa: F401
)
from test_qa_demo_import import FIXTURES

QUOTES = (
    "检验结果合格且无严重缺陷的钢卷判为正品。",
    "力学性能合格但存在一般缺陷的钢卷可判为降级品。",
    "检验结果不合格，或存在严重的结疤、边裂缺陷的钢卷判废。",
)
DOCUMENT_BODY = "钢卷在精整线上由表面检测仪和人工共同检查表面质量。"


async def _attach_evidence(db: AsyncSession, demo: QaDemo) -> UUID:
    item = await db.scalar(
        select(ChangeItem.id).where(ChangeItem.applied_element_id == UUID(demo.steel.ids["Heat"]))
    )
    assert item is not None
    document = Document(
        id=uuid4(),
        ontology_id=demo.steel.ontology.id,
        filename="资料04.md",
        media_type="text/markdown",
        size_bytes=500,
        sha256="a" * 64,
        storage_key="qa/doc04",
        status="ready",
        progress={"step": "done", "done": 3, "total": 3},
        uploaded_by=uuid4(),
    )
    db.add(document)
    await db.flush()
    for seq, quote in enumerate(QUOTES, start=1):
        body = DOCUMENT_BODY + quote
        # Provenance orders evidence from the same document by chunk ID.
        chunk = Chunk(
            id=UUID(int=document.id.int // 4 + seq),
            document_id=document.id,
            seq=seq,
            text=body,
            char_count=len(body),
        )
        db.add(chunk)
        db.add(
            Evidence(change_item_id=item, document_id=document.id, chunk_id=chunk.id, quote=quote)
        )
    await db.commit()
    return document.id


@pytest.mark.parametrize("share", [True, False])
async def test_qa_gateway_sees_only_authorized_fields(
    db: AsyncSession, qa_demo: QaDemo, external_source: ExternalSource, share: bool
) -> None:
    steel = qa_demo.steel
    document_id = await _attach_evidence(db, qa_demo)
    await qa_demo.allow_samples(share)
    question = await qa_demo.run("Q2")
    assert question.status == "answered"
    assert question.evidence is not None
    assert question.plan is not None
    assert question.answer is not None
    docs = next(e.documents for e in question.evidence.elements if str(e.id) == steel.ids["Heat"])
    assert [(d.document_id, d.document_name, d.chunk, d.quote) for d in docs] == [
        (document_id, "资料04.md", 1, QUOTES[0]),
        (document_id, "资料04.md", 2, QUOTES[1]),
    ]

    calls = qa_demo.gateway.calls
    assert [c.purpose for c in calls] == (["qa.plan", "qa.answer"] if share else ["qa.plan"])
    ontology = await bindings.released_ontology(db, steel.ontology.id)
    assert ontology is not None
    english = {e.iri: e.label_en or e.local_name for e in ontology.elements if e.kind == "property"}
    expected = tomllib.loads((FIXTURES / "expected-bindings.toml").read_text("utf-8"))
    columns = {
        column
        for t in expected["types"]
        for iri, column in t["properties"].items()
        if column.casefold() != (english[iri] or "").casefold()
    }
    for call in calls:
        assert not call.files
        assert call.document_id is None
        assert call.effort is None
        for content in (call.text, call.instructions):
            for token in {"mes", *columns, external_source.host, str(external_source.port)}:
                assert not re.search(rf"(?<!\w){re.escape(token)}(?!\w)", content, re.I)
            for private in (
                steel.source_name,
                external_source.database,
                external_source.reader,
                DOCUMENT_BODY,
                *QUOTES,
                "资料04.md",
            ):
                assert private not in content

    plan = calls[0]
    assert plan.schema is QaPlanOut
    payload = json.loads(plan.text)
    assert set(payload) == {"question", "context"}
    assert payload["question"] == question.question
    assert isinstance(payload["context"], list)
    assert payload["context"]
    # Every string value needs a semantic origin, even if a new payload field is added.
    fields = {
        "entity_type": {"labelEn", "bound", "definition", "parent"},
        "property": {"labelEn", "bound", "domain", "datatype", "unit", "allowedValues"},
        "relation_type": {"labelEn", "bound", "domain", "range"},
        "metric": {"definition", "subject", "aggregate", "labelEn"},
    }
    allowed = {"Q235B", "Q275B", "metric"}
    released_metrics = await bindings.released_metrics(db, steel.ontology.id)
    for metric in released_metrics.metrics:
        allowed.update((metric.label_zh, metric.metric.aggregate))
        if metric.label_en is not None:
            allowed.add(metric.label_en)
    for element in ontology.elements:
        allowed.update(
            x
            for x in (
                element.kind,
                element.label_zh,
                element.label_en,
                element.local_name,
                element.definition_zh,
                element.definition_en,
                element.datatype,
                element.unit,
            )
            if x is not None
        )
    for entry in payload["context"]:
        assert set(entry) <= fields[entry["kind"]] | {"ref", "kind", "labelZh"}
        for field, value in entry.items():
            if field == "allowedValues":
                assert value == (["Q235B", "Q275B"] if entry["labelZh"] == "钢种" else [])
            elif field == "bound":
                assert isinstance(value, bool)
            elif value is not None:
                assert isinstance(value, str)
                assert value in allowed or re.fullmatch(r"[TPRM][1-9]\d*", value)
    for row in [*question.evidence.rows, *question.evidence.tail]:
        assert row.key not in plan.text
        for key in row.source.key:
            assert key.value not in plan.text

    if not share:
        assert "rows_not_shared" in question.answer.notes
        assert question.answer.text is None
        return

    answer = calls[1]
    assert answer.schema is QaAnswerOut
    rows = [*question.evidence.rows, *question.evidence.tail]
    assert len(rows) == 5
    bound = await bindings.bound_model(db, steel.ontology.id)
    assert bound is not None
    expected_rows = []
    for i, row in enumerate(rows, start=1):
        typ = bound.type(row.type_id)
        assert typ is not None
        ref = (
            None
            if i <= 2
            else next(f"K{j}" for j, obj in enumerate(rows[:2], start=1) if obj.key == row.via[4])
        )
        expected_rows.append(
            {
                "ref": f"K{i}",
                "type": typ.label,
                # #128: the primary key values, without the key column names.
                "name": " / ".join(k.value for k in row.source.key),
                "answerRef": ref,
                "values": [
                    {"label": p.label, "value": row.values[p.property_id]} for p in typ.properties
                ],
            }
        )
    assert json.loads(answer.text) == {
        "question": question.question,
        "plan": question.plan.description,
        "rows": expected_rows,
        "total": 2,
        "metric": None,
        "rules": [],
        "truncated": False,
        "limit": 50,
    }


async def test_qa_answer_caps_combined_rows_and_property_text(
    db: AsyncSession, qa_demo: QaDemo
) -> None:
    question = await qa_demo.run("Q2")
    assert question.evidence is not None
    assert question.plan is not None
    evidence = question.evidence.model_copy(deep=True)
    first = evidence.rows[0]
    prop = UUID(qa_demo.steel.ids["coilStatus"])
    first.values[prop] = "长" * 200 + "截断后的内容"
    # With 49 answers, only one of the three supporting rows can receive a reference.
    evidence.rows.extend(first.model_copy(update={"key": f"extra-{i}"}) for i in range(47))
    context = await qa_context(db, qa_demo.steel.ontology.id)
    qa_demo.gateway.outputs["qa.answer"] = QaAnswerOut(
        answer="共有 72 个对象。", cited_keys=["K50", "K51"], counterpoints=[]
    )
    result = await qa_answer.answer(
        db, qa_demo.gateway, "scripted", question.question, question.plan, context, evidence, 72
    )
    call = qa_demo.gateway.calls[-1]
    payload = json.loads(call.text)
    assert [r["ref"] for r in payload["rows"]] == [f"K{i}" for i in range(1, 51)]
    assert payload["truncated"]
    assert payload["total"] == result.facts.count == 72
    assert {"label": "状态", "value": "长" * 200} in payload["rows"][0]["values"]
    assert "截断后的内容" not in call.text
    assert result.cited_keys == [evidence.tail[0].key]
    assert set(result.notes) == {"rows_truncated", "cited_unknown"}


async def test_a_business_value_shaped_like_a_row_ref_stays(
    db: AsyncSession, qa_demo: QaDemo
) -> None:
    question = await qa_demo.run("Q2")
    assert question.evidence is not None
    assert question.plan is not None
    evidence = question.evidence.model_copy(deep=True)
    evidence.rows[0].values[UUID(qa_demo.steel.ids["coilStatus"])] = "K55"
    context = await qa_context(db, qa_demo.steel.ontology.id)
    qa_demo.gateway.outputs["qa.answer"] = QaAnswerOut(
        answer="K1 的状态是 K55（K1）。", cited_keys=["K1"], counterpoints=[]
    )
    result = await qa_answer.answer(
        db, qa_demo.gateway, "scripted", question.question, question.plan, context, evidence, 2
    )
    name = " / ".join(k.value for k in evidence.rows[0].source.key)
    assert result.text == f"{name} 的状态是 K55。"
    assert result.notes == []


@pytest.mark.parametrize("case", ["Q3", "Q4"])
async def test_qa_aggregate_prompt_contains_only_business_results(
    qa_demo: QaDemo, case: str
) -> None:
    question = await qa_demo.run(case)
    assert question.evidence is not None
    assert question.plan is not None
    _, answer = qa_demo.gateway.calls
    metric = None
    rules = []
    if case == "Q3":
        value = question.evidence.metric
        assert value is not None
        metric = {
            "label": "检验合格率",
            "display": "92.3%",
            "unit": None,
            "value": value.value,
            "population": 39,
            "matched": 36,
        }
    else:
        report = question.evidence.rules
        assert report is not None
        assert any(r.message and r.samples for r in report.results)
        rules = [{"label": r.constraint_label, "violations": r.violations} for r in report.results]
    assert json.loads(answer.text) == {
        "question": question.question,
        "plan": question.plan.description,
        "rows": [],
        "total": None,
        "metric": metric,
        "rules": rules,
        "truncated": False,
        "limit": 50,
    }
