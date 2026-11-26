"""The MCP `propose_changes` tool (spec 003, 9.4; section 15, "AI 不直接改本体" ② and "令牌"
⑤⑦): it only ever makes a change set waiting for review."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Element, Ontology
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem
from support import csrf_headers, make_client
from test_mcp_support import READ_TOOLS, call_tool, new_token, rpc, tool_error
from test_ontology_support import add_elements, add_ontology, element

PROPOSE = ["ontology:read", "changes:propose"]


@dataclass
class Setup:
    ontology: Ontology
    coil: Element
    weight: Element
    token: str
    token_id: str
    owner_id: UUID


@pytest.fixture
async def setup(client: AsyncClient, db: AsyncSession) -> Setup:
    ontology = await add_ontology(db)
    coil = element(ontology, "entity_type", "Coil", "钢卷")
    weight = element(ontology, "property", "weight", "重量", domain_id=coil.id, datatype="decimal")
    await add_elements(db, coil, weight)
    token, token_id = await new_token(client, db, Role.EDITOR, PROPOSE)
    owner_id = await db.scalar(select(User.id).where(User.username == "editor-user"))
    assert owner_id is not None
    return Setup(ontology, coil, weight, token, token_id, owner_id)


def _create(local_name: str, label: str, **fields: Any) -> dict[str, Any]:
    return {
        "op": "create",
        "kind": "entity_type",
        "tempRef": f"new:{local_name}",
        "fields": {"localName": local_name, "labelZh": label, **fields},
        "rationale": f"资料里多次提到{label}",
    }


async def _propose(app: FastAPI, token: str, arguments: dict[str, Any]) -> dict[str, Any]:
    async with make_client(app) as agent:
        return await call_tool(agent, token, "propose_changes", arguments)


def _content(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result
    content: dict[str, Any] = result["structuredContent"]
    return content


async def _change_sets(db: AsyncSession) -> list[ChangeSet]:
    rows = await db.scalars(
        select(ChangeSet).order_by(ChangeSet.created_at).execution_options(populate_existing=True)
    )
    return list(rows)


async def _working(db: AsyncSession, ontology: Ontology) -> list[tuple[Any, ...]]:
    rows = await db.execute(
        select(Element.id, Element.label_zh, Element.status, Element.revision)
        .where(Element.ontology_id == ontology.id)
        .order_by(Element.id)
        .execution_options(populate_existing=True)
    )
    return [tuple(row) for row in rows]


# ---------- what it makes ----------


async def test_a_proposal_becomes_a_change_set_waiting_for_review(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    before = await _working(db, setup.ontology)

    result = await _propose(
        app,
        setup.token,
        {
            "ontology": setup.ontology.key,
            "title": "补充钢包与盛放关系",
            "operations": [
                _create("Ladle", "钢包"),
                {
                    "op": "create",
                    "kind": "relation_type",
                    "tempRef": "new:holds",
                    "fields": {
                        "localName": "holds",
                        "labelZh": "盛放",
                        "domain": "new:Ladle",
                        "range": str(setup.coil.id),
                    },
                    "rationale": "钢包盛放钢水",
                },
                {
                    "op": "update",
                    "kind": "entity_type",
                    "target": str(setup.coil.id),
                    "fields": {"labelEn": "Coil", "synonymsZh": ["卷"]},
                    "rationale": "补英文名",
                },
                # Not an element of the ontology: dropped.
                {
                    "op": "update",
                    "kind": "property",
                    "target": str(setup.coil.id),
                    "fields": {"unit": "t"},
                    "rationale": "单位",
                },
            ],
        },
    )

    content = _content(result)
    assert (content["proposed"], content["dropped"]) == (3, 1)
    assert "1" in content["notice"]
    [change_set] = await _change_sets(db)
    assert content["changeSetId"] == str(change_set.id)
    assert change_set.source == "mcp"
    assert change_set.title == "MCP：补充钢包与盛放关系"
    assert change_set.status == "open"
    assert change_set.created_by == setup.owner_id
    assert change_set.token_id == UUID(setup.token_id)
    items = list(
        await db.scalars(
            select(ChangeItem)
            .where(ChangeItem.change_set_id == change_set.id)
            .order_by(ChangeItem.seq)
        )
    )
    assert [(i.op, i.kind, i.decision) for i in items] == [
        ("create", "entity_type", "pending"),
        ("create", "relation_type", "pending"),
        ("update", "entity_type", "pending"),
    ]
    assert [i.rationale for i in items] == ["资料里多次提到钢包", "钢包盛放钢水", "补英文名"]
    assert items[1].proposed["domainRef"] == "new:Ladle"
    assert items[1].proposed["rangeRef"] == str(setup.coil.id)
    assert items[2].proposed == {
        "labelEn": "Coil",
        "synonyms": [{"lang": "zh", "text": "卷"}],
    }
    assert items[2].target_revision == setup.coil.revision
    # The working version is untouched: only review and merge change it.
    assert await _working(db, setup.ontology) == before


async def test_an_explicit_null_clears_and_an_omitted_field_stays(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    result = await _propose(
        app,
        setup.token,
        {
            "ontology": str(setup.ontology.id),
            "title": "去掉单位",
            "operations": [
                {
                    "op": "update",
                    "kind": "property",
                    "target": str(setup.weight.id),
                    "fields": {"unit": None, "definitionZh": "钢卷的净重"},
                    "rationale": "单位写在定义里",
                }
            ],
        },
    )

    assert _content(result)["proposed"] == 1
    [change_set] = await _change_sets(db)
    [item] = await db.scalars(select(ChangeItem).where(ChangeItem.change_set_id == change_set.id))
    assert item.proposed == {"unit": None, "definitionZh": "钢卷的净重"}


async def test_a_long_title_is_cut_to_sixty_characters(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    title = "钢" * 70

    _content(
        await _propose(
            app,
            setup.token,
            {
                "ontology": setup.ontology.key,
                "title": f"  {title[:30]}\n {title[30:]} ",
                "operations": [_create("Ladle", "钢包")],
            },
        )
    )

    [change_set] = await _change_sets(db)
    assert change_set.title == "MCP：" + "钢" * 30 + " " + "钢" * 29 + "…"


async def test_a_delete_takes_its_cascade_along(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    content = _content(
        await _propose(
            app,
            setup.token,
            {
                "ontology": setup.ontology.key,
                "title": "删除钢卷",
                "operations": [
                    {
                        "op": "delete",
                        "kind": "entity_type",
                        "target": str(setup.coil.id),
                        "rationale": "合并到板卷",
                    }
                ],
            },
        )
    )

    assert (content["proposed"], content["dropped"]) == (1, 0)
    assert "notice" not in content
    [change_set] = await _change_sets(db)
    items = await db.scalars(select(ChangeItem).where(ChangeItem.change_set_id == change_set.id))
    assert {(i.op, i.target_element_id) for i in items} == {
        ("delete", setup.coil.id),
        ("delete", setup.weight.id),
    }


async def test_nothing_valid_makes_no_change_set(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    content = _content(
        await _propose(
            app,
            setup.token,
            {
                "ontology": setup.ontology.key,
                "title": "重名",
                "operations": [_create("Coil", "钢卷"), _create("weight", "重量")],
            },
        )
    )

    assert content == {
        "changeSetId": None,
        "proposed": 0,
        "dropped": 2,
        "notice": content["notice"],
    }
    assert await _change_sets(db) == []


# ---------- what it cannot do ----------


@pytest.mark.parametrize(
    "operation",
    [
        # Bindings come from a catalog through ontology.binding_proposals, never from here.
        {
            "op": "create",
            "kind": "type_binding",
            "tempRef": "new:b",
            "fields": {"subjectRef": "x"},
            "rationale": "r",
        },
        {"op": "create", "kind": "property_binding", "fields": {}, "rationale": "r"},
        {"op": "create", "kind": "relation_binding", "fields": {}, "rationale": "r"},
        {
            "op": "create",
            "kind": "entity_type",
            "tempRef": "new:Ladle",
            "fields": {"localName": "Ladle", "labelZh": "钢包", "binding": {"table": "t"}},
            "rationale": "r",
        },
        {
            "op": "create",
            "kind": "entity_type",
            "tempRef": "new:Ladle",
            "fields": {"localName": "Ladle", "labelZh": "钢包", "subjectRef": "x"},
            "rationale": "r",
        },
        # Constraints are edited in their form; imports alone bring an explicit IRI.
        {"op": "delete", "kind": "constraint", "target": "x", "rationale": "r"},
        {
            "op": "create",
            "kind": "entity_type",
            "fields": {"localName": "Ladle", "labelZh": "钢包", "iri": "urn:x:Ladle"},
            "rationale": "r",
        },
        # Restoring is not one of the operations; a reason is required.
        {"op": "restore", "kind": "entity_type", "target": "x", "rationale": "r"},
        {"op": "create", "kind": "entity_type", "fields": {"localName": "Ladle"}},
    ],
)
async def test_bindings_and_other_operations_are_refused(
    app: FastAPI, db: AsyncSession, setup: Setup, operation: dict[str, Any]
) -> None:
    before = await _working(db, setup.ontology)

    result = await _propose(
        app,
        setup.token,
        {"ontology": setup.ontology.key, "title": "绑定", "operations": [operation]},
    )

    tool_error(result, "validation.failed")
    assert await _change_sets(db) == []
    assert await _working(db, setup.ontology) == before


@pytest.mark.parametrize("count", [0, 51])
async def test_one_to_fifty_operations(
    app: FastAPI, db: AsyncSession, setup: Setup, count: int
) -> None:
    operations = [_create(f"T{n}", f"类型{n}") for n in range(count)]

    result = await _propose(
        app,
        setup.token,
        {"ontology": setup.ontology.key, "title": "批量", "operations": operations},
    )

    tool_error(result, "validation.failed")
    assert await _change_sets(db) == []


async def test_it_is_the_only_tool_that_writes_and_it_cannot_review(
    app: FastAPI, setup: Setup
) -> None:
    async with make_client(app) as agent:
        response = await rpc(agent, setup.token, "tools/list")
    tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}

    assert list(tools) == [*READ_TOOLS, "propose_changes"]
    annotations = tools["propose_changes"]["annotations"]
    assert annotations["readOnlyHint"] is False
    assert annotations["destructiveHint"] is False
    assert annotations["openWorldHint"] is False
    schema = tools["propose_changes"]["inputSchema"]
    assert set(schema["properties"]) == {"ontology", "title", "operations"}
    assert all(tools[name]["annotations"]["readOnlyHint"] is True for name in READ_TOOLS)


async def test_the_owner_cannot_review_it_in_separate_mode(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.settings.review_mode = "separate"
    ontology = await add_ontology(db)
    token, _ = await new_token(client, db, Role.REVIEWER, PROPOSE)
    content = _content(
        await _propose(
            app,
            token,
            {"ontology": ontology.key, "title": "钢包", "operations": [_create("Ladle", "钢包")]},
        )
    )
    change_set_id = content["changeSetId"]
    detail = (await client.get(f"/api/change-sets/{change_set_id}")).json()
    item_id = detail["items"][0]["id"]
    headers = csrf_headers(client)

    for response in (
        await client.patch(
            f"/api/change-sets/{change_set_id}/items/{item_id}",
            json={"decision": "accepted"},
            headers=headers,
        ),
        await client.post(f"/api/change-sets/{change_set_id}/merge", headers=headers),
    ):
        assert response.status_code == 403
        assert response.json()["code"] == "changeset.self_review"


# ---------- who may ----------


async def test_it_needs_the_scope(app: FastAPI, client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    token, _ = await new_token(client, db, Role.EDITOR, ["ontology:read", "objects:read"])

    result = await _propose(
        app,
        token,
        {"ontology": ontology.key, "title": "钢包", "operations": [_create("Ladle", "钢包")]},
    )

    tool_error(result, "auth.insufficient_scope")
    assert await _change_sets(db) == []


async def test_an_owner_made_viewer_is_refused_at_once(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    arguments = {
        "ontology": setup.ontology.key,
        "title": "钢包",
        "operations": [_create("Ladle", "钢包")],
    }
    _content(await _propose(app, setup.token, arguments))
    await db.execute(update(User).where(User.id == setup.owner_id).values(role=Role.VIEWER.value))
    await db.commit()

    arguments["operations"] = [_create("Tundish", "中间包")]
    result = await _propose(app, setup.token, arguments)

    tool_error(result, "auth.insufficient_scope")
    assert len(await _change_sets(db)) == 1


async def test_an_unknown_ontology_is_a_tool_error(app: FastAPI, setup: Setup) -> None:
    result = await _propose(
        app,
        setup.token,
        {"ontology": "no-such", "title": "钢包", "operations": [_create("Ladle", "钢包")]},
    )

    tool_error(result, "ontology.not_found")


# ---------- how often ----------


async def test_ten_change_sets_per_token_and_hour(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    def arguments(n: int) -> dict[str, Any]:
        return {
            "ontology": setup.ontology.key,
            "title": f"第{n}个",
            "operations": [_create(f"T{n}", f"类型{n}")],
        }

    for n in range(10):
        assert _content(await _propose(app, setup.token, arguments(n)))["changeSetId"]

    tool_error(await _propose(app, setup.token, arguments(10)), "mcp.rate_limited")
    assert len(await _change_sets(db)) == 10

    # An hour later the window has room again.
    await db.execute(
        update(ChangeSet).values(created_at=datetime.now(UTC) - timedelta(hours=1, minutes=1))
    )
    await db.commit()
    assert _content(await _propose(app, setup.token, arguments(10)))["changeSetId"]


async def test_twenty_open_mcp_change_sets_per_user(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    for n in range(20):
        await service.create_change_set(
            db,
            ontology_id=setup.ontology.id,
            title=f"MCP：旧的{n}",
            source="mcp",
            document_id=None,
            created_by=setup.owner_id,
            items=[
                ProposedItem(
                    op="create",
                    kind="entity_type",
                    temp_ref=f"new:Old{n}",
                    proposed=ElementFields(local_name=f"Old{n}", label_zh=f"旧{n}"),
                )
            ],
        )
    await db.commit()
    arguments = {
        "ontology": setup.ontology.key,
        "title": "钢包",
        "operations": [_create("Ladle", "钢包")],
    }

    tool_error(await _propose(app, setup.token, arguments), "mcp.rate_limited")
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 20

    # Once one is decided, there is room again.
    first = (await _change_sets(db))[0]
    await db.execute(update(ChangeSet).where(ChangeSet.id == first.id).values(status="rejected"))
    await db.commit()
    assert _content(await _propose(app, setup.token, arguments))["changeSetId"]


# ---------- audit ----------


async def test_the_audit_names_the_token_but_not_the_arguments(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    content = _content(
        await _propose(
            app,
            setup.token,
            {
                "ontology": setup.ontology.key,
                "title": "审计用的标题",
                "operations": [_create("Ladle", "钢包", definitionZh="盛放钢水的容器")],
            },
        )
    )

    events = list(await db.scalars(select(AuditEvent).order_by(AuditEvent.id)))
    [called] = [e for e in events if e.action == "mcp.tool_called"]
    assert called.actor_id == setup.owner_id
    assert called.detail == {
        "tool": "propose_changes",
        "tokenId": setup.token_id,
        "ontology": str(setup.ontology.id),
        "code": "ok",
    }
    [created] = [e for e in events if e.action == "changeset.created"]
    assert created.actor_id == setup.owner_id
    assert created.target_id == content["changeSetId"]
    assert created.detail["tokenId"] == setup.token_id
    logged = json.dumps([e.detail for e in events], ensure_ascii=False)
    for argument in ("审计用的标题", "盛放钢水的容器", "资料里多次提到钢包", "Ladle"):
        assert argument not in logged


async def test_a_refused_call_is_audited_with_its_code(
    app: FastAPI, db: AsyncSession, setup: Setup
) -> None:
    await _propose(
        app,
        setup.token,
        {
            "ontology": setup.ontology.key,
            "title": "绑定",
            "operations": [
                {"op": "create", "kind": "type_binding", "fields": {}, "rationale": "r"}
            ],
        },
    )

    [called] = await db.scalars(select(AuditEvent).where(AuditEvent.action == "mcp.tool_called"))
    assert called.detail["code"] == "validation.failed"
