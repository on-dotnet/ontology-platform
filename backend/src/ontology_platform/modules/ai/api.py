"""HTTP routes of the ai module."""

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from ontology_platform.modules.ai.gateway import ModelGateway, OpenAIGateway
from ontology_platform.modules.ai.schemas import AiStatus
from ontology_platform.modules.identity.api import CurrentUser
from ontology_platform.settings import Settings, get_settings

router = APIRouter(prefix="/api", tags=["ai"])

STATUS_CACHE_SECONDS = 60.0


def get_gateway(request: Request) -> ModelGateway:
    """One gateway per app; tests replace `app.state.model_gateway` with a fake."""
    gateway: ModelGateway | None = getattr(request.app.state, "model_gateway", None)
    if gateway is None:
        settings: Settings = request.app.state.settings
        gateway = OpenAIGateway(settings, getattr(request.app.state, "session_factory", None))
        request.app.state.model_gateway = gateway
    return gateway


Gateway = Annotated[ModelGateway, Depends(get_gateway)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/ai/status")
async def ai_status(
    request: Request, user: CurrentUser, settings: AppSettings, gateway: Gateway
) -> AiStatus:
    """Whether model access is configured and reachable. Never reveals the key or the proxy."""
    if not settings.ai_configured:
        return AiStatus(configured=False, reachable=None, model=None)
    state = request.app.state
    lock: asyncio.Lock | None = getattr(state, "ai_status_lock", None)
    if lock is None:
        lock = state.ai_status_lock = asyncio.Lock()
    # One check at a time: concurrent page loads wait for it instead of each pinging.
    async with lock:
        cached: tuple[float, bool] | None = getattr(state, "ai_status_cache", None)
        now = time.monotonic()
        if cached is not None and now - cached[0] < STATUS_CACHE_SECONDS:
            reachable = cached[1]
        else:
            reachable = await gateway.ping()
            state.ai_status_cache = (time.monotonic(), reachable)
    return AiStatus(configured=True, reachable=reachable, model=settings.ai_model)
