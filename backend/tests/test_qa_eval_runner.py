"""Exercise the same stdin bundle, disposable databases and job handlers as eval-qa."""

import base64
import json
import os
import re
import tomllib
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from external_source import SQL_FILES, STEEL_SQL
from ontology_platform import qa_eval
from ontology_platform.modules.ai.gateway import AiUnavailableError, InputFile
from ontology_platform.modules.ai.prompts import AssistantOut
from ontology_platform.modules.ai.qa_scoring import parse_plan
from ontology_platform.modules.connectors import config
from ontology_platform.modules.jobs import runner
from test_ai_assistant import operation
from test_qa_demo_import import FIXTURES


@pytest.fixture
def bundle(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(runner, "_handlers", {})
    monkeypatch.setattr(config, "_configured", None)
    monkeypatch.setenv("OP_OPENAI_API_KEY", "")
    monkeypatch.setenv("OP_AI_PROXY", "")
    files = {p.name: p.read_bytes() for p in FIXTURES.iterdir() if p.is_file()}
    files.update({name: (STEEL_SQL / name).read_bytes() for name in SQL_FILES})
    return {"mode": "record", "files": {k: base64.b64encode(v).decode() for k, v in files.items()}}


class SteelGateway:
    def __init__(self, *, broken: str | None = None) -> None:
        self.scripts = tomllib.loads((FIXTURES / "plans.toml").read_text("utf-8"))
        qs = tomllib.loads((FIXTURES / "questions.toml").read_text("utf-8"))["questions"]
        self.cases = {q["text"]: f"Q{i}" for i, q in enumerate(qs, 1)}
        self.broken = broken

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
        effort: str | None = None,
    ) -> T:
        assert not files
        assert document_id is None
        case = next(case for question, case in self.cases.items() if question in text)
        if self.broken in (case, "all") and purpose == "qa.plan":
            raise AiUnavailableError("scripted", retryable=False)
        script = self.scripts[case]
        if purpose == "qa.gap":
            coil = re.search(r"^([0-9a-f-]+) \| entity_type \| 钢卷 /", text, re.M)
            assert coil is not None
            ops = []
            for op in script["proposal"]["operations"]:
                fields = op["fields"].copy()
                if fields.get("domain") == "T2":
                    fields["domain"] = coil[1]
                ops.append(operation(op["op"], op["kind"], temp_ref=op.get("temp_ref"), **fields))
            return schema.model_validate(AssistantOut(reply="审核", operations=ops).model_dump())
        if purpose == "qa.answer":
            # An output-only physical name must never be reported as an input leak.
            return schema.model_validate({**script["answer"], "answer": "mes.heat"})
        labels = {
            "T1": "炉次",
            "T2": "钢卷",
            "T3": "质量检验",
            "T4": "浇次",
            "T5": "板坯",
            "T6": "轧制事件",
            "P1": "钢种",
            "P2": "是否合格",
            "R1": "对应浇次",
            "R2": "产出板坯",
            "R3": "参与轧制",
            "R4": "产出钢卷",
            "R5": "检验对象",
            "M1": "检验合格率",
        }
        refs = {row["labelZh"]: row["ref"] for row in json.loads(text)["context"]}
        plan = parse_plan(script["plan"]).model_dump_json()
        plan = re.sub(r'"([TPRM]\d+)"', lambda m: json.dumps(refs[labels[m[1]]]), plan)
        return schema.model_validate_json(plan)

    def take_usage(self) -> tuple[int, int, int, int]:
        return 1, 101, 23, 7

    async def ping(self) -> bool:
        pytest.fail("evaluation should only call structured")


def evaluate(
    bundle: dict[str, Any],
    gateway: SteelGateway | None = None,
    lines: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int]:
    return qa_eval.evaluate(
        bundle,
        os.environ["OP_TEST_ADMIN_DATABASE_URL"],
        gateway,
        (lines if lines is not None else []).append,
    )


def test_record_and_replay_in_fresh_databases(bundle: dict[str, Any]) -> None:
    lines: list[dict[str, Any]] = []
    reply, code = evaluate(bundle, SteelGateway(), lines)
    assert code == 0, reply.get("error")
    assert reply["type"] == "result"
    result = json.loads(reply["result"])
    rows = result["questions"]
    assert [q["result"] for q in rows] == ["pass"] * 4 + ["unanswerable"]
    assert all(q["v2Pass"] and q["planEquivalent"] and q["plan"] for q in rows)
    assert result["summary"] == {"passed": 4, "v2Passed": 5, "equivalent": 5}
    assert result["promptLeaks"] == []
    assert [r["usage"]["calls"] for r in rows] == [2] * 5
    assert all(r["usage"]["inputTokens"] == 202 and r["usage"]["outputTokens"] == 46 for r in rows)
    gap = rows[-1]["proposal"]
    assert gap["unchanged"]
    assert gap["status"] == "done"
    assert gap["dropped"] == 0
    assert {i["labelZh"] for i in gap["items"]} == {
        "表面缺陷",
        "缺陷类型",
        "位置",
        "严重程度",
        "钢卷表面缺陷",
    }
    assert {i["op"] for i in gap["items"]} == {"create"}
    assert lines[0]["type"] == "file"
    assert lines[0]["name"] == "models.json"
    manifest = lines[0]["content"]
    records = [f["content"] for f in lines[1:]]
    assert all(f["type"] == "file" for f in lines[1:])
    bundle.update(mode="replay", recordings=records, manifest=manifest)
    replay_lines: list[dict[str, Any]] = []
    replay, code = evaluate(bundle, lines=replay_lines)
    assert code == 0, replay.get("error")
    actual = json.loads(replay["result"])
    assert actual["summary"] == result["summary"]
    assert actual["questions"][-1]["proposal"]["items"] == gap["items"]
    assert all(
        q["usage"]["replayed"] == 2 and q["usage"]["calls"] == 0 for q in actual["questions"]
    )
    assert replay_lines == []

    bundle["recordings"] = [r for r in records if json.loads(r)["purpose"] != "qa.gap"]
    missing, code = evaluate(bundle)
    assert code == 1
    assert "Q5" in missing["error"]
    assert "qa.gap" in missing["error"]


def test_failed_question_does_not_abort_the_batch(bundle: dict[str, Any]) -> None:
    original = "Q235B 一共有哪些炉次？"
    questions = base64.b64decode(bundle["files"]["questions.toml"]).decode()
    questions = questions.replace(original, original + " mes.heat steel_grade")
    bundle["files"]["questions.toml"] = base64.b64encode(questions.encode()).decode()
    reply, code = evaluate(bundle, SteelGateway(broken="Q2"))
    assert code == 0, reply.get("error")
    result = json.loads(reply["result"])
    assert [r["result"] for r in result["questions"]] == [
        "pass",
        "error",
        "pass",
        "pass",
        "unanswerable",
    ]
    q2 = result["questions"][1]
    assert q2["status"] == "failed"
    assert q2["detail"]["errorCode"] == "ai.unavailable"
    assert q2["plan"] is None
    assert not q2["planEquivalent"]
    assert result["summary"] == {"passed": 3, "v2Passed": 4, "equivalent": 4}
    assert result["promptLeaks"] == [
        {"question": "Q1", "stage": stage, "call": call, "term": term}
        for call, stage in enumerate(("qa.plan", "qa.answer"), 1)
        for term in ("mes", "steel_grade")
    ]


def test_persistent_model_outage(bundle: dict[str, Any]) -> None:
    lines: list[dict[str, Any]] = []
    reply, code = evaluate(bundle, SteelGateway(broken="all"), lines)
    assert code == 1
    assert reply["type"] == "error"
    assert reply["error"] == "Q1-Q5 qa.plan 模型连续不可用"
    assert lines == []


def test_interrupt_keeps_first_question_recording(bundle: dict[str, Any]) -> None:
    class Interrupted(SteelGateway):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def structured[T: BaseModel](self, **call: Any) -> T:
            if self.calls >= 2:
                raise KeyboardInterrupt
            self.calls += 1
            return await super().structured(**call)

    lines: list[dict[str, Any]] = []
    with pytest.raises(KeyboardInterrupt):
        evaluate(bundle, Interrupted(), lines)
    assert [line["name"] for line in lines[:1]] == ["models.json"]
    assert len(lines) >= 2
    assert all(line["type"] == "file" for line in lines)
