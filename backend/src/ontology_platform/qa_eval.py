"""Run the five steel competency checks on v2 in disposable databases."""

import asyncio
import base64
import json
import logging
import os
import re
import secrets
import sys
import time
import tomllib
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from alembic import command
from alembic.config import Config
from fastapi import Request
from psycopg import sql
from pydantic import BaseModel, SecretStr
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.db import create_database_engine, create_session_factory
from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa, qa_gap
from ontology_platform.modules.ai.gateway import AiError, InputFile, ModelGateway
from ontology_platform.modules.ai.qa_prompts import QaPlanOut
from ontology_platform.modules.ai.qa_scoring import parse_plan, score_plan
from ontology_platform.modules.ai.replay import (
    STAGE_COUNTS,
    MeteredGateway,
    ReplayGateway,
    ReplayMissError,
    load_recordings,
)
from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.connectors import jobs as catalog_jobs
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.connectors.schemas import DataSourceCreate
from ontology_platform.modules.cq import service as cq
from ontology_platform.modules.cq.importing import import_questions
from ontology_platform.modules.identity import service as identity
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.ontology import (
    bindings,
    editing,
    importing,
    merge,
    releases,
    schemas,
)
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.qa_context import QaContext, qa_context
from ontology_platform.settings import Settings

type Factory = async_sessionmaker[AsyncSession]
type Files = dict[str, bytes]
type Json = dict[str, Any]


class EvaluationError(Exception):
    """A safe diagnostic for the stdout envelope."""


class GatewaySettings(Settings):
    @property
    def ai_configured(self) -> bool:
        # CQ and gap enqueue check availability. A replay gateway needs no provider credential.
        return True


@contextmanager
def databases(admin_url: str, files: Files) -> Iterator[tuple[str, DataSourceCreate]]:
    admin = make_url(admin_url)
    suffix = secrets.token_hex(6)
    platform, mes, reader = (f"ontology_{name}_{suffix}" for name in ("qa", "mes", "reader"))
    password = secrets.token_urlsafe(24)
    url = admin.set(drivername="postgresql")
    with (
        psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as conn,
        ExitStack() as cleanup,
    ):
        conn.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(reader), sql.Literal(password)
            )
        )
        cleanup.callback(conn.execute, sql.SQL("DROP ROLE {}").format(sql.Identifier(reader)))
        for name in (platform, mes):
            identifier = sql.Identifier(name)
            conn.execute(sql.SQL("CREATE DATABASE {}").format(identifier))
            drop = sql.SQL("DROP DATABASE {} WITH (FORCE)").format(identifier)
            cleanup.callback(conn.execute, drop)
        with psycopg.connect(url.set(database=mes).render_as_string(hide_password=False)) as db:
            for filename in ("01-schema.sql", "02-data.sql"):
                db.execute(files[filename])
            db.execute(
                sql.SQL(
                    "REVOKE ALL ON DATABASE {db} FROM PUBLIC;"
                    "REVOKE CREATE ON SCHEMA public FROM PUBLIC;"
                    "GRANT CONNECT ON DATABASE {db} TO {r};"
                    "GRANT USAGE ON SCHEMA mes TO {r};"
                    "GRANT SELECT ON ALL TABLES IN SCHEMA mes TO {r};"
                    "ALTER ROLE {r} SET default_transaction_read_only = on"
                ).format(db=sql.Identifier(mes), r=sql.Identifier(reader))
            )
        platform_url = admin.set(database=platform).render_as_string(hide_password=False)
        migration = Config()
        migration.set_main_option("script_location", "ontology_platform:migrations")
        migration.attributes["database_url"] = platform_url
        command.upgrade(migration, "head")
        source = DataSourceCreate(
            kind="postgresql",
            name="评测用冶金数据源",
            host=admin.host or "localhost",
            port=admin.port or 5432,
            database=mes,
            username=reader,
            password=SecretStr(password),
            schemas=["mes"],
            allow_samples=True,
        )
        yield platform_url, source


async def drain(factory: Factory, gateway: "QuestionGateway | None" = None) -> None:
    """Run the production queue with one worker until this isolated batch is terminal."""
    stop = gateway.stop if gateway else asyncio.Event()
    stop.clear()
    worker = asyncio.create_task(
        runner.run_worker(factory, "eval-qa", poll_interval=0.1, stop_event=stop)
    )
    active = select(Job.id).where(Job.status.in_(("queued", "running"))).limit(1)
    try:
        while not worker.done():
            if gateway and gateway.fatal:
                raise gateway.fatal
            async with factory() as db:
                pending = await db.scalar(active)
            if pending is None:
                break
            await asyncio.sleep(0.1)
    finally:
        stop.set()
        await worker
    if gateway and gateway.fatal:
        raise gateway.fatal


async def review(db: AsyncSession, change_id: UUID, reviewer: UUID) -> None:
    detail = await ontology.get_change_set(db, change_id)
    if detail.source not in ("import", "manual"):
        raise EvaluationError("评测只审核样例导入、绑定和指标")
    decision = schemas.BulkDecision(item_ids=[i.id for i in detail.items], decision="accepted")
    detail = await ontology.decide_items(
        db, change_id, decision, actor=reviewer, review_mode="separate"
    )
    result = await merge.merge_change_set(
        db,
        change_id,
        actor=reviewer,
        ip=None,
        review_mode="separate",
        resolution_token=detail.resolution_token,
    )
    if result.skipped:
        raise EvaluationError("样例审核有跳过项")


def binding_edits(spec: Json, ids: dict[str, str], source: UUID) -> list[Json]:
    refs = {t["type"]: t["table"] for t in spec["types"]}
    items: list[Json] = []

    def add(kind: str, subject: str, binding: Json, **fields: str) -> None:
        items.append(
            {
                "op": "create",
                "kind": kind,
                "fields": {"subjectRef": ids[subject], "binding": binding, **fields},
            }
        )

    for t in spec["types"]:
        name = t["table"]
        table = {
            "target": "table",
            "dataSourceId": str(source),
            "schema": t["schema"],
            "table": name,
            "keyColumns": t["key"],
        }
        add("type_binding", t["type"], table)
        items[-1]["tempRef"] = name
        for iri, column in t["properties"].items():
            add("property_binding", iri, {"target": "column", "column": column}, parentRef=name)
    for r in spec["relations"]:
        add(
            "relation_binding",
            r["relation"],
            {"target": "join", "join": r["join"]},
            domainRef=refs[r["source"]],
            rangeRef=refs[r["target"]],
        )
    return items


async def prepare(
    db: AsyncSession, files: Files, source_id: UUID, editor: UUID, reviewer: UUID
) -> UUID:
    imported = await importing.import_new(
        db,
        data=files["ontology.ttl"],
        filename="ontology.ttl",
        name="钢铁质量演示",
        key="qa-steel",
        actor=editor,
        ip=None,
    )
    if imported.change_set_id is None:
        raise EvaluationError("样例导入没有变更集")
    await review(db, imported.change_set_id, reviewer)
    oid = imported.ontology.id
    elements = await ontology.list_elements(db, oid, kind=None, q=None)
    ids = {e.iri: str(e.id) for e in elements if e.iri}
    edits = binding_edits(tomllib.loads(files["expected-bindings.toml"].decode()), ids, source_id)
    metrics = tomllib.loads(files["metrics.toml"].decode())["items"]
    for item in metrics:
        fields = item["fields"]
        fields["subjectRef"] = ids[fields["subjectRef"]]
        item["tempRef"] = f"new:{fields['localName']}"
        for condition in fields["metric"]["filters"] + fields["metric"]["numerator"]:
            condition["propertyRef"] = ids[condition["propertyRef"]]
    for version, items in enumerate((edits, metrics), 1):
        saved = await editing.save_edits(
            db,
            oid,
            schemas.EditRequest.model_validate({"items": items}),
            actor=editor,
            ip=None,
            may_apply=False,
        )
        await review(db, saved.change_set_id, reviewer)
        release = await releases.publish_release(
            db, oid, schemas.ReleaseCreate(title=f"v{version}"), actor=reviewer, ip=None
        )
        if release.version != version:
            raise EvaluationError("样例发布版本不符")
    return oid


def request_for(content: bytes) -> Request:
    async def receive() -> Json:
        return {"type": "http.request", "body": content, "more_body": False}

    return Request({"type": "http", "headers": [(b"content-type", b"text/plain")]}, receive)


class QuestionGateway:
    def __init__(
        self, replay: ReplayGateway, ctx: QaContext, source: DataSourceCreate, cases: dict[str, str]
    ) -> None:
        self.replay = replay
        self.cases = cases
        self.plans: dict[str, QaPlanOut] = {}
        self.leaks: list[Json] = []
        self.stop = asyncio.Event()
        self.fatal: EvaluationError | None = None
        self.calls: dict[str, int] = {}
        english = {e.id: e.label_en or e.local_name or "" for e in ctx.ontology.elements}
        columns = {
            p.column
            for t in ctx.model.types
            for p in t.properties
            if p.column.casefold() != english[p.property_id].casefold()
        }
        self.tokens = {
            token: re.compile(rf"(?<!\w){re.escape(token)}(?!\w)", re.I)
            for token in {*source.schemas, source.host, str(source.port), *columns}
        }
        for s in (source.name, source.database, source.username):
            self.tokens[s] = re.compile(re.escape(s), re.I)
        # Gap prompts use UUIDs; keep the same UUID-shaped identities across fresh imports.
        self.stable = {
            str(e.id): str(uuid5(NAMESPACE_URL, e.iri)) for e in ctx.ontology.elements if e.iri
        }
        self.local = {v: k for k, v in self.stable.items()}

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
        case = "Q5" if purpose == "qa.gap" else self.cases[json.loads(text)["question"]]
        self.replay.label(None, case)
        call = self.calls[case] = self.calls.get(case, 0) + 1
        if purpose == "qa.gap":
            text = _translate_ids(text, self.stable)
        content = instructions + "\n" + text
        if purpose != "qa.gap":
            content += "\n" + json.dumps(json.loads(text), ensure_ascii=False)
        for token, pattern in sorted(self.tokens.items()):
            if pattern.search(content):
                self.leaks.append({"question": case, "stage": purpose, "call": call, "term": token})
        if files or document_id is not None:
            raise EvaluationError(f"{case} {purpose} 包含意外的附件或资料引用")
        try:
            out = await self.replay.structured(
                purpose=purpose,
                model=model,
                instructions=instructions,
                text=text,
                schema=schema,
                files=files,
                document_id=document_id,
                effort=effort,
            )
        except ReplayMissError as exc:
            self.fatal = EvaluationError(f"{case} {purpose} 缺录制")
            self.stop.set()
            raise self.fatal from exc
        except AiError as exc:
            if exc.code == "ai.not_configured":
                self.fatal = EvaluationError(f"{case} {purpose} {exc.code}")
                self.stop.set()
            raise
        if isinstance(out, QaPlanOut):
            self.plans[case] = out.model_copy(deep=True)
        if purpose == "qa.gap":
            return schema.model_validate_json(_translate_ids(out.model_dump_json(), self.local))
        return out

    async def ping(self) -> bool:
        return await self.replay.ping()


def _translate_ids(text: str, ids: dict[str, str]) -> str:
    pattern = r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b"
    return re.sub(pattern, lambda m: ids.get(m[0], m[0]), text)


def fixture_plan(actual: QaPlanOut, refs: dict[str, str]) -> QaPlanOut:
    plan = actual.model_copy(deep=True)

    def ref(value: str) -> str:
        return refs.get(value, "release:" + value)

    if plan.start is not None:
        plan.start = ref(plan.start)
    if plan.metric is not None:
        plan.metric = ref(plan.metric)
    for hop in plan.path:
        hop.relation = ref(hop.relation)
    for filters in [plan.filters, *(hop.filters for hop in plan.path)]:
        for condition in filters:
            condition.property = ref(condition.property)
    for missing in plan.missing:
        missing.near = [ref(v) for v in missing.near]
    return plan


async def snapshot(db: AsyncSession, oid: UUID) -> tuple[UUID, set[UUID], set[UUID]]:
    working = await ontology.list_elements(db, oid, kind=None, q=None)
    active = await bindings.released_ontology(db, oid)
    if active is None:
        raise EvaluationError("生效版本不存在")
    return active.release_id, {e.id for e in working}, {e.id for e in active.elements}


async def propose(
    db: AsyncSession,
    factory: Factory,
    question: QaQuestion,
    actor: identity.Principal,
    settings: Settings,
    gateway: QuestionGateway,
) -> Json:
    before = await snapshot(db, question.ontology_id)
    await qa_gap.enqueue_gap_proposal(db, question.id, user_id=actor.id, settings=settings)
    await drain(factory, gateway)
    question = await qa.get_question(db, question.id, actor=actor)
    proposal = question.gap_proposal
    if proposal is None or proposal.status not in ("done", "empty"):
        raise EvaluationError(f"Q5 qa.gap {proposal.error_code if proposal else 'pending'}")
    items = []
    if proposal.change_set_id:
        detail = await ontology.get_change_set(db, proposal.change_set_id)
        pending = all(i.decision == "pending" for i in detail.items)
        if detail.source != "ai_qa" or detail.status != "open" or not pending:
            raise EvaluationError("缺口提议未进入待审核变更集")
        items = [{"op": i.op, "kind": i.kind, "labelZh": i.proposed.label_zh} for i in detail.items]
    if before != await snapshot(db, question.ontology_id):
        raise EvaluationError("缺口提议改变了工作版本或生效版本")
    return {
        "status": proposal.status,
        "items": items,
        "dropped": proposal.dropped,
        "unchanged": True,
    }


async def run_case(
    factory: Factory,
    settings: Settings,
    files: Files,
    source: DataSourceCreate,
    replay: ReplayGateway,
    model: str,
) -> Json:
    scripts = tomllib.loads(files["plans.toml"].decode())
    catalog_jobs.register_handlers(factory, settings)
    async with factory() as db:

        async def person(role: Role) -> identity.Principal:
            user = await identity.create_user(
                db, username=f"qa-{role}", password=secrets.token_urlsafe(), role=role
            )
            return identity.principal_of(user)

        editor, reviewer = await person(Role.ADMIN), await person(Role.REVIEWER)
        created = await connectors.create_data_source(db, source, actor=editor, ip=None)
        await connectors.request_catalog_refresh(db, created.id, actor=editor, ip=None)
        await drain(factory)
        refreshed = await connectors.get_data_source(db, created.id, actor=editor)
        if refreshed.catalog is None or refreshed.catalog.status != "ready":
            raise EvaluationError("样例数据源目录刷新失败")
        oid = await prepare(db, files, created.id, editor.id, reviewer.id)
        ctx = await qa_context(db, oid)
        imported = await import_questions(db, oid, request_for(files["questions.toml"]), editor.id)
        if imported.created != 5:
            raise EvaluationError("需要五条能力问题")
        db.info["qa_settings"] = settings
        checks = await cq.start_checks(db, oid, editor.id, batch=True)
        await db.commit()
        questions = (await cq.list_questions(db, oid, archived=False)).items
        cases = {q.text: f"Q{i}" for i, q in enumerate(questions, 1)}
        by_id = {q.id: cases[q.text] for q in questions}
        labels = {str(c.qa_question_id): by_id[c.question_id] for c in checks}
        gateway = QuestionGateway(replay, ctx, source, cases)
        elapsed = dict.fromkeys(cases.values(), 0.0)

        def timed(handler: runner.Handler) -> runner.Handler:
            async def handle(job: runner.JobContext) -> None:
                case = labels[job.payload["questionId"]]
                start = time.monotonic()
                try:
                    await handler(job)
                finally:
                    elapsed[case] += time.monotonic() - start

            return handle

        qa.register_listener(cq.record_result)
        runner.register(qa.JOB_KIND, timed(qa.make_answerer(factory, gateway, model)))
        runner.register(qa_gap.JOB_KIND, timed(qa_gap.make_gap_proposer(factory, gateway, model)))
        await drain(factory, gateway)
        names = {e.id: e.local_name for e in ctx.ontology.elements}
        names.update((m.id, m.local_name) for m in ctx.metrics.metrics)
        fixture_refs = {name: ref for ref, name in scripts["refs"].items()}
        refs = {
            ref: fixture_refs[name]
            for ref, id_ in ctx.refs.items()
            if (name := names[id_]) is not None and name in fixture_refs
        }
        rows: list[Json] = []
        for q in (await cq.list_questions(db, oid, archived=False)).items:
            check = q.last_check
            if check is None or check.result == "pending":
                raise EvaluationError("能力问题未完成")
            case = cases[q.text]
            answer = await qa.get_question(db, check.qa_question_id, actor=editor)
            if answer.error_code == "query.source_unavailable":
                raise EvaluationError(f"{case} {answer.error_code}")
            proposal = None
            if case == "Q5" and answer.gaps and answer.gaps.elements:
                proposal = await propose(db, factory, answer, editor, settings, gateway)
            plan = gateway.plans.get(case)
            expected = parse_plan(scripts[case]["plan"])
            equivalent, mismatch = (
                score_plan(expected, fixture_plan(plan, refs)) if plan else (False, "plan")
            )
            v2_pass = check.result == "pass"
            if case == "Q5":
                elements = answer.gaps.elements if answer.gaps else []
                missing = {(e.kind, e.label_zh) for e in elements}
                v2_pass = (
                    check.result == "unanswerable"
                    and {(e.kind, e.label_zh) for e in expected.missing} <= missing
                    and proposal is not None
                    and proposal["status"] == "done"
                )
            stages = replay.stats().get(case, {})
            detail = check.detail.model_dump(by_alias=True, mode="json") if check.detail else None
            gaps = answer.gaps.model_dump(by_alias=True, mode="json") if answer.gaps else None
            rows.append(
                {
                    "case": case,
                    "question": q.text,
                    "status": answer.status,
                    "result": check.result,
                    "detail": detail,
                    "v2Pass": v2_pass,
                    "planEquivalent": equivalent,
                    "firstMismatch": mismatch,
                    "plan": plan.model_dump() if plan else None,
                    "answer": answer.answer.text if answer.answer else None,
                    "gaps": gaps,
                    "proposal": proposal,
                    "elapsedSeconds": round(elapsed[case], 2),
                    "usage": {k: sum(s[k] for s in stages.values()) for k in STAGE_COUNTS},
                }
            )
    if all(r["detail"] and r["detail"].get("errorCode") == "ai.unavailable" for r in rows):
        raise EvaluationError("Q1-Q5 qa.plan 模型连续不可用")
    return {
        "questions": rows,
        "model": model,
        "references": {ref: names[id_] for ref, id_ in ctx.refs.items()},
        "promptLeaks": gateway.leaks,
        "summary": {
            "passed": sum(q["result"] == "pass" for q in rows),
            "equivalent": sum(q["planEquivalent"] for q in rows),
            "v2Passed": sum(q["v2Pass"] for q in rows),
        },
    }


async def _run(
    settings: Settings, files: Files, source: DataSourceCreate, replay: ReplayGateway, model: str
) -> Json:
    engine = create_database_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        return await run_case(factory, settings, files, source, replay, model)
    finally:
        await engine.dispose()


def evaluate(bundle: Json, admin_url: str, inner: ModelGateway | None = None) -> tuple[Json, int]:
    settings = Settings()
    mode = bundle["mode"]
    if mode not in ("record", "replay"):
        raise ValueError("Invalid evaluation mode")
    model = settings.ai_model
    if mode == "replay" and bundle.get("manifest"):
        model = json.loads(bundle["manifest"])["model"]
    if mode == "replay":
        inner = None
    elif inner is None:
        inner = MeteredGateway(settings)
    replay = ReplayGateway(load_recordings(bundle.get("recordings", [])), inner)
    reply: Json = {}
    try:
        files = {k: base64.b64decode(v) for k, v in bundle["files"].items()}
        with databases(admin_url, files) as (url, source):
            settings = GatewaySettings(database_url=url)
            result = asyncio.run(_run(settings, files, source, replay, model))
        reply["result"] = json.dumps(result, indent=2, ensure_ascii=False)
    except EvaluationError as exc:
        reply["error"] = str(exc)
    except AppError as exc:
        reply["error"] = exc.code
    except Exception as exc:
        # Driver and validation messages may include connection details.
        reply["error"] = type(exc).__name__
    recordings = [{"name": n, "content": c} for n, c in replay.recording_files()]
    if recordings:
        recordings.append({"name": "models.json", "content": json.dumps({"model": model})})
    reply["files"] = recordings
    return reply, int("error" in reply)


if __name__ == "__main__":
    # The CLI already reports a replay miss with its question and stage.
    logging.getLogger(runner.__name__).addFilter(
        lambda record: not (record.exc_info and isinstance(record.exc_info[1], EvaluationError))
    )
    output, code = evaluate(json.load(sys.stdin), os.environ["OP_QA_EVAL_ADMIN_URL"])
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(code)
