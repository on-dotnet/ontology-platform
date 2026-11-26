"""The MCP endpoint (spec 003, section 9): POST /mcp, JSON-RPC, protocol revision 2026-07-28.

Not under /api and not part of the OpenAPI document. The transport is in `transport.py`, the
tools in `tools.py`. GET and DELETE are answered 405 by the router, as the revision asks of a
server that offers no stream and no session.
"""

from fastapi import APIRouter, Request, Response

from ontology_platform.db import DbSession
from ontology_platform.modules.mcp import transport
from ontology_platform.settings import get_settings

router = APIRouter(tags=["mcp"])


@router.post("/mcp", include_in_schema=False, response_model=None)
async def mcp(request: Request, db: DbSession) -> Response:
    return await transport.handle(request, db, get_settings(request))
