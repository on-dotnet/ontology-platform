"""Scripted QA jobs against the published steel release and its external fixture."""

import tomllib
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field, replace
from functools import cache
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.ai import qa
from ontology_platform.modules.ai.gateway import AiError, InputFile
from ontology_platform.modules.ai.qa_prompts import QaAnswerOut, QaPlanOut
from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import JobContext
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.qa_context import qa_context
from ontology_platform.settings import Settings
from query_path_support import qa_steel_fixture
from support import csrf_headers
from test_metrics_evaluate import inspection_metric_fixture
from test_qa_demo_import import FIXTURES
from test_query_paging import SteelObjects

__all__ = [
    "GatewayCall",
    "QaDemo",
    "ScriptedGateway",
    "inspection_metric_fixture",
    "qa_demo_fixture",
    "qa_steel_fixture",
]


@dataclass(frozen=True)
class GatewayCall:
    purpose: str
    text: str
    instructions: str
    schema: type[BaseModel]
    files: tuple[InputFile, ...]
    document_id: Any
    effort: str | None


class ScriptedGateway:
    def __init__(self) -> None:
        self.calls: list[GatewayCall] = []
        self.outputs: dict[str, BaseModel | AiError] = {}
        self.question: str | None = None
        self.before_call: Callable[[GatewayCall], Awaitable[None]] | None = None

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
        call = GatewayCall(purpose, text, instructions, schema, tuple(files), document_id, effort)
        self.calls.append(call)
        assert self.question is not None
        assert self.question in text
        if self.before_call:
            await self.before_call(call)
        result = self.outputs[purpose]
        if isinstance(result, AiError):
            raise result
        assert isinstance(result, schema)
        return result

    async def ping(self) -> bool:
        return True


@dataclass
class QaDemo:
    steel: SteelObjects
    metric_id: UUID
    client: AsyncClient
    factory: async_sessionmaker[AsyncSession]
    questions: dict[str, dict[str, Any]]
    scripts: dict[str, Any]
    gateway: ScriptedGateway = field(default_factory=ScriptedGateway)
    completed: list[QaQuestion] = field(default_factory=list)
    broken_calls: list[UUID] = field(default_factory=list)
    break_listener: bool = False

    @property
    def url(self) -> str:
        return f"/api/ontologies/{self.steel.ontology.id}/qa/questions"

    async def allow_samples(self, allowed: bool) -> None:
        url = f"/api/data-sources/{self.steel.source_id}"
        source = await self.client.get(url)
        assert source.status_code == 200
        response = await self.client.patch(
            url,
            json={"revision": source.json()["revision"], "allowSamples": allowed},
            headers=csrf_headers(self.client),
        )
        assert response.status_code == 200, response.text
        assert response.json()["allowSamples"] is allowed

    async def references(self) -> dict[UUID, str]:
        async with self.factory() as db:
            context = await qa_context(db, self.steel.ontology.id)
        return {element_id: ref for ref, element_id in context.refs.items()}

    async def ref_for(self, element_id: UUID) -> str:
        return (await self.references())[element_id]

    async def plan(self, case: str) -> QaPlanOut:
        by_id = await self.references()
        ids = {name: UUID(value) for name, value in self.steel.ids.items()}
        refs = {code: by_id[ids[name]] for code, name in self.scripts["refs"].items()}
        plan = deepcopy(self.scripts[case]["plan"])
        for name in ("start", "metric"):
            plan[name] = refs[plan[name]] if name in plan else None
        plan.setdefault("target", None)
        for step in plan["path"]:
            step["relation"] = refs[step["relation"]]
        for step in [plan, *plan["path"]]:
            for condition in step["filters"]:
                condition["property"] = refs[condition["property"]]
                condition.setdefault("value", None)
                condition.setdefault("values", None)
        for missing in plan["missing"]:
            missing["near"] = [refs[ref] for ref in missing["near"]]
        return QaPlanOut.model_validate(plan)

    async def submit(self, case: str) -> Response:
        return await self.client.post(
            self.url,
            json={"question": self.questions[case]["text"]},
            headers=csrf_headers(self.client),
        )

    async def queue(self, case: str) -> QaQuestion:
        response = await self.submit(case)
        assert response.status_code == 202, response.text
        assert "answerKeys" not in response.json()
        queued = QaQuestion.model_validate(response.json())
        assert queued.status == "queued"
        assert queued.question == self.questions[case]["text"]
        self.gateway.question = queued.question
        return queued

    async def fetch(self, question_id: UUID) -> QaQuestion:
        response = await self.client.get(f"/api/qa/questions/{question_id}")
        assert response.status_code == 200, response.text
        assert "answerKeys" not in response.json()
        assert "answer_keys" not in response.json()
        return QaQuestion.model_validate(response.json())

    async def execute(self, question_id: UUID, *, attempts: int = 1, max_attempts: int = 3) -> None:
        payload = {"questionId": str(question_id)}
        statement = select(Job).where(Job.kind == qa.JOB_KIND, Job.payload == payload)
        async with self.factory() as db:
            row = (await db.scalars(statement)).one()
            job = JobContext(row.id, row.payload, self.factory, attempts, max_attempts)
        handler = qa.make_answerer(self.factory, self.gateway, "scripted")
        token = _active.set(self)
        try:
            await handler(job)
        finally:
            _active.reset(token)

    async def run(
        self,
        case: str,
        *,
        plan: QaPlanOut | AiError | None = None,
        answer: QaAnswerOut | AiError | None = None,
    ) -> QaQuestion:
        self.gateway.outputs = {"qa.plan": plan if plan is not None else await self.plan(case)}
        if answer is not None:
            self.gateway.outputs["qa.answer"] = answer
        elif "answer" in self.scripts[case]:
            scripted = self.scripts[case]["answer"]
            self.gateway.outputs["qa.answer"] = QaAnswerOut.model_validate(scripted)
        queued = await self.queue(case)
        await self.execute(queued.id)
        [result] = [q for q in self.completed if q.id == queued.id]
        persisted = await self.fetch(result.id)
        assert persisted.model_dump() == result.model_dump()
        assert result.finished_at is not None
        assert result.step == "done"
        return result


# The worker API registers listeners for a process lifetime. Keep test state scoped to a job.
_active: ContextVar[QaDemo | None] = ContextVar("active_qa_demo", default=None)


@cache
def _register_listeners() -> None:
    async def broken(db: AsyncSession, question: QaQuestion) -> None:
        demo = _active.get()
        if demo is not None and demo.break_listener:
            demo.broken_calls.append(question.id)
            raise RuntimeError("scripted listener failure")

    async def capture(db: AsyncSession, question: QaQuestion) -> None:
        demo = _active.get()
        if demo is not None:
            demo.completed.append(question)

    qa.register_listener(broken)
    qa.register_listener(capture)


@pytest.fixture(name="qa_demo")
async def qa_demo_fixture(
    app: FastAPI,
    settings: Settings,
    client: AsyncClient,
    db: AsyncSession,
    qa_steel: SteelObjects,
    inspection_metric: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> QaDemo:
    settings.openai_api_key = SecretStr("test")
    monkeypatch.setenv("OP_OPENAI_API_KEY", "test")
    questions = tomllib.loads((FIXTURES / "questions.toml").read_text("utf-8"))["questions"]
    release = (await bindings.released_metrics(db, qa_steel.ontology.id)).release
    steel = replace(
        qa_steel,
        ids={**qa_steel.ids, "inspectionPassRate": str(inspection_metric)},
        release=release.model_dump(mode="json"),
    )
    demo = QaDemo(
        steel,
        inspection_metric,
        client,
        app.state.session_factory,
        {f"Q{i}": q for i, q in enumerate(questions, 1)},
        tomllib.loads((FIXTURES / "plans.toml").read_text("utf-8")),
    )
    await demo.allow_samples(True)
    _register_listeners()
    return demo
