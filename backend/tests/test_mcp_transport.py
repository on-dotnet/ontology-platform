"""The MCP endpoint's transport (spec 003, 9.1 and 9.2; section 15, "令牌" for /mcp).

Every protocol field and error code is the 2026-07-28 revision's: the Streamable HTTP page
for headers and statuses, schema.ts for the result shapes and the codes.
"""

import base64
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.settings import Settings
from support import csrf_headers, make_client
from test_identity_tokens import backdate, set_user
from test_mcp_support import (
    HEADER_MISMATCH,
    INVALID_PARAMS,
    INVALID_REQUEST,
    META,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION,
    READ_TOOLS,
    UNSUPPORTED_PROTOCOL_VERSION,
    headers,
    message,
    new_token,
    rpc,
    rpc_error,
)

AGENT_ORIGIN = "https://agent.example"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"mcp_allowed_origins": f"{AGENT_ORIGIN}, https://b.example"})


async def test_mcp_refuses_requests_without_a_token(client: AsyncClient) -> None:
    response = await client.post("/mcp", json={})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_mcp_takes_a_valid_token(app: FastAPI, client: AsyncClient, db: AsyncSession) -> None:
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])

    async with make_client(app) as agent:
        response = await agent.post("/mcp", json={}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code not in (401, 501)


# ---------- authentication ----------


async def test_an_invalid_token_is_refused_with_the_bearer_challenge(client: AsyncClient) -> None:
    response = await rpc(client, "op_pat_" + "A" * 43, "server/discover")

    assert response.status_code == 401
    assert response.json()["code"] == "auth.invalid_token"
    assert response.headers["WWW-Authenticate"] == 'Bearer error="invalid_token"'


@pytest.mark.parametrize("change", ["revoked", "expired", "inactive"])
async def test_a_dead_token_is_refused_on_the_next_request(
    app: FastAPI, client: AsyncClient, db: AsyncSession, change: str
) -> None:
    token, token_id = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    async with make_client(app) as agent:
        assert (await rpc(agent, token, "server/discover")).status_code == 200
        if change == "revoked":
            revoked = await client.delete(
                f"/api/auth/tokens/{token_id}", headers=csrf_headers(client)
            )
            assert revoked.status_code == 204
        elif change == "expired":
            await backdate(db, token_id, days=5, expires_in=-timedelta(seconds=1))
        else:
            await set_user(db, "viewer-user", is_active=False)
        after = await rpc(agent, token, "server/discover")

    assert after.status_code == 401
    assert after.json()["code"] == "auth.invalid_token"


async def test_protocol_methods_need_a_scope_the_owner_still_holds(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    token, _ = await new_token(client, db, Role.EDITOR, ["changes:propose"])
    await set_user(db, "editor-user", role=Role.VIEWER.value)

    async with make_client(app) as agent:
        for method in ("server/discover", "tools/list"):
            response = await rpc(agent, token, method)
            assert response.status_code == 403, method
            assert response.json()["code"] == "auth.insufficient_scope"
            assert response.headers["WWW-Authenticate"] == 'Bearer error="insufficient_scope"'


# ---------- HTTP methods and Origin ----------


@pytest.mark.parametrize("method", ["GET", "DELETE"])
async def test_only_post_is_supported(client: AsyncClient, method: str) -> None:
    response = await client.request(method, "/mcp")

    assert response.status_code == 405
    assert response.headers["Allow"] == "POST"


@pytest.mark.parametrize(
    ("origin", "status"),
    [
        (None, 200),
        ("http://testserver", 200),
        (AGENT_ORIGIN, 200),
        ("https://b.example", 200),
        ("https://evil.example", 403),
        ("http://testserver.evil.example", 403),
        ("null", 403),
    ],
)
async def test_the_origin_is_checked_when_present(
    app: FastAPI, client: AsyncClient, db: AsyncSession, origin: str | None, status: int
) -> None:
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    request_headers = headers(token, "server/discover")
    if origin is not None:
        request_headers["Origin"] = origin

    async with make_client(app) as agent:
        response = await agent.post(
            "/mcp", json=message("server/discover"), headers=request_headers
        )

    assert response.status_code == status, response.text


async def test_a_foreign_origin_is_refused_before_authentication(client: AsyncClient) -> None:
    response = await client.post("/mcp", json={}, headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


# ---------- JSON-RPC envelope and headers ----------


@pytest.fixture
async def token(client: AsyncClient, db: AsyncSession) -> str:
    created, _ = await new_token(client, db, Role.VIEWER, ["ontology:read", "objects:read"])
    return created


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"{not json", PARSE_ERROR),
        (b"[]", INVALID_REQUEST),
        (b'[{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}]', INVALID_REQUEST),
        (b'{"jsonrpc": "1.0", "id": 1, "method": "tools/list"}', INVALID_REQUEST),
        (b'{"jsonrpc": "2.0", "id": null, "method": "tools/list"}', INVALID_REQUEST),
        (b'{"jsonrpc": "2.0", "id": 1, "method": 7}', INVALID_REQUEST),
        (b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": []}', INVALID_REQUEST),
    ],
)
async def test_a_malformed_message_is_refused(
    client: AsyncClient, token: str, body: bytes, code: int
) -> None:
    response = await client.post(
        "/mcp",
        content=body,
        headers={**headers(token, "tools/list"), "Content-Type": "application/json"},
    )

    rpc_error(response, 400, code)
    # JSON-RPC 2.0: the id is null when it cannot be read from the message.
    assert response.json()["id"] in (None, 1)


async def test_a_notification_is_accepted_without_a_body(client: AsyncClient, token: str) -> None:
    body = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}

    response = await client.post(
        "/mcp", json=body, headers=headers(token, "notifications/cancelled")
    )

    assert response.status_code == 202
    assert response.content == b""


async def test_the_protocol_version_header_is_required(client: AsyncClient, token: str) -> None:
    request_headers = headers(token, "tools/list")
    del request_headers["MCP-Protocol-Version"]

    response = await client.post("/mcp", json=message("tools/list"), headers=request_headers)

    rpc_error(response, 400, HEADER_MISMATCH)


@pytest.mark.parametrize("version", ["2025-11-25", "2025-06-18", "1900-01-01"])
async def test_other_protocol_versions_are_not_supported(
    client: AsyncClient, token: str, version: str
) -> None:
    body = message("tools/list")
    body["params"]["_meta"] = {**META, "io.modelcontextprotocol/protocolVersion": version}

    response = await client.post(
        "/mcp", json=body, headers=headers(token, "tools/list", version=version)
    )

    error = rpc_error(response, 400, UNSUPPORTED_PROTOCOL_VERSION)
    assert error["data"] == {"supported": [PROTOCOL_VERSION], "requested": version}


async def test_the_method_header_must_match_the_body(client: AsyncClient, token: str) -> None:
    missing = headers(token, "tools/list")
    del missing["Mcp-Method"]
    for request_headers in (missing, headers(token, "server/discover")):
        response = await client.post("/mcp", json=message("tools/list"), headers=request_headers)
        rpc_error(response, 400, HEADER_MISMATCH)


async def test_a_tool_call_names_its_tool_in_a_header(client: AsyncClient, token: str) -> None:
    body = message("tools/call", {"name": "list_ontologies", "arguments": {}})
    for name in (None, "search_elements", "LIST_ONTOLOGIES"):
        response = await client.post(
            "/mcp", json=body, headers=headers(token, "tools/call", name=name)
        )
        rpc_error(response, 400, HEADER_MISMATCH)

    encoded = base64.b64encode(b"list_ontologies").decode()
    response = await client.post(
        "/mcp", json=body, headers=headers(token, "tools/call", name=f"=?base64?{encoded}?=")
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["isError"] is False


async def test_the_request_meta_is_required(client: AsyncClient, token: str) -> None:
    for meta in (None, {}, {"io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION}):
        body = message("tools/list")
        if meta is None:
            del body["params"]["_meta"]
        else:
            body["params"]["_meta"] = meta
        response = await client.post("/mcp", json=body, headers=headers(token, "tools/list"))
        rpc_error(response, 400, INVALID_PARAMS)


async def test_the_meta_version_must_match_the_header(client: AsyncClient, token: str) -> None:
    body = message("tools/list")
    body["params"]["_meta"] = {**META, "io.modelcontextprotocol/protocolVersion": "2025-11-25"}

    response = await client.post("/mcp", json=body, headers=headers(token, "tools/list"))

    rpc_error(response, 400, HEADER_MISMATCH)


@pytest.mark.parametrize("method", ["initialize", "ping", "resources/list", "prompts/get"])
async def test_unknown_methods_are_not_found(client: AsyncClient, token: str, method: str) -> None:
    response = await client.post("/mcp", json=message(method), headers=headers(token, method))

    rpc_error(response, 404, METHOD_NOT_FOUND)


async def test_an_unknown_tool_is_an_invalid_params_error(client: AsyncClient, token: str) -> None:
    response = await rpc(client, token, "tools/call", {"name": "propose_changes", "arguments": {}})

    rpc_error(response, 400, INVALID_PARAMS)


# ---------- server/discover and tools/list ----------


async def test_discover_describes_the_server(client: AsyncClient, token: str) -> None:
    response = await client.post(
        "/mcp",
        json=message("server/discover", id_="a-1"),
        headers=headers(token, "server/discover"),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/json"
    assert "mcp-session-id" not in response.headers
    body = response.json()
    assert (body["jsonrpc"], body["id"]) == ("2.0", "a-1")
    result = body["result"]
    assert result["resultType"] == "complete"
    assert result["supportedVersions"] == [PROTOCOL_VERSION]
    assert result["capabilities"] == {"tools": {}}
    assert isinstance(result["ttlMs"], int)
    assert result["ttlMs"] > 0
    assert result["cacheScope"] == "public"
    server = result["_meta"]["io.modelcontextprotocol/serverInfo"]
    assert server["name"]
    assert server["version"]
    assert isinstance(result["instructions"], str)


async def test_the_tool_list_is_the_same_for_every_token(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    lists = []
    for scopes in (["ontology:read"], ["objects:read"], ["ontology:read", "objects:read"]):
        token, _ = await new_token(client, db, Role.VIEWER, scopes)
        async with make_client(app) as agent:
            response = await rpc(agent, token, "tools/list")
        assert response.status_code == 200
        lists.append(response.json()["result"])

    assert lists[0] == lists[1] == lists[2]
    result = lists[0]
    assert result["resultType"] == "complete"
    assert result["cacheScope"] == "public"
    assert result["ttlMs"] > 0
    assert "nextCursor" not in result
    assert [tool["name"] for tool in result["tools"]] == READ_TOOLS
    for tool in result["tools"]:
        assert tool["title"]
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["openWorldHint"] is False


@pytest.mark.parametrize(
    ("origin", "status"),
    [("http://testserver:28080", 200), ("http://testserver:9999", 403), ("http://testserver", 403)],
)
async def test_the_port_is_compared_when_the_host_names_one(
    app: FastAPI, client: AsyncClient, db: AsyncSession, origin: str, status: int
) -> None:
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    request_headers = {**headers(token, "server/discover"), "Host": "testserver:28080"}
    request_headers["Origin"] = origin

    async with make_client(app) as agent:
        response = await agent.post(
            "/mcp", json=message("server/discover"), headers=request_headers
        )

    assert response.status_code == status, response.text


async def test_a_notification_still_names_the_revision(client: AsyncClient, token: str) -> None:
    body = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}
    request_headers = headers(token, "notifications/cancelled")
    del request_headers["MCP-Protocol-Version"]

    response = await client.post("/mcp", json=body, headers=request_headers)

    assert response.status_code == 400
