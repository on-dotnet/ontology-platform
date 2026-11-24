"""The AI assistant (spec 002, section 10): requests, the job that answers them with a change
set for review, the checks that drop bad operations, and failures."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.assistant import JOB_KIND, OPERATIONS_MAX, make_assistant
from ontology_platform.modules.ai.gateway import AiNotConfiguredError, AiUnavailableError
from ontology_platform.modules.ai.models import AssistantRequest
from ontology_platform.modules.ai.prompts import (
    AssistantFieldsOut,
    AssistantOperationOut,
    AssistantOut,
)
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology
from support import csrf_headers
from test_ai_extraction import ScriptedGateway
from test_ai_pipeline import FailingGateway
from test_ontology_support import add_elements, add_ontology, element, sign_in

MESSAGE = "新增对象类型钢包，钢包盛装炉次；炉次的同义词加上熔次；删除板坯"


def operation(
    op: str,
    kind: str,
    *,
    target: Element | None = None,
    temp_ref: str | None = None,
    confidence: float = 0.9,
    **fields: Any,
) -> AssistantOperationOut:
    given: dict[str, Any] = dict.fromkeys(AssistantFieldsOut.model_fields)
    given.update(fields)
    return AssistantOperationOut(
        op=op,  # type: ignore[arg-type]
        kind=kind,  # type: ignore[arg-type]
        target=str(target.id) if target else None,
        temp_ref=temp_ref,
        fields=AssistantFieldsOut(**given),
        rationale="用户明确要求。",
        confidence=confidence,
    )


async def steel(db: AsyncSession) -> tuple[Ontology, dict[str, Element]]:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    slab = element(ontology, "entity_type", "Slab", "板坯")
    weight = element(ontology, "property", "weight", "重量", domain_id=heat.id, datatype="decimal")
    cast_in = element(
        ontology, "relation_type", "castIn", "浇铸", domain_id=heat.id, range_id=slab.id
    )
    await add_elements(db, heat, slab, weight, cast_in)
    return ontology, {"Heat": heat, "Slab": slab, "weight": weight, "castIn": cast_in}


async def ask(client: AsyncClient, ontology: Ontology, message: str = MESSAGE) -> dict[str, Any]:
    response = await client.post(
        f"/api/ontologies/{ontology.id}/assistant/requests",
        json={"message": message, "context": {"page": "ontology"}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


async def answer(app: FastAPI, request_id: str, gateway: Any, attempts: int = 1) -> None:
    handler = make_assistant(app.state.session_factory, gateway, "test-model")
    await handler(
        JobContext(
            id=uuid4(),
            payload={"requestId": request_id},
            session_factory=app.state.session_factory,
            attempts=attempts,
        )
    )


async def stored(app: FastAPI, request_id: str) -> AssistantRequest:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as db:
        row = await db.get(AssistantRequest, UUID(request_id))
        assert row is not None
        return row


async def test_a_request_is_queued_for_the_assistant_job(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)

    body = await ask(client, ontology)

    assert (body["status"], body["step"], body["changeSetId"]) == ("queued", None, None)
    assert body["context"] == {"page": "ontology", "elementId": None}
    job = await db.scalar(select(Job).where(Job.kind == JOB_KIND))
    assert job is not None
    assert job.payload == {"requestId": body["id"]}


async def test_viewers_cannot_ask_and_messages_have_limits(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology, _ = await steel(db)
    await sign_in(client, db, Role.VIEWER)
    url = f"/api/ontologies/{ontology.id}/assistant/requests"
    refused = await client.post(
        url,
        json={"message": "加一个类型", "context": {"page": "ontology"}},
        headers=csrf_headers(client),
    )
    assert refused.status_code == 403
    await sign_in(client, db, Role.EDITOR)
    for message in ("  ", "字" * 2001):
        response = await client.post(
            url,
            json={"message": message, "context": {"page": "ontology"}},
            headers=csrf_headers(client),
        )
        assert response.status_code == 422
    missing = await client.post(
        f"/api/ontologies/{uuid4()}/assistant/requests",
        json={"message": "加一个类型", "context": {"page": "ontology"}},
        headers=csrf_headers(client),
    )
    assert missing.status_code == 404


async def test_checked_operations_become_a_change_set_for_review(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)
    request = await ask(client, ontology)
    gateway = ScriptedGateway(
        {
            "assistant": [
                AssistantOut(
                    reply="已按要求整理成变更。",
                    operations=[
                        operation(
                            "create",
                            "entity_type",
                            temp_ref="new:Ladle",
                            label_zh="钢包",
                            label_en="Ladle",
                            local_name="Ladle",
                        ),
                        operation(
                            "create",
                            "relation_type",
                            temp_ref="new:holds",
                            label_zh="盛装",
                            local_name="holds",
                            domain="new:Ladle",
                            range=str(rows["Heat"].id),
                            required=False,
                            multiple=True,
                        ),
                        operation(
                            "update", "entity_type", target=rows["Heat"], synonyms_zh=["熔次"]
                        ),
                        operation("delete", "entity_type", target=rows["Slab"]),
                        # Fails the naming rules, and takes the property built on it along.
                        operation(
                            "create",
                            "entity_type",
                            temp_ref="new:bad",
                            label_zh="坏",
                            local_name="bad name",
                        ),
                        operation(
                            "create",
                            "property",
                            label_zh="长度",
                            local_name="length",
                            domain="new:bad",
                            datatype="decimal",
                            required=False,
                            multiple=False,
                        ),
                    ],
                )
            ]
        }
    )

    await answer(app, request["id"], gateway)

    row = await stored(app, request["id"])
    assert (row.status, row.step, row.reply, row.dropped) == (
        "succeeded",
        "changeset",
        "已按要求整理成变更。",
        2,
    )
    assert row.change_set_id is not None
    assert row.finished_at is not None
    change_set = await db.get(ChangeSet, row.change_set_id)
    assert change_set is not None
    editor = await db.scalar(select(User.id).where(User.username == "editor-user"))
    assert (change_set.source, change_set.status, change_set.created_by) == (
        "ai_assistant",
        "open",
        editor,
    )
    assert change_set.title == "助手：" + MESSAGE
    long_title = ontology_assistant._title("字" * 70)
    assert long_title == "助手：" + "字" * 60 + "…"
    detail = (await client.get(f"/api/change-sets/{change_set.id}")).json()
    items = {(item["op"], item["kind"], item["targetElementId"]): item for item in detail["items"]}
    assert set(items) == {
        ("create", "entity_type", None),
        ("create", "relation_type", None),
        ("update", "entity_type", str(rows["Heat"].id)),
        ("delete", "entity_type", str(rows["Slab"].id)),
        # The cascade: castIn ends on Slab.
        ("delete", "relation_type", str(rows["castIn"].id)),
    }
    assert all(item["decision"] == "pending" for item in detail["items"])
    assert items[("create", "entity_type", None)]["confidence"] == 0.9
    assert items[("update", "entity_type", str(rows["Heat"].id))]["proposed"] == {
        "synonyms": [{"lang": "zh", "text": "熔次"}]
    }
    assert gateway.calls == [("assistant", "test-model")]


async def test_a_reply_alone_makes_no_change_set(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)
    request = await ask(client, ontology, "炉次有多少条记录？")
    gateway = ScriptedGateway(
        {"assistant": [AssistantOut(reply="这类问题将在后续版本支持。", operations=[])]}
    )

    await answer(app, request["id"], gateway)

    row = await stored(app, request["id"])
    assert (row.status, row.change_set_id, row.dropped) == ("succeeded", None, 0)
    assert row.reply == "这类问题将在后续版本支持。"
    assert await db.scalar(select(ChangeSet.id).where(ChangeSet.ontology_id == ontology.id)) is None


async def test_only_the_first_passing_operation_on_an_element_counts(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)
    request = await ask(client, ontology, "改一改")
    gateway = ScriptedGateway(
        {
            "assistant": [
                AssistantOut(
                    reply="好的。",
                    operations=[
                        # Not an element; a field the kind does not have; a second change to Heat.
                        operation("delete", "entity_type", target=None),
                        operation("update", "entity_type", target=rows["Heat"], datatype="decimal"),
                        operation("update", "entity_type", target=rows["Heat"], label_en="Heat"),
                        operation("update", "entity_type", target=rows["Heat"], label_en="Melt"),
                    ],
                )
            ]
        }
    )

    await answer(app, request["id"], gateway)

    row = await stored(app, request["id"])
    assert row.status == "succeeded"
    # The first update to Heat passes; the second one to the same element is dropped.
    assert row.dropped == 3
    assert row.change_set_id is not None


async def element_rows(db: AsyncSession, ontology: Ontology) -> set[tuple[Any, ...]]:
    rows = await db.execute(
        select(Element.id, Element.status, Element.revision).where(
            Element.ontology_id == ontology.id
        )
    )
    return {tuple(row) for row in rows}


async def proposed_items(client: AsyncClient, change_set_id: UUID | None) -> list[dict[str, Any]]:
    assert change_set_id is not None
    detail = (await client.get(f"/api/change-sets/{change_set_id}")).json()
    items: list[dict[str, Any]] = detail["items"]
    return items


async def run(
    app: FastAPI, client: AsyncClient, ontology: Ontology, operations: list[AssistantOperationOut]
) -> AssistantRequest:
    request = await ask(client, ontology, "改一改")
    gateway = ScriptedGateway({"assistant": [AssistantOut(reply="好的。", operations=operations)]})
    await answer(app, request["id"], gateway)
    row = await stored(app, request["id"])
    assert row.status == "succeeded", row.error_code
    return row


async def test_operations_that_all_fail_make_no_change_set_and_touch_nothing(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)
    before = await element_rows(db, ontology)

    row = await run(
        app,
        client,
        ontology,
        [
            operation("delete", "entity_type", target=None),
            operation("update", "entity_type", target=rows["Heat"], datatype="decimal"),
            # Fails the field limits before any check: counted all the same.
            operation("update", "entity_type", target=rows["Heat"], label_zh="长" * 201),
            # Changes nothing.
            operation("update", "entity_type", target=rows["Slab"]),
        ],
    )

    assert (row.dropped, row.change_set_id) == (4, None)
    assert await element_rows(db, ontology) == before


async def test_constraints_can_only_be_deleted(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)
    shape = element(
        ontology, "constraint", "HeatShape", "炉次约束", domain_id=rows["Heat"].id, rules=[]
    )
    other = element(
        ontology, "constraint", "SlabShape", "板坯约束", domain_id=rows["Slab"].id, rules=[]
    )
    await add_elements(db, shape, other)

    row = await run(
        app,
        client,
        ontology,
        [
            operation("update", "constraint", target=shape, label_zh="新名字"),
            operation("update", "constraint", target=other, domain=str(rows["Heat"].id)),
            operation("delete", "constraint", target=other),
        ],
    )

    items = await proposed_items(client, row.change_set_id)
    assert [(item["op"], item["targetElementId"]) for item in items] == [("delete", str(other.id))]
    assert row.dropped == 2


async def test_temp_refs_are_claimed_once_and_never_look_like_ids(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)

    row = await run(
        app,
        client,
        ontology,
        [
            operation(
                "create", "entity_type", temp_ref=" new:Ladle ", label_zh="钢包", local_name="Ladle"
            ),
            # The same temp_ref again, a temp_ref that is an element id.
            operation(
                "create",
                "entity_type",
                temp_ref="new:Ladle",
                label_zh="钢包二",
                local_name="Ladle2",
            ),
            operation(
                "create", "entity_type", temp_ref=str(uuid4()), label_zh="罐", local_name="Tank"
            ),
            operation(
                "create",
                "property",
                label_zh="容量",
                local_name="capacity",
                domain="new:Ladle",
                datatype="decimal",
                required=False,
                multiple=False,
            ),
            # "none" clears a reference.
            operation("update", "relation_type", target=rows["castIn"], inverse=" None "),
        ],
    )

    items = await proposed_items(client, row.change_set_id)
    assert [(item["op"], item["proposed"].get("localName")) for item in items] == [
        ("create", "Ladle"),
        ("create", "capacity"),
        ("update", None),
    ]
    assert items[0]["tempRef"] == "new:Ladle"
    assert items[1]["proposed"]["domainRef"] == "new:Ladle"
    assert items[2]["proposed"] == {"inverseRef": None}
    assert row.dropped == 2


async def test_what_conflicts_with_a_delete_goes_with_what_depends_on_it(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)

    row = await run(
        app,
        client,
        ontology,
        [
            operation("delete", "entity_type", target=rows["Slab"]),
            # A subtype of what goes away, and a property built on that subtype.
            operation(
                "create",
                "entity_type",
                temp_ref="new:Thick",
                label_zh="厚板坯",
                local_name="ThickSlab",
                parent=str(rows["Slab"].id),
            ),
            operation(
                "create",
                "property",
                label_zh="厚度",
                local_name="thickness",
                domain="new:Thick",
                datatype="decimal",
                required=False,
                multiple=False,
            ),
        ],
    )

    items = await proposed_items(client, row.change_set_id)
    assert [(item["op"], item["targetElementId"]) for item in items] == [
        ("delete", str(rows["Slab"].id)),
        ("delete", str(rows["castIn"].id)),
    ]
    assert row.dropped == 2


async def test_an_axiom_that_mentions_a_deleted_element_is_dropped(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, rows = await steel(db)
    heat, slab = (f"<{ontology.base_iri}{name}>" for name in ("Heat", "Slab"))
    disjoint = "<http://www.w3.org/2002/07/owl#disjointWith>"

    row = await run(
        app,
        client,
        ontology,
        [
            operation("delete", "entity_type", target=rows["Slab"]),
            operation("create", "axiom", turtle=f"{heat} {disjoint} {slab} ."),
        ],
    )

    items = await proposed_items(client, row.change_set_id)
    assert [(item["op"], item["kind"], item["targetElementId"]) for item in items] == [
        ("delete", "entity_type", str(rows["Slab"].id)),
        ("delete", "relation_type", str(rows["castIn"].id)),
    ]
    assert row.dropped == 1


async def test_axioms_are_checked_normalized_and_taken_once(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)
    heat, slab = (f"<{ontology.base_iri}{name}>" for name in ("Heat", "Slab"))
    disjoint = "<http://www.w3.org/2002/07/owl#disjointWith>"

    row = await run(
        app,
        client,
        ontology,
        [
            operation("create", "axiom", turtle=f"{heat}   {disjoint}   {slab} ."),
            # The same axiom written another way; one that does not parse.
            operation("create", "axiom", turtle=f"{heat} {disjoint} {slab} ."),
            operation("create", "axiom", turtle=f"{heat} {disjoint} ."),
        ],
    )

    items = await proposed_items(client, row.change_set_id)
    assert len(items) == 1
    turtle = items[0]["proposed"]["turtle"]
    assert "   " not in turtle
    assert "disjointWith" in turtle
    assert row.dropped == 2


async def test_operations_past_the_cap_are_dropped(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)
    operations = [
        operation("create", "entity_type", label_zh=f"类型{n}", local_name=f"Type{n}")
        for n in range(OPERATIONS_MAX + 2)
    ]

    row = await run(app, client, ontology, operations)

    assert len(await proposed_items(client, row.change_set_id)) == OPERATIONS_MAX
    assert row.dropped == 2


async def test_model_failures_are_reported_and_transient_ones_retried(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)

    first = await ask(client, ontology)
    with pytest.raises(AppError) as raised:
        await answer(app, first["id"], FailingGateway(AiNotConfiguredError()))
    assert raised.value.code == "ai.not_configured"
    row = await stored(app, first["id"])
    assert (row.status, row.error_code, row.change_set_id) == ("failed", "ai.not_configured", None)
    assert row.finished_at is not None

    second = await ask(client, ontology)
    transient = FailingGateway(AiUnavailableError("timeout", retryable=True))
    with pytest.raises(RetryableJobError):
        await answer(app, second["id"], transient, attempts=1)
    assert (await stored(app, second["id"])).status == "queued"
    with pytest.raises(AppError):
        await answer(app, second["id"], transient, attempts=3)
    row = await stored(app, second["id"])
    assert (row.status, row.error_code) == ("failed", "ai.unavailable")

    # A replayed job leaves a finished request alone.
    await answer(app, second["id"], ScriptedGateway({}))
    assert (await stored(app, second["id"])).status == "failed"

    # Claimed again after the last attempt died without reporting: no more model calls.
    third = await ask(client, ontology)
    idle = ScriptedGateway({})
    with pytest.raises(AppError) as raised:
        await answer(app, third["id"], idle, attempts=4)
    assert raised.value.code == "internal.error"
    row = await stored(app, third["id"])
    assert (row.status, row.error_code) == ("failed", "internal.error")
    assert row.finished_at is not None
    assert idle.calls == []


async def test_users_see_only_their_own_requests(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology, _ = await steel(db)
    older = await ask(client, ontology, "第一个请求")
    newer = await ask(client, ontology, "第二个请求")

    listed = await client.get(f"/api/ontologies/{ontology.id}/assistant/requests")
    assert [item["id"] for item in listed.json()] == [newer["id"], older["id"]]
    limited = await client.get(
        f"/api/ontologies/{ontology.id}/assistant/requests", params={"limit": 1}
    )
    assert [item["id"] for item in limited.json()] == [newer["id"]]
    assert (await client.get(f"/api/assistant/requests/{older['id']}")).status_code == 200

    await sign_in(client, db, Role.REVIEWER)
    other = await client.get(f"/api/assistant/requests/{older['id']}")
    assert other.status_code == 404
    assert other.json()["code"] == "assistant.not_found"
    assert (await client.get(f"/api/ontologies/{ontology.id}/assistant/requests")).json() == []


async def test_the_model_sees_a_summary_and_the_selected_element(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    ontology, rows = await steel(db)

    text = await ontology_assistant.context_for(
        db, ontology.id, message="给炉次加同义词", page="ontology", element_id=rows["Heat"].id
    )

    assert f"{rows['castIn'].id} | relation_type | 浇铸 / - / castIn" in text
    assert f"domain={rows['Heat'].id} range={rows['Slab'].id}" in text
    assert "Selected element: " in text
    assert '"localName": "Heat"' in text
    assert "The user is on the ontology page." in text

    # Large ontologies: only what the message names and its direct neighbours.
    monkeypatch.setattr(ontology_assistant, "CONTEXT_ELEMENTS_MAX", 2)
    cut = await ontology_assistant.context_for(
        db, ontology.id, message="板坯", page="ontology", element_id=None
    )
    assert "Only the 2 of 4 elements" in cut
    assert f"{rows['Slab'].id} |" in cut
    assert f"{rows['castIn'].id} |" in cut
    assert f"{rows['weight'].id} |" not in cut
    # Naming nothing still says why the list is empty.
    nothing = await ontology_assistant.context_for(
        db, ontology.id, message="加一个类型", page="ontology", element_id=None
    )
    assert "Only the 0 of 4 elements" in nothing
    assert "(none)" in nothing
