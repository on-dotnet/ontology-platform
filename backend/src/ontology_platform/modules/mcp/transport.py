"""The Streamable HTTP transport of MCP revision 2026-07-28 (spec 003, 9.1-9.2), stateless.

One POST carries one JSON-RPC message and gets one JSON response: no SSE, no session id, no
batches. The order of the checks matters: Origin first (a foreign page gets nothing, not even
an authentication answer), then the token, then the message, its headers and its `_meta`.
Field names, headers and error codes follow the revision's schema.ts and transport page.
"""

import base64
import binascii
import json
import re
from importlib import metadata
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import problem_response
from ontology_platform.modules.identity import tokens
from ontology_platform.modules.identity.api import bearer_token, client_ip
from ontology_platform.modules.mcp import tools
from ontology_platform.settings import Settings

PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_VERSIONS = [PROTOCOL_VERSION]
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"
# The discovery answer and the tool list change only with a deployment.
CACHE_TTL_MS = 60 * 60 * 1000

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

INSTRUCTIONS = (
    "Access to the platform's published ontologies and the business objects bound to them. "
    "Start with list_ontologies, look terms up with search_elements and get_element, then read "
    "data with search_objects, get_object and get_related_objects. Every result comes from the "
    "release in effect and names its version. propose_changes submits changes as a change set "
    "for people to review; it never changes an ontology itself."
)
ENCODED_HEADER = re.compile(r"=\?base64\?([A-Za-z0-9+/=]*)\?=")

type JsonId = str | int | None


class RpcError(Exception):
    def __init__(
        self, status: int, code: int, message: str, *, id_: JsonId = None, data: Any = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.id = id_
        self.data = data


def _error_response(exc: RpcError) -> JSONResponse:
    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.data is not None:
        error["data"] = exc.data
    return JSONResponse({"jsonrpc": "2.0", "id": exc.id, "error": error}, status_code=exc.status)


def _result(id_: JsonId, result: dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def _server_version() -> str:
    try:
        return metadata.version("ontology-platform")
    except metadata.PackageNotFoundError:
        return "0"


# ---------- Origin ----------


def _same_origin(origin: str, request: Request) -> bool:
    """Whether `origin` names this host. nginx passes `Host` without the port, so the port is
    compared only when the Host header carries one. Origin and Host both come from the
    caller, so this stops ordinary pages, not DNS rebinding: that is covered by the bearer
    token, which a browser never attaches by itself (cookies are refused here). Revisit if
    /mcp ever accepts cookies."""
    parts = urlsplit(origin)
    host = request.headers.get("host", "")
    if not parts.hostname or not host:
        return False
    served = urlsplit(f"//{host}")
    if parts.hostname != served.hostname:
        return False
    if served.port is None:
        return True
    default = {"http": 80, "https": 443}.get(parts.scheme)
    return (parts.port or default) == served.port


def origin_allowed(request: Request, settings: Settings) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True
    return origin in settings.mcp_origins or _same_origin(origin, request)


# ---------- the message ----------


def _envelope(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise RpcError(400, PARSE_ERROR, "Parse error.") from None
    if not isinstance(body, dict):
        raise RpcError(400, INVALID_REQUEST, "The body must be a single JSON-RPC message.")
    id_ = body.get("id")
    readable_id = id_ if isinstance(id_, str | int) and not isinstance(id_, bool) else None
    invalid = RpcError(400, INVALID_REQUEST, "Invalid JSON-RPC request.", id_=readable_id)
    if body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
        raise invalid
    if "id" in body and readable_id is None:
        raise invalid
    if not isinstance(body.get("params", {}), dict):
        raise invalid
    return body


def _decoded(value: str) -> str | None:
    encoded = ENCODED_HEADER.fullmatch(value)
    if encoded is None:
        return value
    try:
        return base64.b64decode(encoded.group(1), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        return None


def _check_headers(request: Request, method: str, params: dict[str, Any], id_: JsonId) -> str:
    version = request.headers.get("mcp-protocol-version")
    if version is None:
        raise RpcError(400, HEADER_MISMATCH, "The MCP-Protocol-Version header is missing.", id_=id_)
    if version not in SUPPORTED_VERSIONS:
        raise RpcError(
            400,
            UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version.",
            id_=id_,
            data={"supported": SUPPORTED_VERSIONS, "requested": version},
        )
    if request.headers.get("mcp-method") != method:
        raise RpcError(400, HEADER_MISMATCH, "The Mcp-Method header does not match.", id_=id_)
    if method == "tools/call":
        name = request.headers.get("mcp-name")
        if name is None or _decoded(name) != params.get("name"):
            raise RpcError(400, HEADER_MISMATCH, "The Mcp-Name header does not match.", id_=id_)
    return version


def _check_meta(params: dict[str, Any], version: str, id_: JsonId) -> None:
    meta = params.get("_meta")
    if (
        not isinstance(meta, dict)
        or not isinstance(meta.get(META_VERSION), str)
        or not isinstance(meta.get(META_CAPABILITIES), dict)
    ):
        raise RpcError(400, INVALID_PARAMS, "The request _meta is missing or incomplete.", id_=id_)
    if meta[META_VERSION] != version:
        raise RpcError(
            400, HEADER_MISMATCH, "The _meta protocol version does not match the header.", id_=id_
        )


# ---------- methods ----------


def _discover() -> dict[str, Any]:
    return {
        "resultType": "complete",
        "supportedVersions": SUPPORTED_VERSIONS,
        "capabilities": {"tools": {}},
        "instructions": INSTRUCTIONS,
        "ttlMs": CACHE_TTL_MS,
        "cacheScope": "public",
        "_meta": {
            META_SERVER_INFO: {
                "name": "ontology-platform",
                "title": "Ontology Platform",
                "version": _server_version(),
            }
        },
    }


def _tool_list() -> dict[str, Any]:
    return {
        "resultType": "complete",
        "tools": tools.definitions(),
        "ttlMs": CACHE_TTL_MS,
        "cacheScope": "public",
    }


def _insufficient_scope() -> JSONResponse:
    return problem_response(
        403,
        "auth.insufficient_scope",
        "The access token lacks a scope.",
        headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
    )


async def handle(request: Request, db: AsyncSession, settings: Settings) -> Response:
    if not origin_allowed(request, settings):
        return problem_response(403, "mcp.origin_not_allowed", "The Origin is not allowed.")
    # A cookie session is not enough here: external agents authenticate with a token only.
    token = bearer_token(request)
    if not token:
        return problem_response(
            401,
            "auth.not_authenticated",
            "An access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    context = await tokens.authenticate(db, token, ip=client_ip(request))
    try:
        body = _envelope(await request.body())
        method: str = body["method"]
        params: dict[str, Any] = body.get("params", {})
        if "id" not in body:
            # A notification: nothing is answered, but every POST names the revision.
            if request.headers.get("mcp-protocol-version") not in SUPPORTED_VERSIONS:
                return Response(status_code=400)
            return Response(status_code=202)
        id_: JsonId = body["id"]
        version = _check_headers(request, method, params, id_)
        _check_meta(params, version, id_)
        if method not in ("server/discover", "tools/list", "tools/call"):
            raise RpcError(404, METHOD_NOT_FOUND, "Method not found.", id_=id_)
        # Discovery and the tool list need some scope the owner still holds; each tool checks
        # its own, so a token for proposals alone can still discover (batch 6b).
        if not context.scopes:
            return _insufficient_scope()
        if method == "server/discover":
            return _result(id_, _discover())
        if method == "tools/list":
            return _result(id_, _tool_list())
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise RpcError(400, INVALID_PARAMS, "Invalid tools/call parameters.", id_=id_)
        try:
            outcome = await tools.call(db, request, context, name, arguments, ip=client_ip(request))
        except tools.UnknownToolError:
            raise RpcError(400, INVALID_PARAMS, f"Unknown tool: {name}", id_=id_) from None
    except RpcError as exc:
        return _error_response(exc)
    return _result(
        id_,
        {
            "resultType": "complete",
            "content": [{"type": "text", "text": tools.text(outcome.content)}],
            "structuredContent": outcome.content,
            "isError": outcome.is_error,
        },
    )
