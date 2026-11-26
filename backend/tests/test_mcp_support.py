"""Shared helpers for the MCP tests: well-formed requests of protocol revision 2026-07-28.

Field names, headers and error codes follow the revision's schema
(schema/2026-07-28/schema.ts) and its Streamable HTTP transport page.
"""

import json
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_support import sign_in

PROTOCOL_VERSION = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "test-agent", "version": "1.0"},
}
READ_TOOLS = [
    "list_ontologies",
    "search_elements",
    "get_element",
    "search_objects",
    "get_object",
    "get_related_objects",
]

# JSON-RPC and MCP error codes of the revision.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022


async def new_token(
    client: AsyncClient, db: AsyncSession, role: Role, scopes: list[str]
) -> tuple[str, str]:
    """Sign the client in with `role` and create a token: (token, token id)."""
    await sign_in(client, db, role)
    response = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": scopes},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201, response.text
    created = response.json()
    return created["token"], created["info"]["id"]


def message(
    method: str, params: dict[str, Any] | None = None, *, id_: int | str = 1
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": id_,
        "method": method,
        "params": {"_meta": META, **(params or {})},
    }


def headers(
    token: str | None, method: str, *, name: str | None = None, version: str = PROTOCOL_VERSION
) -> dict[str, str]:
    result = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": version,
        "Mcp-Method": method,
    }
    if token is not None:
        result["Authorization"] = f"Bearer {token}"
    if name is not None:
        result["Mcp-Name"] = name
    return result


async def rpc(
    agent: AsyncClient, token: str, method: str, params: dict[str, Any] | None = None
) -> Response:
    name = (params or {}).get("name") if method == "tools/call" else None
    return await agent.post(
        "/mcp", json=message(method, params), headers=headers(token, method, name=name)
    )


async def call_tool(
    agent: AsyncClient, token: str, name: str, arguments: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The result of a tools/call, checked to carry the same content as structure and text."""
    response = await rpc(agent, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    result: dict[str, Any] = body["result"]
    assert result["resultType"] == "complete"
    [content] = result["content"]
    assert content["type"] == "text"
    assert json.loads(content["text"]) == result["structuredContent"]
    return result


def rpc_error(response: Response, status: int, code: int) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].split(";")[0] == "application/json"
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    error: dict[str, Any] = body["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str)
    return error


def tool_error(result: dict[str, Any], code: str) -> None:
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == code
    assert isinstance(result["structuredContent"]["message"], str)
