"""Review assistance stays advisory and filters model input."""

import asyncio
import json
from collections.abc import Awaitable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from pydantic import BaseModel, SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.db import Base
from ontology_platform.modules.ai import review_assist, schemas
from ontology_platform.modules.ai.gateway import AiUnavailableError
from ontology_platform.modules.ai.models import AiRun, ReviewAssistRow
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs.runner import JobContext
from ontology_platform.modules.ontology.models import (
    ChangeItem,
    ChangeSet,
    Evidence,
    ReviewMemoryRow,
)
from ontology_platform.modules.ontology.review_context import (
    ElementBrief,
    ReviewContext,
    ReviewItem,
    disjoint_pairs,
    review_context,
)
from ontology_platform.modules.ontology.review_memory import MemoryEntry
from ontology_platform.settings import Settings
from support import csrf_headers
from test_ontology_support import (
    add_elements,
    add_ontology,
    element,
    open_change_set,
    proposal,
    sign_in,
)


class FakeGateway:
    def __init__(self, factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.factory = factory
        self.long_summary = False

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        **kwargs: object,
    ) -> T:
        self.calls.append((purpose, instructions, text))
        if self.factory is not None:
            async with self.factory.begin() as db:
                db.add(
                    AiRun(
                        purpose=purpose,
                        model=model,
                        document_id=None,
                        status="succeeded",
                        input_tokens=None,
                        output_tokens=None,
                        latency_ms=0,
                        error_code=None,
                    )
                )
        if purpose == "review.assist.summary":
            return schema.model_validate(
                {
                    "summary": "S" * 700 if self.long_summary else "combined",
                    "groups": [
                        {
                            "title": "All",
                            "from": [{"batch": 1, "group": 1}, {"batch": 2, "group": 1}],
                        },
                        {"title": "Repeated", "from": [{"batch": 1, "group": 1}]},
                    ],
                }
            )
        return schema.model_validate(
            {
                "summary": "S" * 700 if self.long_summary else "batch",
                "groups": [
                    {"title": "A", "items": ["i1"]},
                ],
                "items": [{"ref": "i1", "risks": [], "suggestion": "accept", "reason": "ok"}],
            }
        )

    async def ping(self) -> bool:
        return True


class FailingGateway(FakeGateway):
    def __init__(self, fail_at: int) -> None:
        super().__init__()
        self.fail_at = fail_at

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        **kwargs: object,
    ) -> T:
        if len(self.calls) + 1 == self.fail_at:
            self.calls.append((purpose, instructions, text))
            raise AiUnavailableError("fake", retryable=False)
        return await super().structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            **kwargs,
        )


class LostRunningGateway(FakeGateway):
    def __init__(self, factory: async_sessionmaker[AsyncSession], assist_id: UUID) -> None:
        super().__init__()
        self.factory_for_status = factory
        self.assist_id = assist_id

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        **kwargs: object,
    ) -> T:
        output = await super().structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            **kwargs,
        )
        async with self.factory_for_status.begin() as db:
            row = await db.get(ReviewAssistRow, self.assist_id)
            assert row is not None
            row.status = "failed"
        return output


class TimeoutGateway(FakeGateway):
    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        **kwargs: object,
    ) -> T:
        if len(self.calls) == 1:
            self.calls.append((purpose, instructions, text))
            raise TimeoutError
        return await super().structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            **kwargs,
        )


class SummaryTimeoutGateway(FakeGateway):
    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        **kwargs: object,
    ) -> T:
        if purpose == "review.assist.summary":
            self.calls.append((purpose, instructions, text))
            raise TimeoutError
        return await super().structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            **kwargs,
        )


async def _request(client: AsyncClient, change_set_id: UUID) -> Response:
    return await client.post(
        f"/api/change-sets/{change_set_id}/review-assist",
        json={"locale": "en"},
        headers=csrf_headers(client),
    )


async def _ontology_rows(db: AsyncSession) -> dict[str, list[tuple[object, ...]]]:
    result: dict[str, list[tuple[object, ...]]] = {}
    for table in Base.metadata.tables.values():
        if table.schema == "ontology":
            rows = (await db.execute(select(table).order_by(*table.primary_key.columns))).all()
            result[table.name] = [tuple(row) for row in rows]
    return result


async def test_permissions_status_and_rule_only(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.VIEWER)
    refused = await _request(client, change_set_id)
    assert refused.status_code == 403
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    assert started.status_code == 202
    assert started.json()["status"] == "queued"
    assert (await _request(client, change_set_id)).json()["code"] == "review_assist.running"
    assist_id = UUID(started.json()["id"])
    job = JobContext(uuid4(), {"assistId": str(assist_id)}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    done = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert done["status"] == "done"
    assert done["aiUsed"] is False
    assert done["summary"] is None
    assert len(done["items"]) == 1
    assert done["items"][0]["suggestion"] is None
    row = await db.get(ChangeSet, change_set_id)
    assert row is not None
    row.status = "rejected"
    await db.commit()
    closed = await _request(client, change_set_id)
    assert (closed.status_code, closed.json()["code"]) == (409, "changeset.closed")
    await sign_in(client, db, Role.VIEWER)
    assert (await _request(client, change_set_id)).status_code == 403


async def test_context_edited_and_no_catalog_quote(db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    item = await db.scalar(select(ChangeItem).where(ChangeItem.change_set_id == change_set_id))
    assert item is not None
    item.edited = {"labelZh": "Engine"}
    item.note = "private reviewer note"
    db.add(
        Evidence(
            change_item_id=item.id,
            kind="catalog",
            document_id=None,
            chunk_id=None,
            source={
                "dataSourceName": "private_db",
                "table": "secret_table",
                "column": "secret_column",
                "connection": "private_host",
            },
            quote="private catalog quote",
            char_start=None,
            char_end=None,
        )
    )
    await db.commit()
    ctx = await review_context(db, change_set_id)
    text = review_assist.batch_text(ctx, "en")
    assert "Engine" in text
    assert "private reviewer note" not in text
    for private in (
        "private catalog quote",
        "private_db",
        "secret_table",
        "secret_column",
        "private_host",
    ):
        assert private not in text
    assert '"labelZh": "Motor"' not in text


async def test_context_quotes_are_stably_ordered_and_evidence_is_detected(db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    item = await db.scalar(select(ChangeItem).where(ChangeItem.change_set_id == change_set_id))
    assert item is not None
    for position, quote in ((4, "later"), (2, "first"), (3, "second")):
        db.add(
            Evidence(
                change_item_id=item.id,
                kind="document",
                document_id=UUID(int=1),
                chunk_id=UUID(int=1),
                source=None,
                quote=quote,
                char_start=position,
                char_end=position + len(quote),
            )
        )
    await db.commit()
    ctx = await review_context(db, change_set_id)
    assert ctx.items[0].has_evidence is True
    assert ctx.items[0].quotes == ("first", "second")


async def test_context_missing_other_labels_stays_none(db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name="Motor", label_zh="Motor"),
            proposal("create", "entity_type", local_name="Other", label_zh="Other"),
        ],
    )
    rows = (
        await db.scalars(
            select(ChangeItem)
            .where(ChangeItem.change_set_id == change_set_id)
            .order_by(ChangeItem.seq)
        )
    ).all()
    rows[0].match_kind = "possible"
    rows[0].match_item_id = rows[1].id
    rows[1].proposed = {"localName": "Other"}
    await db.commit()
    ctx = await review_context(db, change_set_id)
    assert ctx.items[0].match_other_label is None


async def test_review_context_disjoint_names_from_active_axioms(db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    a = element(ontology, "entity_type", "A", "类型甲")
    b = element(ontology, "entity_type", "B", "类型乙")
    c = element(ontology, "entity_type", "C", "类型丙")
    owl_disjoint = "http://www.w3.org/2002/07/owl#disjointWith"
    owl_members = "http://www.w3.org/2002/07/owl#members"
    pair = element(
        ontology,
        "axiom",
        "",
        "",
        turtle=f"<{ontology.base_iri}A> <{owl_disjoint}> <{ontology.base_iri}B> .",
    )
    pair.local_name = None
    pair.label_zh = None
    collection = element(
        ontology,
        "axiom",
        "",
        "",
        turtle="[] a <http://www.w3.org/2002/07/owl#AllDisjointClasses> ; "
        f"<{owl_members}> (<{ontology.base_iri}B> <{ontology.base_iri}C>) .",
    )
    collection.local_name = None
    collection.label_zh = None
    await add_elements(db, a, b, c, pair, collection)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="D", label_zh="类型丁")]
    )
    ctx = await review_context(db, change_set_id)
    found = {brief.local_name: brief.disjoint for brief in ctx.elements}
    assert found == {"A": ("类型乙",), "B": ("类型丙", "类型甲"), "C": ("类型乙",)}


def test_disjoint_named_classes_and_invalid_fragments() -> None:
    names = {"urn:a": "A", "urn:b": "B", "urn:c": "C"}
    fragments = [
        "<urn:a> <http://www.w3.org/2002/07/owl#disjointWith> <urn:b> .",
        "[] a <http://www.w3.org/2002/07/owl#AllDisjointClasses> ; "
        "<http://www.w3.org/2002/07/owl#members> (<urn:b> <urn:c>) .",
        "[] <http://www.w3.org/2002/07/owl#disjointWith> <urn:a> .",
        "not turtle",
    ]
    found = disjoint_pairs(fragments, {}, names)
    assert found == {"urn:a": ("B",), "urn:b": ("A", "C"), "urn:c": ("B",)}


def test_model_output_drops_bad_references_and_codes() -> None:
    item = ReviewItem(
        id=uuid4(),
        seq=1,
        fingerprint="x",
        kind="entity_type",
        op="create",
        decision="pending",
        label_zh="Motor",
        label_en="Motor",
        local_name="Motor",
        definition=None,
        parent=None,
        domain=None,
        range=None,
        flags=(),
        confidence=None,
        has_evidence=False,
        quotes=(),
        match_kind=None,
        match_decision=None,
        match_other_label=None,
        kept_fields=(),
        target_stale=False,
    )
    output = schemas.ReviewAssistOut.model_validate(
        {
            "summary": "summary",
            "groups": [
                {"title": "A", "items": ["i1", "i1", "i9"]},
                {"title": "Empty", "items": []},
            ],
            "items": [
                {"ref": "i9", "suggestion": "accept", "reason": "bad", "risks": []},
                {
                    "ref": "i1",
                    "suggestion": "edit",
                    "reason": "x" * 400,
                    "rename": {"localName": "bad-name"},
                    "risks": [{"code": "unknown", "reason": "bad"}],
                },
            ],
        }
    )
    reviewed, groups, dropped = review_assist._validated(output, (item,))
    assert reviewed[item.id][0] == "unsure"
    assert reviewed[item.id][2] is None
    assert len(reviewed[item.id][1]) == 300
    assert groups[0].item_ids == [item.id]
    assert len(groups) == 1
    assert dropped == 4


def test_model_output_caps_titles_names_and_group_count() -> None:
    item = ReviewItem(
        uuid4(),
        1,
        "x",
        "entity_type",
        "create",
        "pending",
        "Motor",
        "Motor",
        "Motor",
        None,
        None,
        None,
        None,
        (),
        None,
        True,
        (),
        None,
        None,
        None,
        (),
        False,
    )
    output = schemas.ReviewAssistOut.model_validate(
        {
            "summary": "s" * 700,
            "groups": [{"title": "T" * 50, "items": [f"i{index}"]} for index in range(1, 14)],
            "items": [
                {
                    "ref": "i1",
                    "risks": [],
                    "suggestion": "edit",
                    "reason": "ok",
                    "rename": {"labelZh": "中" * 250, "labelEn": "E" * 250},
                }
            ],
        }
    )
    batch = (item, *(replace(item, id=uuid4(), seq=index) for index in range(2, 14)))
    reviewed, groups, dropped = review_assist._validated(output, batch)
    assert len(reviewed[item.id][2].label_zh or "") == 200  # type: ignore[union-attr]
    assert len(reviewed[item.id][2].label_en or "") == 200  # type: ignore[union-attr]
    assert len(groups) == 12
    assert len(groups[0].title) == 40
    assert dropped == 1
    no_rename = schemas.ReviewAssistOut.model_validate(
        {
            "summary": "",
            "groups": [],
            "items": [{"ref": "i1", "risks": [], "suggestion": "edit", "reason": "ok"}],
        }
    )
    assert review_assist._validated(no_rename, (item,))[0][item.id][0] == "unsure"


def test_each_batch_selects_its_own_elements_and_memory() -> None:
    item = ReviewItem(
        id=uuid4(),
        seq=1,
        fingerprint="x",
        kind="entity_type",
        op="create",
        decision="pending",
        label_zh="Motor",
        label_en=None,
        local_name="Motor",
        definition=None,
        parent=None,
        domain=None,
        range=None,
        flags=(),
        confidence=None,
        has_evidence=False,
        quotes=(),
        match_kind=None,
        match_decision=None,
        match_other_label=None,
        kept_fields=(),
        target_stale=False,
    )
    second = replace(item, id=uuid4(), seq=2, label_zh="Engine", local_name="Engine")
    element = ElementBrief(
        uuid4(), "entity_type", "MotorPart", None, "MotorPart", None, None, None, ()
    )
    second_element = replace(element, id=uuid4(), label_zh="EnginePart", local_name="EnginePart")
    now = datetime.now(UTC)
    memory = MemoryEntry(
        uuid4(),
        "rejected",
        "entity_type",
        "t:motorpart",
        "MotorPart",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        now,
        None,
    )
    second_memory = replace(memory, id=uuid4(), key="t:enginepart", label="EnginePart")
    pool = ReviewContext(
        uuid4(),
        uuid4(),
        "open",
        "manual",
        (item, second),
        (element, second_element),
        (memory, second_memory),
    )
    first = review_assist.select_batch_context(pool, (item,))
    later = review_assist.select_batch_context(pool, (second,))
    assert first.elements[0] == element
    assert later.elements[0] == second_element
    assert "EnginePart" in review_assist.batch_text(later, "en")
    assert first.rejected == (memory,)
    assert later.rejected == (second_memory,)
    single = replace(pool, items=(item,), elements=(element,), rejected=(memory,))
    assert review_assist.select_batch_context(single, single.items) == single


async def test_two_model_batches_send_only_allowlisted_data_and_leave_ontology_untouched(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(81)
        ],
    )
    first_item = await db.scalar(
        select(ChangeItem).where(ChangeItem.change_set_id == change_set_id, ChangeItem.seq == 1)
    )
    assert first_item is not None
    first_item.edited = {"labelZh": "PrivateEditedMotor"}
    first_item.note = "private reviewer note"
    db.add(
        Evidence(
            change_item_id=first_item.id,
            kind="catalog",
            document_id=None,
            chunk_id=None,
            source={
                "dataSourceId": str(uuid4()),
                "schema": "private_db",
                "table": "secret_table",
                "column": "secret_column",
                "fact": "column",
            },
            quote="private catalog quote",
            char_start=None,
            char_end=None,
        )
    )
    for index in range(3):
        db.add(
            Evidence(
                change_item_id=first_item.id,
                kind="document",
                document_id=uuid4(),
                chunk_id=uuid4(),
                source=None,
                quote="Q" * 250 if index == 0 else f"extra quote {index}",
                char_start=0,
                char_end=250 if index == 0 else 13,
            )
        )
    existing = element(ontology, "entity_type", "Existing", "Existing")
    binding = element(
        ontology,
        "type_binding",
        "",
        "",
        subject_id=existing.id,
        binding={"schema": "secret_schema", "table": "physical_secret_table"},
    )
    binding.local_name = None
    binding.label_zh = None
    await add_elements(db, existing, binding)
    await db.commit()
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    assert started.status_code == 202
    assist_id = UUID(started.json()["id"])
    before = await _ontology_rows(db)
    fake = FakeGateway(app.state.session_factory)
    configured = settings.model_copy(
        update={"openai_api_key": SecretStr("fake"), "ai_model": "fake"}
    )
    job = JobContext(uuid4(), {"assistId": str(assist_id)}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    assert before == await _ontology_rows(db)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert before == await _ontology_rows(db)
    assert (await _request(client, change_set_id)).status_code == 202
    assert before == await _ontology_rows(db)
    assert result["status"] == "done"
    assert result["aiUsed"] is True
    assert result["summary"] == "combined"
    assert len(result["groups"]) == 1
    assert result["counts"]["total"] == 81
    assert [call[0] for call in fake.calls] == [
        "review.assist",
        "review.assist",
        "review.assist.summary",
    ]
    purposes = (await db.scalars(select(AiRun.purpose).order_by(AiRun.created_at))).all()
    assert purposes == ["review.assist", "review.assist", "review.assist.summary"]
    assert "Motor80" in fake.calls[1][2]
    assert "Motor80" not in fake.calls[0][2]
    assert "Motor80" not in fake.calls[2][2]
    assert "i1" not in fake.calls[2][2]
    first_text = fake.calls[0][2]
    assert "PrivateEditedMotor" in first_text
    assert '"labelZh": "Motor0"' not in first_text
    for private in (
        "private reviewer note",
        "private catalog quote",
        "private_db",
        "secret_table",
        "secret_column",
        "physical_secret_table",
    ):
        assert private not in first_text
    payload = json.loads(first_text.split("\n", 1)[1])
    assert len(payload["items"][0]["quotes"]) == 2
    assert all(len(quote) <= 200 for quote in payload["items"][0]["quotes"])
    assert all(
        "PrivateEditedMotor" not in call[1] and "extra quote" not in call[1] for call in fake.calls
    )
    assert all(
        name not in instructions
        for _, instructions, _ in fake.calls
        for name in ("PrivateEditedMotor", *(f"Motor{i}" for i in range(1, 81)))
    )


async def test_stale_fingerprint_excludes_decision_and_note(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    item = await db.scalar(select(ChangeItem).where(ChangeItem.change_set_id == change_set_id))
    assert item is not None
    item.decision = "accepted"
    item.note = "note changed"
    await db.commit()
    url = f"/api/change-sets/{change_set_id}/review-assist"
    assert (await client.get(url)).json()["items"][0]["stale"] is False
    item.edited = {"labelZh": "Engine"}
    await db.commit()
    result = (await client.get(url)).json()
    assert result["items"][0]["stale"] is True
    assert result["counts"]["stale"] == 1


async def test_open_get_recomputes_rule_risks_but_closed_get_uses_saved(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    item = await db.scalar(select(ChangeItem).where(ChangeItem.change_set_id == change_set_id))
    assert item is not None
    item.flags = ["possible_duplicate"]
    await db.commit()
    url = f"/api/change-sets/{change_set_id}/review-assist"
    open_result = (await client.get(url)).json()
    assert "possible_duplicate" in [risk["detail"] for risk in open_result["items"][0]["risks"]]
    change_set = await db.get(ChangeSet, change_set_id)
    assert change_set is not None
    change_set.status = "rejected"
    await db.commit()
    closed_result = (await client.get(url)).json()
    assert "possible_duplicate" not in [
        risk["detail"] for risk in closed_result["items"][0]["risks"]
    ]


async def test_rejected_rule_uses_full_memory_pool_on_job_and_open_get(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    now = datetime.now(UTC)
    matching = uuid4()
    for index in range(70):
        db.add(
            ReviewMemoryRow(
                id=matching if index == 69 else uuid4(),
                ontology_id=ontology.id,
                kind="rejected",
                element_kind="entity_type",
                key=f"t:motor-part-{index}",
                label="Motors" if index == 69 else "Motor",
                detail={},
                created_at=now - timedelta(minutes=1) if index == 69 else now,
            )
        )
    await db.commit()
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    row = await db.get(ReviewAssistRow, UUID(started.json()["id"]))
    assert row is not None
    await db.refresh(row)
    saved = row.result["items"][0]["risks"]
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    current = result["items"][0]["risks"]
    assert saved == current
    assert any(
        risk["detail"] == "similar_to_rejected" and risk["memoryEntryId"] == str(matching)
        for risk in current
    )


async def test_failed_batch_keeps_completed_result(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(81)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = FailingGateway(2)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["status"] == "partial"
    assert result["errorCode"] == "ai.unavailable"
    assert result["aiUsed"] is True
    assert result["items"][0]["suggestion"] == "accept"
    assert result["items"][80]["suggestion"] is None


async def test_all_model_batches_failed_still_return_rules(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = FailingGateway(1)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["status"] == "partial"
    assert result["aiUsed"] is False
    assert result["summary"] is None
    assert result["items"][0]["suggestion"] is None
    assert result["items"][0]["risks"]


async def test_summary_failure_uses_first_batch_summary(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(81)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = FailingGateway(3)
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["status"] == "done"
    assert result["errorCode"] is None
    assert result["summary"] == "batch"
    assert len(result["groups"]) == 2


async def test_summary_timeout_uses_first_batch_without_changing_status(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(2)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(
        update={
            "openai_api_key": SecretStr("fake"),
            "review_assist_batch": 1,
        }
    )
    fake = SummaryTimeoutGateway()
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert [call[0] for call in fake.calls] == [
        "review.assist",
        "review.assist",
        "review.assist.summary",
    ]
    assert (result["status"], result["errorCode"], result["summary"]) == ("done", None, "batch")
    assert len(result["groups"]) == 2


async def test_cap_items_before_splitting_batches(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(121)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(
        update={
            "openai_api_key": SecretStr("fake"),
            "review_assist_batch": 50,
            "review_assist_items_max": 120,
        }
    )
    fake = FakeGateway()
    fake.long_summary = True
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    batches = [
        json.loads(call[2].split("\n", 1)[1])["items"]
        for call in fake.calls
        if call[0] == "review.assist"
    ]
    assert [len(batch) for batch in batches] == [50, 50, 20]
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["truncated"] is True
    assert len(result["summary"]) == 600
    assert result["items"][120]["suggestion"] is None


async def test_expired_deadline_skips_later_batch(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(2)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(
        update={"openai_api_key": SecretStr("fake"), "review_assist_batch": 1}
    )
    ticks = iter((0.0, 1.0, 301.0))
    monkeypatch.setattr(review_assist, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    timeouts: list[float] = []
    original_wait_for = asyncio.wait_for

    async def tracked_wait_for(awaitable: Awaitable[object], **options: float) -> object:
        timeouts.append(options["timeout"])
        return await original_wait_for(awaitable, **options)

    monkeypatch.setattr(asyncio, "wait_for", tracked_wait_for)
    fake = FakeGateway()
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, fake, "fake", configured)(
        job
    )
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert len(fake.calls) == 1
    assert len(timeouts) == 1
    assert (result["status"], result["errorCode"]) == ("partial", "review_assist.timeout")


async def test_expired_deadline_skips_summary_without_failing_batches(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(2)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(
        update={"openai_api_key": SecretStr("fake"), "review_assist_batch": 1}
    )
    ticks = iter((0.0, 1.0, 2.0, 301.0))
    monkeypatch.setattr(review_assist, "time", SimpleNamespace(monotonic=lambda: next(ticks)))
    fake = FakeGateway()
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, fake, "fake", configured)(
        job
    )
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert len(fake.calls) == 2
    assert (result["status"], result["errorCode"], result["summary"]) == ("done", None, "batch")


async def test_batch_timeout_preserves_earlier_items(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(81)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = TimeoutGateway()
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["status"] == "partial"
    assert result["errorCode"] == "review_assist.timeout"
    assert result["items"][0]["suggestion"] == "accept"
    assert result["items"][80]["suggestion"] is None


async def test_stale_running_row_is_failed_before_next_request(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    first = await _request(client, change_set_id)
    assert first.status_code == 202
    row = await db.get(ReviewAssistRow, UUID(first.json()["id"]))
    assert row is not None
    row.created_at = datetime.now(UTC) - timedelta(hours=2)
    await db.commit()
    second = await _request(client, change_set_id)
    assert second.status_code == 202
    await db.refresh(row)
    assert (row.status, row.error_code) == ("failed", "review_assist.timeout")


async def test_rate_limit_has_retry_after(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    ontology = await add_ontology(db)
    first_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    second_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Engine", label_zh="Engine")]
    )
    app.state.settings = app.state.settings.model_copy(update={"review_assists_per_hour": 1})
    await sign_in(client, db, Role.EDITOR)
    assert (await _request(client, first_id)).status_code == 202
    limited = await _request(client, second_id)
    assert (limited.status_code, limited.json()["code"]) == (429, "review_assist.rate_limited")
    assert int(limited.headers["Retry-After"]) > 0


async def test_concurrent_requests_create_only_one_running_assist(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    responses = await asyncio.gather(
        _request(client, change_set_id),
        _request(client, change_set_id),
    )
    assert sorted(response.status_code for response in responses) == [202, 409]
    refused = next(response for response in responses if response.status_code == 409)
    assert refused.json()["code"] == "review_assist.running"
    count = await db.scalar(select(func.count()).select_from(ReviewAssistRow))
    assert count == 1


async def test_insert_conflict_returns_running_and_session_remains_usable(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    assert (await _request(client, change_set_id)).status_code == 202
    original_scalar = AsyncSession.scalar
    suppressed = False

    async def skip_running_precheck(
        session: AsyncSession,
        statement: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        nonlocal suppressed
        if not suppressed and "SELECT ai.review_assists.id" in str(statement):
            suppressed = True
            return None
        return await original_scalar(session, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "scalar", skip_running_precheck)
    refused = await _request(client, change_set_id)
    assert suppressed is True
    assert (refused.status_code, refused.json()["code"]) == (409, "review_assist.running")
    assert await db.scalar(select(func.count()).select_from(ReviewAssistRow)) == 1


async def test_more_than_400_items_are_rule_checked_and_marked_truncated(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(401)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    assert started.status_code == 202
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["truncated"] is False
    assert result["counts"]["total"] == 401
    assert len(result["items"]) == 401
    assert result["items"][-1]["risks"]
    assert result["items"][-1]["suggestion"] is None


async def test_configured_ai_marks_default_cap_truncated(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db,
        ontology,
        [
            proposal("create", "entity_type", local_name=f"Motor{i}", label_zh=f"Motor{i}")
            for i in range(401)
        ],
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = FakeGateway()
    job = JobContext(uuid4(), {"assistId": started.json()["id"]}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    result = (await client.get(f"/api/change-sets/{change_set_id}/review-assist")).json()
    assert result["truncated"] is True
    assert result["counts"]["total"] == 401
    assert len([call for call in fake.calls if call[0] == "review.assist"]) == 5
    assert result["items"][400]["suggestion"] is None


async def test_worker_does_not_overwrite_row_that_lost_running_status(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    assist_id = UUID(started.json()["id"])
    configured = settings.model_copy(update={"openai_api_key": SecretStr("fake")})
    fake = LostRunningGateway(app.state.session_factory, assist_id)
    job = JobContext(uuid4(), {"assistId": str(assist_id)}, app.state.session_factory)
    await review_assist.make_review_assistant(
        app.state.session_factory,
        fake,
        "fake",
        configured,
    )(job)
    row = await db.get(ReviewAssistRow, assist_id)
    assert row is not None
    await db.refresh(row)
    assert row.status == "failed"
    assert row.result == {}


async def test_reclaimed_running_job_does_not_leave_row_stuck(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    settings: Settings,
) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Motor", label_zh="Motor")]
    )
    await sign_in(client, db, Role.EDITOR)
    started = await _request(client, change_set_id)
    assist_id = UUID(started.json()["id"])
    row = await db.get(ReviewAssistRow, assist_id)
    assert row is not None
    row.status = "running"
    await db.commit()
    job = JobContext(uuid4(), {"assistId": str(assist_id)}, app.state.session_factory)
    await review_assist.make_review_assistant(app.state.session_factory, None, None, settings)(job)
    await db.refresh(row)
    assert (row.status, row.error_code) == ("failed", "review_assist.timeout")
