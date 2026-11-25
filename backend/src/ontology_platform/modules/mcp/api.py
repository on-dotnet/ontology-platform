"""The MCP endpoint (spec 003, section 9): POST /mcp, JSON-RPC, protocol revision 2026-07-28.

Not under /api and not part of the OpenAPI document. The skeleton only fixes the address and
the rule that every request needs an access token; the transport and the tools arrive with
batch 6, which checks every field name against the schema of the specification.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ontology_platform.errors import not_implemented, problem_response

router = APIRouter(tags=["mcp"])

BEARER = "bearer "


@router.post("/mcp", include_in_schema=False, response_model=None)
async def mcp(request: Request) -> JSONResponse:
    # A cookie session is not enough here: external agents authenticate with a token only.
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith(BEARER) or not authorization[len(BEARER) :].strip():
        return problem_response(
            401,
            "auth.not_authenticated",
            "An access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise not_implemented("The MCP endpoint")
