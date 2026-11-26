"""The read-only MCP tools (spec 003, 9.3; section 15, "MCP", "令牌" ⑤ and the audit of
`mcp.tool_called`)."""

import base64
import dataclasses
import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.mcp import tools
from ontology_platform.modules.ontology.models import Element
from support import csrf_headers, make_client
from test_mcp_support import call_tool, new_token, rpc, tool_error
from test_ontology_support import add_elements, add_ontology, element
from test_query_support import QueryCatalog, make_catalog, publish_bindings

# Table and column names of the bindings; ontology tools must never show them.
SOURCE_NAMES = ['"mes"', "coil_no", "quality_inspection", "inspection_id", '"status"']


@dataclass
class Published:
    catalog: QueryCatalog
    special: Element
    token: str
    token_id: str


@pytest.fixture
async def published(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> Published:
    catalog = await make_catalog(client, db, external_source)
    catalog.coil.definition_zh = "热轧后卷取成卷的钢带"
    catalog.coil.synonyms = [{"lang": "en", "text": "Steel coil"}]
    special = element(
        catalog.ontology, "entity_type", "SpecialCoil", "特殊钢卷", parent_id=catalog.coil.id
    )
    await add_elements(db, special)
    await publish_bindings(client, catalog)
    token, token_id = await new_token(client, db, Role.ADMIN, ["ontology:read", "objects:read"])
    return Published(catalog, special, token, token_id)


def _structured(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result
    content: dict[str, Any] = result["structuredContent"]
    return content


async def _tool(app: FastAPI, token: str, name: str, **arguments: Any) -> dict[str, Any]:
    async with make_client(app) as agent:
        return await call_tool(agent, token, name, arguments)


# ---------- ontology tools ----------


async def test_list_ontologies_shows_the_released_ones(
    app: FastAPI, db: AsyncSession, published: Published
) -> None:
    await add_ontology(db, key="draft", name="草稿")

    content = _structured(await _tool(app, published.token, "list_ontologies"))

    [item] = content["ontologies"]
    ontology = published.catalog.ontology
    assert item["id"] == str(ontology.id)
    assert item["key"] == ontology.key
    assert item["name"] == ontology.name
    assert item["version"] == 1
    assert item["releaseId"]
    assert item["publishedAt"]


@pytest.mark.parametrize("by", ["id", "key"])
async def test_search_elements_finds_names_synonyms_and_definitions(
    app: FastAPI, published: Published, by: str
) -> None:
    ontology = published.catalog.ontology
    reference = str(ontology.id) if by == "id" else ontology.key

    for query in ("钢卷", "steel COIL", "卷取", "Coil"):
        content = _structured(
            await _tool(app, published.token, "search_elements", ontology=reference, query=query)
        )
        assert content["release"]["version"] == 1
        assert str(published.catalog.coil.id) in [item["id"] for item in content["items"]], query

    typed = _structured(
        await _tool(
            app,
            published.token,
            "search_elements",
            ontology=reference,
            query="钢卷",
            kinds=["relation_type"],
        )
    )
    assert {item["kind"] for item in typed["items"]} == {"relation_type"}
    [brief] = [i for i in typed["items"] if i["id"] == str(published.catalog.inspected_coil.id)]
    assert (brief["domain"], brief["range"]) == ("质检", "钢卷")
    assert brief["labelZh"] == "受检钢卷"
    assert brief["iri"].endswith("#inspectedCoil")


async def test_search_elements_pages_with_a_cursor(app: FastAPI, published: Published) -> None:
    ontology = str(published.catalog.ontology.id)
    seen: list[str] = []
    cursor = None
    for _ in range(10):
        arguments: dict[str, Any] = {"ontology": ontology, "limit": 2}
        if cursor is not None:
            arguments["cursor"] = cursor
        content = _structured(await _tool(app, published.token, "search_elements", **arguments))
        assert len(content["items"]) <= 2
        seen.extend(item["id"] for item in content["items"])
        cursor = content["nextCursor"]
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 6


async def test_get_element_describes_an_object_type(app: FastAPI, published: Published) -> None:
    catalog = published.catalog
    ontology = catalog.ontology.key

    coil = _structured(
        await _tool(app, published.token, "get_element", ontology=ontology, id="Coil")
    )
    assert coil["id"] == str(catalog.coil.id)
    assert coil["release"]["version"] == 1
    assert coil["definitionZh"] == "热轧后卷取成卷的钢带"
    assert coil["synonyms"] == [{"lang": "en", "text": "Steel coil"}]
    assert [p["id"] for p in coil["properties"]] == [str(catalog.status.id)]
    assert [r["id"] for r in coil["relationsOut"]] == [str(catalog.inspections.id)]
    assert [r["id"] for r in coil["relationsIn"]] == [str(catalog.inspected_coil.id)]
    assert coil["children"] == [{"id": str(published.special.id), "label": "特殊钢卷"}]
    assert coil["hasData"] is True

    special = _structured(
        await _tool(
            app,
            published.token,
            "get_element",
            ontology=ontology,
            iri=published.special.iri or f"{catalog.ontology.base_iri}SpecialCoil",
        )
    )
    assert special["parent"] == "钢卷"
    # Inherited from Coil.
    assert [p["id"] for p in special["properties"]] == [str(catalog.status.id)]
    assert special["hasData"] is False

    status = _structured(
        await _tool(
            app, published.token, "get_element", ontology=ontology, id=str(catalog.status.id)
        )
    )
    assert (status["kind"], status["domain"], status["datatype"]) == ("property", "钢卷", "string")
    assert "properties" not in status


async def test_ontology_tools_never_show_tables_or_columns(
    app: FastAPI, published: Published
) -> None:
    ontology = published.catalog.ontology.key
    results = [
        await _tool(app, published.token, "list_ontologies"),
        await _tool(app, published.token, "search_elements", ontology=ontology),
    ]
    for name in ("Coil", "Inspection", "coilStatus", "inspectedCoil", "inspections"):
        results.append(await _tool(app, published.token, "get_element", ontology=ontology, id=name))

    for result in results:
        text = json.dumps(_structured(result), ensure_ascii=False)
        for name in SOURCE_NAMES:
            assert name not in text, (name, text)


async def test_an_unknown_ontology_or_element_is_a_tool_error(
    app: FastAPI, db: AsyncSession, published: Published
) -> None:
    await add_ontology(db, key="draft", name="草稿")
    token = published.token

    tool_error(await _tool(app, token, "search_elements", ontology="nope"), "ontology.not_found")
    tool_error(await _tool(app, token, "search_elements", ontology="draft"), "query.no_release")
    tool_error(
        await _tool(app, token, "get_element", ontology="steel", id="Missing"),
        "element.not_found",
    )
    tool_error(await _tool(app, token, "get_element", ontology="steel"), "validation.failed")
    tool_error(
        await _tool(app, token, "search_elements", ontology="steel", limit=0), "validation.failed"
    )
    tool_error(
        await _tool(app, token, "search_elements", ontology="steel", extra=1), "validation.failed"
    )


# ---------- object tools: the same results as /api ----------


async def test_object_tools_answer_like_the_query_api(
    app: FastAPI, client: AsyncClient, published: Published
) -> None:
    catalog = published.catalog
    url = catalog.url
    api_page = await client.post(
        f"{url}/search",
        json={"typeId": str(catalog.coil.id), "limit": 2},
        headers=csrf_headers(client),
    )
    assert api_page.status_code == 200, api_page.text
    by_name = _structured(
        await _tool(app, published.token, "search_objects", ontology="steel", type="Coil", limit=2)
    )
    assert by_name == api_page.json()
    by_iri = _structured(
        await _tool(
            app,
            published.token,
            "search_objects",
            ontology=str(catalog.ontology.id),
            type=f"{catalog.ontology.base_iri}Coil",
            limit=2,
        )
    )
    assert by_iri == api_page.json()
    assert by_name["items"][0]["source"]["table"] == "coil"

    key = api_page.json()["items"][0]["key"]
    api_object = await client.get(f"{url}/{catalog.coil.id}/{key}")
    assert api_object.status_code == 200
    mcp_object = _structured(
        await _tool(app, published.token, "get_object", ontology="steel", type="Coil", key=key)
    )
    assert mcp_object == api_object.json()

    api_related = await client.get(
        f"{url}/{catalog.coil.id}/{key}/related",
        params={"relationId": str(catalog.inspected_coil.id), "direction": "in"},
    )
    assert api_related.status_code == 200, api_related.text
    mcp_related = _structured(
        await _tool(
            app,
            published.token,
            "get_related_objects",
            ontology="steel",
            type="Coil",
            key=key,
            relation="inspectedCoil",
            direction="in",
        )
    )
    assert mcp_related == api_related.json()


async def test_search_objects_filters_and_sorts_like_the_query_api(
    app: FastAPI, client: AsyncClient, published: Published
) -> None:
    catalog = published.catalog
    api_body = {
        "typeId": str(catalog.coil.id),
        "filters": [{"propertyId": str(catalog.status.id), "op": "notNull"}],
        "sort": [{"propertyId": str(catalog.status.id), "direction": "desc"}],
        "limit": 1,
    }
    api_page = await client.post(
        f"{catalog.url}/search", json=api_body, headers=csrf_headers(client)
    )
    assert api_page.status_code == 200, api_page.text

    content = _structured(
        await _tool(
            app,
            published.token,
            "search_objects",
            ontology="steel",
            type="Coil",
            filters=[{"propertyId": "coilStatus", "op": "notNull"}],
            sort=[{"propertyId": "coilStatus", "direction": "desc"}],
            limit=1,
        )
    )
    assert content == api_page.json()
    # One per page, so the second page is always compared.
    assert content["nextCursor"] is not None

    if content["nextCursor"] is not None:
        api_next = await client.post(
            f"{catalog.url}/search",
            json={**api_body, "cursor": content["nextCursor"]},
            headers=csrf_headers(client),
        )
        mcp_next = _structured(
            await _tool(
                app,
                published.token,
                "search_objects",
                ontology="steel",
                type="Coil",
                filters=[{"propertyId": "coilStatus", "op": "notNull"}],
                sort=[{"propertyId": "coilStatus", "direction": "desc"}],
                limit=1,
                cursor=content["nextCursor"],
            )
        )
        assert mcp_next == api_next.json()


async def test_object_tool_failures_carry_the_query_codes(
    app: FastAPI, published: Published
) -> None:
    token = published.token
    tool_error(
        await _tool(app, token, "search_objects", ontology="steel", type="SpecialCoil"),
        "query.type_not_bound",
    )
    tool_error(
        await _tool(
            app,
            token,
            "search_objects",
            ontology="steel",
            type="Coil",
            filters=[{"propertyId": "coilStatus", "op": "gt", "value": [1, 2]}],
        ),
        "query.invalid_filter",
    )
    tool_error(
        await _tool(
            app,
            token,
            "search_objects",
            ontology="steel",
            type="Coil",
            filters=[{"propertyId": "noSuchProperty", "op": "notNull"}],
        ),
        "query.invalid_filter",
    )
    tool_error(
        await _tool(app, token, "get_object", ontology="steel", type="Coil", key="!!"),
        "query.object_not_found",
    )


# ---------- scopes, size and audit ----------


async def test_a_tool_needs_its_scope(
    app: FastAPI, client: AsyncClient, db: AsyncSession, published: Published
) -> None:
    ontology_only, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    objects_only, _ = await new_token(client, db, Role.VIEWER, ["objects:read"])

    tool_error(
        await _tool(app, ontology_only, "search_objects", ontology="steel", type="Coil"),
        "auth.insufficient_scope",
    )
    tool_error(await _tool(app, objects_only, "list_ontologies"), "auth.insufficient_scope")
    _structured(await _tool(app, ontology_only, "list_ontologies"))
    _structured(await _tool(app, objects_only, "search_objects", ontology="steel", type="Coil"))


async def test_a_result_over_the_size_limit_is_cut_short(
    app: FastAPI, published: Published, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tools.RESULT_LIMIT_BYTES == 256 * 1024
    full = _structured(
        await _tool(app, published.token, "search_elements", ontology="steel", limit=100)
    )
    size = len(json.dumps(full, ensure_ascii=False).encode())
    monkeypatch.setattr(tools, "RESULT_LIMIT_BYTES", size - 1)

    cut = _structured(
        await _tool(app, published.token, "search_elements", ontology="steel", limit=100)
    )

    assert 0 < len(cut["items"]) < len(full["items"])
    assert cut["items"] == full["items"][: len(cut["items"])]
    assert cut["truncated"] is True
    assert cut["nextCursor"] is None
    assert "limit" in cut["notice"]
    assert len(json.dumps(cut, ensure_ascii=False).encode()) <= size - 1


async def test_every_tool_call_is_audited_without_secrets(
    app: FastAPI, db: AsyncSession, published: Published
) -> None:
    token = published.token
    await _tool(
        app,
        token,
        "search_objects",
        ontology="steel",
        type="Coil",
        filters=[{"propertyId": "coilStatus", "op": "notNull"}],
    )
    # The value is no label of the source enum, so this call fails: the failure path must
    # keep filter values out of the audit as well.
    await _tool(
        app,
        token,
        "search_objects",
        ontology="steel",
        type="Coil",
        filters=[{"propertyId": "coilStatus", "op": "eq", "value": "FILTER-VALUE-7731"}],
    )
    await _tool(app, token, "get_element", ontology="steel", id="Missing")

    events = list(
        await db.scalars(
            select(AuditEvent).where(AuditEvent.action == "mcp.tool_called").order_by(AuditEvent.id)
        )
    )
    assert [(e.detail["tool"], e.detail["code"]) for e in events] == [
        ("search_objects", "ok"),
        ("search_objects", "query.invalid_filter"),
        ("get_element", "element.not_found"),
    ]
    for event in events:
        assert event.detail["tokenId"] == published.token_id
        assert event.detail["ontology"] == str(published.catalog.ontology.id)
        assert event.actor_id is not None
        dumped = json.dumps(event.detail, ensure_ascii=False)
        assert token not in dumped
        assert token[:20] not in dumped
        assert "FILTER-VALUE-7731" not in dumped


async def test_search_elements_refuses_a_cursor_of_another_question(
    app: FastAPI, published: Published
) -> None:
    first = _structured(
        await _tool(app, published.token, "search_elements", ontology="steel", limit=2)
    )
    cursor = first["nextCursor"]
    assert cursor is not None
    release_id, question, _ = json.loads(base64.urlsafe_b64decode(cursor))
    forged = [
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        for payload in (
            [release_id, question, -2],
            [release_id, question, True],
            [release_id, question],
        )
    ]
    for bad in (*forged, "not a cursor"):
        result = await _tool(
            app, published.token, "search_elements", ontology="steel", limit=2, cursor=bad
        )
        tool_error(result, "query.invalid_cursor")

    other_question = await _tool(
        app, published.token, "search_elements", ontology="steel", query="钢卷", cursor=cursor
    )
    tool_error(other_question, "query.invalid_cursor")

    stale = base64.urlsafe_b64encode(json.dumps([str(uuid4()), question, 2]).encode()).decode()
    changed = await _tool(
        app, published.token, "search_elements", ontology="steel", limit=2, cursor=stale
    )
    tool_error(changed, "query.release_changed")


async def test_a_single_result_over_the_limit_is_a_tool_error(
    app: FastAPI, published: Published, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "RESULT_LIMIT_BYTES", 64)

    result = await _tool(app, published.token, "get_element", ontology="steel", id="Coil")

    tool_error(result, "mcp.result_too_large")


async def test_get_element_names_the_inverse_relation(app: FastAPI, published: Published) -> None:
    relation = _structured(
        await _tool(app, published.token, "get_element", ontology="steel", id="inspectedCoil")
    )

    assert relation["inverse"] == "质检记录"


async def test_an_empty_object_cursor_is_refused_and_audited(
    app: FastAPI, db: AsyncSession, published: Published
) -> None:
    result = await _tool(
        app, published.token, "search_objects", ontology="steel", type="Coil", cursor=""
    )

    tool_error(result, "validation.failed")
    events = list(
        await db.scalars(select(AuditEvent).where(AuditEvent.action == "mcp.tool_called"))
    )
    assert [event.detail["code"] for event in events] == ["validation.failed"]


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (RuntimeError("boom"), 500, "internal.error"),
        (HTTPException(499), 499, "mcp.client_disconnected"),
    ],
)
async def test_an_unexpected_failure_is_audited_and_propagates(
    app: FastAPI,
    db: AsyncSession,
    published: Published,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    status: int,
    code: str,
) -> None:
    async def fail(ctx: tools.Context, arguments: Any) -> dict[str, Any]:
        raise failure

    tool = tools.TOOLS["list_ontologies"]
    monkeypatch.setitem(tools.TOOLS, "list_ontologies", dataclasses.replace(tool, run=fail))

    async with make_client(app, raise_app_exceptions=False) as agent:
        response = await rpc(
            agent, published.token, "tools/call", {"name": "list_ontologies", "arguments": {}}
        )

    assert response.status_code == status
    events = list(
        await db.scalars(select(AuditEvent).where(AuditEvent.action == "mcp.tool_called"))
    )
    assert [event.detail["code"] for event in events] == [code]
