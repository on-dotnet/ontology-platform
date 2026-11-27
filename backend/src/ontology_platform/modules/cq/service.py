"""Competency questions, their queued checks and release-specific coverage."""

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import qa
from ontology_platform.modules.ai.schemas import QaPlan, QaQuestion, QaQuestionCreate, ReleaseRef
from ontology_platform.modules.cq import schemas
from ontology_platform.modules.cq.compare import compare
from ontology_platform.modules.cq.models import CompetencyQuestionRow as Question
from ontology_platform.modules.cq.models import CqCheckRow as Check
from ontology_platform.modules.cq.schemas import CoverageItem
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology import service as ontology
from ontology_platform.modules.ontology.qa_context import metric_is_bound
from ontology_platform.modules.query import cursor
from ontology_platform.modules.query.schemas import KEY_MAX_LENGTH


def _invalid(detail: str) -> AppError:
    return AppError(422, "validation.failed", detail)


async def active_release(db: AsyncSession, ontology_id: UUID) -> ReleaseRef | None:
    summary = await ontology.get_ontology_summary(db, ontology_id)
    if summary.active_release_id is None or summary.active_release_version is None:
        return None
    return ReleaseRef(id=summary.active_release_id, version=summary.active_release_version)


async def object_types(db: AsyncSession, ontology_id: UUID) -> dict[UUID, str]:
    working = await ontology.list_alignment_elements(db, ontology_id)
    released = await bindings.released_ontology(db, ontology_id)
    return {
        e.id: e.iri or ""
        for e in (*working, *(released.elements if released else ()))
        if e.kind == "entity_type"
    }


def _decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise _invalid("Expected a finite decimal number.") from None
    # PostgreSQL unconstrained NUMERIC supports these integer and fractional digit limits.
    exponent = number.as_tuple().exponent
    if not isinstance(exponent, int) or number.adjusted() >= 131072 or exponent < -16383:
        raise _invalid("The number is outside the supported decimal range.")
    return number


def _encode_key(value: str, width: int | None) -> str:
    if width == 1:
        parts = [value]
    elif value.startswith("["):
        try:
            decoded = json.loads(value)
        except (ValueError, RecursionError):
            decoded = None
        if isinstance(decoded, list) and all(isinstance(p, str) for p in decoded):
            parts = decoded
        else:
            parts = [value]
    else:
        parts = value.split(" · ") if width else [value]
    if not parts or any(not p.strip() for p in parts) or (width and width != len(parts)):
        raise _invalid("Provide the primary key values in column order.")
    try:
        return cursor.encode_key(parts)
    except AppError:
        raise _invalid("The primary key is too long.") from None


def _plain_key(key: str) -> str:
    # Values in storage have already passed the query encoder. The typed decoder requires
    # catalog columns, which may no longer exist when displaying a historical difference.
    parts = cursor._decode(key, KEY_MAX_LENGTH)
    if not isinstance(parts, list) or not parts or not all(isinstance(p, str) for p in parts):
        raise ValueError("Invalid stored object key")
    if len(parts) == 1:
        return str(parts[0])
    if any(" · " in p for p in parts) or parts[0].startswith("["):
        return json.dumps(parts, ensure_ascii=False)
    return " · ".join(parts)


async def _set_expect(db: AsyncSession, row: Question, expect: schemas.CqExpectInput) -> None:
    kind = expect["kind"]
    fields = {
        "answerable": set(),
        "objects": {"keys", "type_id"},
        "number": {"number", "tolerance"},
    }
    if set(expect) - {"kind"} - fields[kind]:
        raise _invalid("Expectation fields do not match its kind.")
    row.expect_kind = kind
    row.expect_objects = None
    row.expect_number = None
    row.tolerance = Decimal(0)
    if kind == "objects":
        type_id = expect.get("type_id")
        if type_id is None or type_id not in await object_types(db, row.ontology_id):
            raise _invalid("Expected an object type belonging to this ontology.")
        if "keys" not in expect:
            raise _invalid("Object expectations require primary keys.")
        model = await bindings.bound_model(db, row.ontology_id)
        bound = model.type(type_id) if model else None
        width = len(bound.key_columns) if bound else None
        keys = dict.fromkeys(_encode_key(value, width) for value in expect["keys"])
        row.expect_objects = {"typeId": str(type_id), "keys": list(keys)}
    elif kind == "number":
        if "number" not in expect:
            raise _invalid("Number expectations require an expected value.")
        row.expect_number = _decimal(expect["number"])
        row.tolerance = _decimal(expect.get("tolerance", "0"))
        if row.tolerance < 0:
            raise _invalid("Tolerance must be non-negative.")


def _expect(row: Question) -> schemas.CqExpect:
    objects = row.expect_objects or {}
    return schemas.CqExpect.model_validate(
        {
            "kind": row.expect_kind,
            "typeId": objects.get("typeId"),
            "keys": objects.get("keys", []),
            "number": str(row.expect_number) if row.expect_number is not None else None,
            "tolerance": str(row.tolerance),
        }
    )


def _check(row: Check, release: ReleaseRef | None) -> schemas.CqCheck:
    stored = row.detail or {}
    detail = None
    if "actual" in stored:
        detail = schemas.CqCheckDetail.model_validate(stored)
        detail.missing = [_plain_key(k) for k in detail.missing]
        detail.extra = [_plain_key(k) for k in detail.extra]
    return schemas.CqCheck(
        id=row.id,
        question_id=row.question_id,
        qa_question_id=row.qa_question_id,
        release=ReleaseRef(id=row.release_id, version=row.version),
        stale=release is None or release.id != row.release_id,
        result=cast(schemas.CqResult, row.result),
        detail=detail,
        created_at=row.created_at,
        finished_at=row.finished_at,
    )


def _question(
    row: Question, last: Check | None, release: ReleaseRef | None
) -> schemas.CompetencyQuestion:
    expect = _expect(row)
    expect.keys = [_plain_key(k) for k in expect.keys]
    return schemas.CompetencyQuestion(
        id=row.id,
        ontology_id=row.ontology_id,
        text=row.text,
        note=row.note,
        position=row.position,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
        archived_at=row.archived_at,
        expect=expect,
        last_check=_check(last, release) if last else None,
    )


def _latest() -> Select[UUID]:
    return (
        select(Check.id)
        .where(Check.question_id == Question.id)
        .order_by(Check.created_at.desc(), Check.id.desc())
        .limit(1)
        .correlate(Question)
    )


async def list_questions(
    db: AsyncSession, ontology_id: UUID, archived: bool
) -> schemas.CompetencyQuestionList:
    release = await active_release(db, ontology_id)
    statement = (
        select(Question, Check)
        .outerjoin(Check, Check.id == _latest().scalar_subquery())
        .where(Question.ontology_id == ontology_id)
        .order_by(Question.position, Question.id)
    )
    if not archived:
        statement = statement.where(Question.archived_at.is_(None))
    return schemas.CompetencyQuestionList(
        items=[_question(row, last, release) for row, last in await db.execute(statement)]
    )


def _text(value: str) -> str:
    if not value.strip():
        raise _invalid("Question text must not be blank.")
    return value.strip()


async def prepare_question(
    db: AsyncSession, ontology_id: UUID, body: schemas.CompetencyQuestionCreate, user_id: UUID
) -> Question:
    row = Question(
        ontology_id=ontology_id,
        text=_text(body["text"]),
        note=body.get("note"),
        created_by=user_id,
    )
    await _set_expect(db, row, body["expect"])
    return row


async def append_questions(db: AsyncSession, ontology_id: UUID, rows: list[Question]) -> None:
    last = await db.scalar(
        select(func.max(Question.position)).where(Question.ontology_id == ontology_id)
    )
    for position, row in enumerate(rows, start=last + 1 if last is not None else 0):
        row.position = position
    db.add_all(rows)
    await db.flush()


async def create(
    db: AsyncSession, ontology_id: UUID, body: schemas.CompetencyQuestionCreate, user_id: UUID
) -> schemas.CompetencyQuestion:
    await ontology.lock_ontology(db, ontology_id)
    row = await prepare_question(db, ontology_id, body, user_id)
    await append_questions(db, ontology_id, [row])
    return _question(row, None, None)


async def _locked_question(db: AsyncSession, id: UUID) -> Question:
    ontology_id = await db.scalar(select(Question.ontology_id).where(Question.id == id))
    if ontology_id is not None:
        await ontology.lock_ontology(db, ontology_id)
        row = await db.get(Question, id, populate_existing=True)
        if row is not None and row.archived_at is None:
            return row
    raise AppError(404, "cq.not_found", "Competency question not found.")


async def patch(
    db: AsyncSession, id: UUID, body: schemas.CompetencyQuestionPatch
) -> schemas.CompetencyQuestion:
    row = await _locked_question(db, id)
    if row.revision != body["revision"]:
        raise AppError(409, "cq.stale", "The question has been modified.")
    if "text" in body:
        row.text = _text(body["text"])
    if "note" in body:
        row.note = body["note"]
    if "expect" in body:
        await _set_expect(db, row, body["expect"])
    if "position" in body and body["position"] != row.position:
        position = body["position"]
        delta = 1 if position < row.position else -1
        low, high = sorted((position, row.position))
        await db.execute(
            update(Question)
            .where(
                Question.ontology_id == row.ontology_id,
                Question.archived_at.is_(None),
                Question.position.between(low, high),
                Question.id != id,
            )
            .values(
                position=Question.position + delta,
                revision=Question.revision + 1,
                updated_at=datetime.now(UTC),
            )
        )
        row.position = position
    return await _updated(db, row)


async def archive(db: AsyncSession, id: UUID, revision: int | None) -> schemas.CompetencyQuestion:
    row = await _locked_question(db, id)
    if revision is not None and revision != row.revision:
        raise AppError(409, "cq.stale", "The question has been modified.")
    row.archived_at = datetime.now(UTC)
    return await _updated(db, row)


async def _updated(db: AsyncSession, row: Question) -> schemas.CompetencyQuestion:
    row.revision += 1
    row.updated_at = datetime.now(UTC)
    await db.flush()
    latest = await db.scalar(
        select(Check)
        .where(Check.question_id == row.id)
        .order_by(Check.created_at.desc(), Check.id.desc())
        .limit(1)
    )
    return _question(row, latest, await active_release(db, row.ontology_id))


async def batch_running(db: AsyncSession, ontology_id: UUID) -> bool:
    pending = (
        select(Check.id)
        .join(Question)
        .where(
            Question.ontology_id == ontology_id,
            Check.result == "pending",
            Check.detail["batch"].as_boolean().is_(True),
        )
    )
    return bool(await db.scalar(select(pending.exists())))


async def start_checks(
    db: AsyncSession, id: UUID, user_id: UUID, *, batch: bool
) -> list[schemas.CqCheck]:
    if batch:
        ontology_id = id
        await ontology.lock_ontology(db, ontology_id)
        if await batch_running(db, ontology_id):
            raise AppError(409, "cq.check_running", "A batch check is already running.")
        questions = list(
            await db.scalars(
                select(Question)
                .where(Question.ontology_id == id, Question.archived_at.is_(None))
                .order_by(Question.position, Question.id)
                .limit(50)
            )
        )
    else:
        row = await _locked_question(db, id)
        ontology_id = row.ontology_id
        questions = [row]
    release = await active_release(db, ontology_id)
    if release is None:
        raise AppError(409, "query.no_release", "The ontology has no active release.")
    if not db.info["qa_settings"].ai_configured:
        raise AppError(409, "ai.not_configured", "No model is configured.")

    checks = []
    # create_question commits its own session. Bind it to our transaction: committing
    # a savepoint keeps the ontology lock and hides jobs from workers until checks exist.
    async with AsyncSession(
        bind=await db.connection(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
        info=db.info,
    ) as queue:
        for row in questions:
            question = await qa.create_question(
                queue,
                ontology_id,
                QaQuestionCreate(question=row.text),
                user_id=user_id,
                origin="cq",
                cq_question_id=row.id,
            )
            check = Check(
                question_id=row.id,
                release_id=release.id,
                version=release.version,
                qa_question_id=question.id,
                created_by=user_id,
                result="pending",
                created_at=datetime.now(UTC),
                detail={"batch": batch, "expect": _expect(row).model_dump(mode="json")},
            )
            db.add(check)
            checks.append(check)
    await db.flush()
    return [_check(check, release) for check in checks]


async def record_result(db: AsyncSession, question: QaQuestion) -> None:
    if question.origin != "cq" or question.status not in ("answered", "failed", "unanswerable"):
        return
    check = await db.scalar(
        select(Check)
        .where(Check.qa_question_id == question.id, Check.result == "pending")
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if check is None:
        return
    row = await db.get(Question, check.question_id)
    if row is None or row.ontology_id != question.ontology_id or row.id != question.cq_question_id:
        return
    stored = check.detail or {}
    expect = (
        schemas.CqExpect.model_validate(stored["expect"]) if "expect" in stored else _expect(row)
    )
    result, diff = compare(expect, question)
    if question.status != "failed" and question.release and question.release.id != check.release_id:
        result = "error"
        diff = schemas.CqCheckDetail(
            missing=[], extra=[], actual=None, error_code="query.release_changed"
        )
    detail: dict[str, Any] = diff.model_dump(mode="json", by_alias=True) if diff else {}
    if diff and diff.error_code == "cq.type_mismatch" and question.answer_keys:
        detail["actualTypeId"] = str(question.answer_keys.type_id)
    if question.plan:
        detail["plan"] = question.plan.model_dump(mode="json", by_alias=True)
        if question.evidence:
            detail["labels"] = {str(e.id): e.label for e in question.evidence.elements}
    check.result = result
    check.finished_at = question.finished_at or datetime.now(UTC)
    check.detail = detail


def _references(plan: QaPlan) -> dict[UUID, str]:
    refs: dict[UUID, str] = {}
    if plan.start:
        refs[plan.start.type_id] = plan.start.label
        refs.update((f.property_id, "") for f in plan.start.filters)
    for hop in plan.hops:
        refs[hop.relation_id] = hop.label
        refs[hop.target_type_id] = hop.target_label
        refs.update((f.property_id, "") for f in hop.filters)
    if plan.metric_id:
        refs[plan.metric_id] = ""
    return refs


async def coverage_report(db: AsyncSession, ontology_id: UUID) -> schemas.CqCoverage:
    released = await bindings.released_ontology(db, ontology_id)
    release = None
    names: dict[UUID, str] = {}
    bound: set[UUID] = set()
    if released:
        model = await bindings.bound_model(db, ontology_id)
        metrics = await bindings.released_metrics(db, ontology_id)
        if model is None or not model.release_id == released.release_id == metrics.release.id:
            raise AppError(409, "query.release_changed", "The active release has changed.")
        release = metrics.release
        names = {e.id: e.label_zh or e.label_en or e.local_name or "" for e in released.elements}
        names.update((m.id, m.label_zh) for m in metrics.metrics)
        bound.update(t.type_id for t in model.types)
        bound.update(p.property_id for t in model.types for p in t.properties)
        bound.update(r.relation_id for r in model.relations)
        bound.update(r.inverse_id for r in model.relations if r.inverse_id is not None)
        bound.update(m.id for m in metrics.metrics if metric_is_bound(m, model))
    elif not await ontology.ontology_exists(db, ontology_id):
        raise AppError(404, "ontology.not_found", "Ontology not found.")

    # Keep the last available plan visible while another check is pending or lacks a plan.
    latest_plan = _latest().where(Check.detail["plan"].as_string().is_not(None))
    statement = (
        select(Question.id, Check.detail, _latest().exists())
        .outerjoin(Check, Check.id == latest_plan.scalar_subquery())
        .where(Question.ontology_id == ontology_id, Question.archived_at.is_(None))
        .order_by(Question.position, Question.id)
    )
    items = []
    for id, detail, checked in await db.execute(statement):
        elements = []
        if detail:
            refs = _references(QaPlan.model_validate(detail["plan"]))
            elements = [
                schemas.CoverageElement(
                    id=key,
                    label=names.get(key) or label or detail.get("labels", {}).get(str(key), ""),
                    present=key in names,
                    bound=key in names and key in bound,
                )
                for key, label in refs.items()
            ]
        if any(not e.present for e in elements):
            items.append(CoverageItem(question_id=id, elements=elements, status="element_missing"))
        elif any(not e.bound for e in elements):
            items.append(CoverageItem(question_id=id, elements=elements, status="binding_missing"))
        else:
            items.append(
                CoverageItem(
                    question_id=id, elements=elements, status="ok" if checked else "never_checked"
                )
            )
    return schemas.CqCoverage(release=release, items=items)


async def coverage(db: AsyncSession, ontology_id: UUID) -> list[CoverageItem]:
    return (await coverage_report(db, ontology_id)).items
