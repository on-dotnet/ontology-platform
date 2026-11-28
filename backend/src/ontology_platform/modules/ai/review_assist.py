"""Advisory review jobs and readback."""

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai import candidates, schemas
from ontology_platform.modules.ai.gateway import AiError, ModelGateway
from ontology_platform.modules.ai.models import ReviewAssistRow
from ontology_platform.modules.ai.review_prompts import (
    REVIEW_INSTRUCTIONS,
    REVIEW_SUMMARY_INSTRUCTIONS,
)
from ontology_platform.modules.ai.review_rules import rule_risks
from ontology_platform.modules.identity.service import Principal, display_names
from ontology_platform.modules.jobs import service as jobs
from ontology_platform.modules.jobs.runner import Handler, JobContext
from ontology_platform.modules.ontology import rules as ontology_rules
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.review_context import (
    ElementBrief,
    ReviewContext,
    ReviewItem,
    item_fingerprints,
    related_name,
    review_context,
)
from ontology_platform.settings import Settings

JOB_KIND = "review.assist"
AI_CODES = frozenset({"weak_evidence", "conflict", "duplicate", "naming"})


def _now() -> datetime:
    return datetime.now(UTC)


async def _out(
    db: AsyncSession, row: ReviewAssistRow, *, current: bool = False
) -> schemas.ReviewAssist:
    names = await display_names(db, [row.requested_by] if row.requested_by else [])
    saved = row.result or {}
    raw_items = saved.get("items", []) if row.status in ("done", "partial") else []
    fingerprints = await item_fingerprints(db, row.change_set_id) if raw_items else {}
    current_rules: dict[UUID, tuple[schemas.AssistRisk, ...]] = {}
    if current and raw_items:
        current_rules = rule_risks(
            await review_context(db, row.change_set_id, memory_max=Settings().review_memory_max)
        )
    items: list[schemas.AssistItem] = []
    for raw in raw_items:
        item = schemas.AssistItem.model_validate(raw)
        item.stale = fingerprints.get(item.item_id) != saved.get("fingerprints", {}).get(
            str(item.item_id)
        )
        if current:
            item.risks = [risk for risk in item.risks if risk.source == "ai"] + list(
                current_rules.get(item.item_id, ())
            )
        items.append(item)
    valid = [item for item in items if not item.stale]
    return schemas.ReviewAssist(
        id=row.id,
        change_set_id=row.change_set_id,
        status=cast(schemas.AssistStatus, row.status),
        error_code=row.error_code,
        ai_used=row.ai_used,
        truncated=row.truncated,
        locale=cast(schemas.Locale, row.locale),
        requested_by=row.requested_by,
        requested_by_name=names.get(row.requested_by) if row.requested_by else None,
        created_at=row.created_at,
        finished_at=row.finished_at,
        summary=saved.get("summary"),
        groups=[schemas.AssistGroup.model_validate(g) for g in saved.get("groups", [])],
        items=items,
        counts=schemas.AssistCounts(
            total=row.items_total,
            ai_reviewed=sum(item.suggestion is not None for item in items),
            with_risks=sum(bool(item.risks) for item in valid),
            suggest_reject=sum(item.suggestion == "reject" for item in valid),
            suggest_edit=sum(item.suggestion == "edit" for item in valid),
            stale=len(items) - len(valid),
            dropped=row.dropped,
        ),
    )


async def request_assist(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    user: Principal,
    locale: schemas.Locale,
    settings: Settings,
) -> schemas.ReviewAssist:
    change_set = await ontology_service.change_set_header(db, change_set_id)
    if change_set.status != "open":
        raise AppError(409, "changeset.closed", "Change set is closed.")
    now = _now()
    cutoff = now - timedelta(seconds=settings.review_assist_timeout_seconds + 120)
    await db.execute(
        update(ReviewAssistRow)
        .where(
            ReviewAssistRow.change_set_id == change_set_id,
            ReviewAssistRow.status.in_(("queued", "running")),
            ReviewAssistRow.created_at < cutoff,
        )
        .values(status="failed", error_code="review_assist.timeout", finished_at=now)
    )
    await db.commit()
    running = await db.scalar(
        select(ReviewAssistRow.id).where(
            ReviewAssistRow.change_set_id == change_set_id,
            ReviewAssistRow.status.in_(("queued", "running")),
        )
    )
    if running:
        raise AppError(409, "review_assist.running", "Review assistance is already running.")
    lock_id = int.from_bytes(user.id.bytes[:8], signed=True)
    await db.execute(select(func.pg_advisory_xact_lock(lock_id)))
    recent = ReviewAssistRow.created_at > now - timedelta(hours=1)
    oldest = await db.scalar(
        select(func.min(ReviewAssistRow.created_at)).where(
            ReviewAssistRow.requested_by == user.id,
            recent,
        )
    )
    count = (
        await db.scalar(
            select(func.count())
            .select_from(ReviewAssistRow)
            .where(
                ReviewAssistRow.requested_by == user.id,
                recent,
            )
        )
        or 0
    )
    if count >= settings.review_assists_per_hour:
        wait = max(1, ceil(((oldest or now) + timedelta(hours=1) - now).total_seconds()))
        raise AppError(
            429,
            "review_assist.rate_limited",
            "Too many review requests.",
            headers={"Retry-After": str(wait)},
        )
    row = ReviewAssistRow(
        id=uuid4(),
        change_set_id=change_set_id,
        ontology_id=change_set.ontology_id,
        requested_by=user.id,
        locale=locale,
        status="queued",
        created_at=now,
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError as exc:
        if "uq_review_assists_change_set_id_running" not in str(exc):
            raise
        raise AppError(
            409, "review_assist.running", "Review assistance is already running."
        ) from None
    await jobs.enqueue(db, JOB_KIND, {"assistId": str(row.id)})
    await db.commit()
    return await _out(db, row)


async def latest_assist(db: AsyncSession, change_set_id: UUID) -> schemas.ReviewAssist | None:
    change_set = await ontology_service.change_set_header(db, change_set_id)
    row = await db.scalar(
        select(ReviewAssistRow)
        .where(ReviewAssistRow.change_set_id == change_set_id)
        .order_by(ReviewAssistRow.created_at.desc(), ReviewAssistRow.id.desc())
        .limit(1)
    )
    return await _out(db, row, current=change_set.status == "open") if row else None


def select_batch_context(ctx: ReviewContext, items: tuple[ReviewItem, ...]) -> ReviewContext:
    terms = tuple(
        candidates.normalize(name)
        for item in items
        for name in (item.label_zh, item.label_en, item.domain, item.range)
        if name
    )
    elements = sorted(
        ctx.elements,
        key=lambda element: (
            not any(
                related_name(name, terms)
                for name in (element.label_zh, element.label_en, element.local_name)
                if name
            ),
            element.label_zh or element.label_en or element.local_name,
        ),
    )[:400]
    rejected = [
        entry
        for entry in ctx.rejected
        if (
            related_name(entry.label, terms) or related_name(entry.label_en or "", terms)
            if entry.element_kind == "entity_type"
            else any(
                candidates.normalize(name) in terms for name in (entry.domain, entry.range) if name
            )
        )
    ]
    rejected.sort(key=lambda entry: entry.last_hit_at or entry.created_at, reverse=True)
    return ReviewContext(
        ctx.change_set_id,
        ctx.ontology_id,
        ctx.status,
        ctx.source,
        items,
        tuple(elements),
        tuple(rejected[:60]),
    )


def batch_text(ctx: ReviewContext, locale: schemas.Locale) -> str:
    """Only frozen allowlisted fields enter the model input."""
    payload = {
        "items": [
            {
                "ref": f"i{index}",
                "kind": item.kind,
                "op": item.op,
                "labelZh": item.label_zh,
                "labelEn": item.label_en,
                "localName": item.local_name,
                "definition": item.definition,
                "parent": item.parent,
                "domain": item.domain,
                "range": item.range,
                "flags": item.flags,
                "confidence": item.confidence,
                "quotes": item.quotes,
                "matchOtherLabel": item.match_other_label,
            }
            for index, item in enumerate(ctx.items, 1)
        ],
        "elements": [
            {
                "kind": e.kind,
                "labelZh": e.label_zh,
                "labelEn": e.label_en,
                "localName": e.local_name,
                "parent": e.parent,
                "domain": e.domain,
                "range": e.range,
                "disjoint": e.disjoint,
            }
            for e in ctx.elements
        ],
        "rejected": [
            {
                "kind": e.element_kind,
                "label": e.label,
                "reason": e.reason,
                "domain": e.domain,
                "range": e.range,
            }
            for e in ctx.rejected
        ],
    }
    return f"language: {locale}\n" + json.dumps(payload, ensure_ascii=False)


def _validated(
    output: schemas.ReviewAssistOut,
    batch: tuple[ReviewItem, ...],
    elements: tuple[ElementBrief, ...] = (),
) -> tuple[
    dict[
        UUID,
        tuple[schemas.AssistSuggestion, str, schemas.AssistRename | None, list[schemas.AssistRisk]],
    ],
    list[schemas.AssistGroup],
    int,
]:
    refs = {f"i{index}": item.id for index, item in enumerate(batch, 1)}
    element_refs = {element.local_name: element.id for element in elements}
    answer: dict[
        UUID,
        tuple[schemas.AssistSuggestion, str, schemas.AssistRename | None, list[schemas.AssistRisk]],
    ] = {}
    dropped = 0
    for raw_model in output.items:
        raw = raw_model.model_dump(mode="json", by_alias=True)
        ref = raw.get("ref")
        if not isinstance(ref, str) or ref not in refs or refs[ref] in answer:
            dropped += 1
            continue
        suggestion = raw.get("suggestion")
        if suggestion not in ("accept", "reject", "edit", "unsure"):
            dropped += 1
            continue
        risks: list[schemas.AssistRisk] = []
        raw_risks = raw.get("risks", [])
        for risk in raw_risks if isinstance(raw_risks, list) else []:
            if not isinstance(risk, dict) or risk.get("code") not in AI_CODES:
                dropped += 1
                continue
            related = risk.get("related", [])
            related_ids = [refs[r] for r in related if isinstance(r, str) and r in refs][:5]
            element_ids = [
                element_refs[r] for r in related if isinstance(r, str) and r in element_refs
            ][:5]
            dropped += sum(
                r not in refs and r not in element_refs for r in related if isinstance(r, str)
            )
            risks.append(
                schemas.AssistRisk(
                    code=cast(schemas.RiskCode, risk["code"]),
                    source="ai",
                    detail=None,
                    reason=str(risk.get("reason", ""))[:300],
                    related_item_ids=related_ids,
                    related_element_ids=element_ids,
                    memory_entry_id=None,
                )
            )
        rename = None
        raw_rename = raw.get("rename")
        if suggestion == "edit" and isinstance(raw_rename, dict):
            values = {
                key: raw_rename[key]
                for key in ("labelZh", "labelEn", "localName")
                if isinstance(raw_rename.get(key), str) and raw_rename[key].strip()
            }
            local = values.get("localName")
            if local and (
                not ontology_rules.LOCAL_NAME.fullmatch(local)
                or len(local) > ontology_rules.LOCAL_NAME_MAX_LENGTH
            ):
                del values["localName"]
                dropped += 1
            if values:
                for key in ("labelZh", "labelEn"):
                    if key in values:
                        values[key] = values[key][:200]
                rename = schemas.AssistRename.model_validate(values)
            else:
                suggestion = "unsure"
        elif suggestion == "edit":
            suggestion = "unsure"
        answer[refs[ref]] = (
            cast(schemas.AssistSuggestion, suggestion),
            str(raw.get("reason", ""))[:300],
            rename,
            risks,
        )
    groups: list[schemas.AssistGroup] = []
    assigned: set[UUID] = set()
    for group_model in output.groups[:12]:
        raw = group_model.model_dump(mode="json", by_alias=True)
        refs_in_group = raw.get("items", [])
        ids = []
        for ref in refs_in_group if isinstance(refs_in_group, list) else []:
            if ref not in refs:
                dropped += 1
            elif refs[ref] not in assigned:
                ids.append(refs[ref])
                assigned.add(refs[ref])
        if ids:
            groups.append(schemas.AssistGroup(title=str(raw.get("title", ""))[:40], item_ids=ids))
    dropped += max(0, len(output.groups) - 12)
    return answer, groups, dropped


@dataclass(frozen=True)
class AssistOutcome:
    status: Literal["done", "partial"]
    error_code: str | None
    ai_used: bool
    truncated: bool
    dropped: int
    summary: str | None
    groups: list[schemas.AssistGroup]
    items: tuple[schemas.AssistItem, ...]

    def stored_result(self, ctx: ReviewContext) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "groups": [g.model_dump(mode="json", by_alias=True) for g in self.groups],
            "items": [item.model_dump(mode="json", by_alias=True) for item in self.items],
            "fingerprints": {str(item.id): item.fingerprint for item in ctx.items},
        }


def context_elements_max(settings: Settings) -> int:
    return 400 * ceil(settings.review_assist_items_max / settings.review_assist_batch)


def _is_model_error(exc: Exception) -> bool:
    if isinstance(exc, AiError):
        return exc.code in ("ai.unavailable", "ai.invalid_output")
    return isinstance(exc, ValidationError)


async def run_assist(
    ctx: ReviewContext,
    gateway: ModelGateway | None,
    model: str | None,
    settings: Settings,
    locale: schemas.Locale,
    *,
    deadline: float,
    document_id: UUID | None = None,
    fail_on_internal_error: bool = False,
) -> AssistOutcome:
    """Review a frozen change set. With no gateway, only the rules run.

    Evaluations propagate internal errors so that only model failures affect their scores.
    """
    batch_size = settings.review_assist_batch
    max_items = settings.review_assist_items_max
    risks = rule_risks(ctx)
    items = {
        item.id: schemas.AssistItem(
            item_id=item.id,
            stale=False,
            risks=list(risks[item.id]),
            suggestion=None,
            reason=None,
            rename=None,
        )
        for item in ctx.items
    }
    capped = ctx.items[:max_items]
    batches = [tuple(capped[i : i + batch_size]) for i in range(0, len(capped), batch_size)]
    completed: list[tuple[int, str, list[schemas.AssistGroup]]] = []
    first_error: str | None = None
    dropped = 0
    if gateway and model:
        for batch_number, batch in enumerate(batches, 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                first_error = first_error or "review_assist.timeout"
                break
            try:
                chosen = select_batch_context(ctx, batch)
                output = await asyncio.wait_for(
                    gateway.structured(
                        purpose=JOB_KIND,
                        model=model,
                        instructions=REVIEW_INSTRUCTIONS,
                        text=batch_text(chosen, locale),
                        schema=schemas.ReviewAssistOut,
                        document_id=document_id,
                    ),
                    timeout=remaining,
                )
                reviewed, groups, lost = _validated(output, batch, chosen.elements)
                dropped += lost
                for item_id, (suggestion, reason, rename, ai_risks) in reviewed.items():
                    items[item_id].suggestion = suggestion
                    items[item_id].reason = reason
                    items[item_id].rename = rename
                    items[item_id].risks.extend(ai_risks)
                completed.append((batch_number, output.summary[:600], groups))
            except TimeoutError:
                first_error = first_error or "review_assist.timeout"
                break
            except (AiError, ValueError, TypeError, KeyError) as exc:
                if fail_on_internal_error and not _is_model_error(exc):
                    raise
                first_error = first_error or (
                    exc.code if isinstance(exc, AiError) else "ai.invalid_output"
                )
    summary = completed[0][1] if completed else None
    groups = [group for _, _, group_list in completed for group in group_list][:12]
    if len(completed) > 1 and gateway and model:
        input_data = [
            {
                "batch": batch_number,
                "summary": summary_text,
                "groups": [
                    {"group": j + 1, "title": group.title, "count": len(group.item_ids)}
                    for j, group in enumerate(group_list)
                ],
            }
            for batch_number, summary_text, group_list in completed
        ]
        remaining = deadline - time.monotonic()
        try:
            if remaining <= 0:
                raise TimeoutError
            summary_output = await asyncio.wait_for(
                gateway.structured(
                    purpose="review.assist.summary",
                    model=model,
                    instructions=REVIEW_SUMMARY_INSTRUCTIONS,
                    text=f"language: {locale}\n" + json.dumps(input_data, ensure_ascii=False),
                    schema=schemas.ReviewAssistSummaryOut,
                    document_id=document_id,
                ),
                timeout=remaining,
            )
            summary = summary_output.summary[:600]
            merged: list[schemas.AssistGroup] = []
            assigned: set[UUID] = set()
            for raw_model in summary_output.groups[:12]:
                raw = raw_model.model_dump(mode="json", by_alias=True)
                ids: list[UUID] = []
                sources = raw.get("from", [])
                for source in sources if isinstance(sources, list) else []:
                    if isinstance(source, dict):
                        b, g = source.get("batch"), source.get("group")
                        if (
                            isinstance(b, int)
                            and isinstance(g, int)
                            and 1 <= b <= len(batches)
                            and any(
                                index == b and 1 <= g <= len(group_list)
                                for index, _, group_list in completed
                            )
                        ):
                            ids.extend(
                                next(
                                    group_list[g - 1].item_ids
                                    for index, _, group_list in completed
                                    if index == b
                                )
                            )
                unique = [item_id for item_id in dict.fromkeys(ids) if item_id not in assigned]
                assigned.update(unique)
                if unique:
                    merged.append(
                        schemas.AssistGroup(
                            title=str(raw.get("title", ""))[:40],
                            item_ids=unique,
                        )
                    )
            # A summary whose groups all cite unknown sources keeps the batches' groups.
            groups = merged or groups
        except TimeoutError:
            pass
        except (AiError, ValueError, TypeError, KeyError) as exc:
            if fail_on_internal_error and not _is_model_error(exc):
                raise
    return AssistOutcome(
        status="partial" if first_error else "done",
        error_code=first_error,
        ai_used=bool(completed),
        truncated=bool(gateway and model) and len(ctx.items) > max_items,
        dropped=dropped,
        summary=summary,
        groups=groups,
        items=tuple(items.values()),
    )


def make_review_assistant(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway | None,
    model: str | None,
    settings: Settings,
) -> Handler:
    async def handle(job: JobContext) -> None:
        deadline = time.monotonic() + settings.review_assist_timeout_seconds
        assist_id = UUID(job.payload["assistId"])
        async with session_factory.begin() as db:
            await job.check_lease(db)
            row = await db.get(ReviewAssistRow, assist_id, with_for_update=True)
            if row is None:
                return
            if row.status == "running":
                row.status = "failed"
                row.error_code = "review_assist.timeout"
                row.finished_at = _now()
                return
            if row.status != "queued":
                return
            row.status = "running"
            change_set_id = row.change_set_id
            locale = cast(schemas.Locale, row.locale)
        try:
            async with session_factory() as db:
                ctx = await review_context(
                    db,
                    change_set_id,
                    elements_max=context_elements_max(settings),
                    memory_max=settings.review_memory_max,
                )
            outcome = await run_assist(
                ctx,
                gateway if settings.ai_configured else None,
                model,
                settings,
                locale,
                deadline=deadline,
            )
            result = outcome.stored_result(ctx)
            async with session_factory.begin() as db:
                await job.check_lease(db)
                row = await db.get(ReviewAssistRow, assist_id, with_for_update=True)
                if row is None or row.status != "running":
                    return
                row.result = result
                row.status = outcome.status
                row.error_code = outcome.error_code
                row.ai_used = outcome.ai_used
                row.truncated = outcome.truncated
                row.items_total = len(ctx.items)
                row.items_ai = sum(item.suggestion is not None for item in outcome.items)
                row.dropped = outcome.dropped
                row.finished_at = _now()
        except Exception:
            async with session_factory.begin() as db:
                await job.check_lease(db)
                row = await db.get(ReviewAssistRow, assist_id, with_for_update=True)
                if row is not None and row.status == "running":
                    row.status = "failed"
                    row.error_code = "internal.error"
                    row.finished_at = _now()
            raise

    return handle
