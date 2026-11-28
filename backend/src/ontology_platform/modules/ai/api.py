"""HTTP routes of the ai module."""

import asyncio
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from ontology_platform.db import DbSession
from ontology_platform.errors import problem_responses
from ontology_platform.modules.ai import (
    assistant,
    binding_suggest,
    qa,
    qa_gap,
    review_assist,
    schemas,
)
from ontology_platform.modules.ai.gateway import ModelGateway, OpenAIGateway
from ontology_platform.modules.ai.schemas import AiStatus
from ontology_platform.modules.identity.api import CurrentUser, client_ip, require_role
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.identity.service import Principal
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
Creator = Annotated[Principal, Depends(require_role(Role.ADMIN, Role.EDITOR, Role.REVIEWER))]


@router.post(
    "/change-sets/{id}/review-assist",
    status_code=202,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def request_review_assist(
    id: UUID, body: schemas.AssistRequest, user: Creator, db: DbSession, settings: AppSettings
) -> schemas.ReviewAssist:
    return await review_assist.request_assist(
        db, id, user=user, locale=body.locale, settings=settings
    )


@router.get("/change-sets/{id}/review-assist", responses=problem_responses(401, 404, 422))
async def get_review_assist(
    id: UUID, user: CurrentUser, db: DbSession
) -> schemas.ReviewAssist | None:
    return await review_assist.latest_assist(db, id)


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


# ---------- AI assistant (spec 002 §10) ----------


@router.post(
    "/ontologies/{id}/assistant/requests",
    status_code=201,
    responses=problem_responses(401, 403, 404, 422),
)
async def create_assistant_request(
    id: UUID,
    body: schemas.AssistantRequestCreate,
    user: Creator,
    db: DbSession,
) -> schemas.AssistantRequest:
    """Ask the assistant for a change. The answer comes from a background job: its result is a
    change set waiting for review (or only a reply); poll the request for it."""
    return await assistant.create_request(db, id, body, user_id=user.id)


@router.get("/assistant/requests/{id}", responses=problem_responses(401, 404, 422))
async def get_assistant_request(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> schemas.AssistantRequest:
    """One of the user's own requests (404 `assistant.not_found` for others')."""
    return await assistant.get_request(db, id, user_id=user.id)


@router.get("/ontologies/{id}/assistant/requests", responses=problem_responses(401, 422))
async def list_assistant_requests(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[schemas.AssistantRequest]:
    """The user's latest requests about the ontology, newest first."""
    return await assistant.list_requests(db, id, user_id=user.id, limit=limit)


# ---------- AI binding suggestions (spec 003 §8) ----------
# Editors and above: suggestions read the catalog, which viewers may not browse.


@router.post(
    "/ontologies/{id}/binding-suggestions",
    status_code=202,
    responses=problem_responses(401, 403, 404, 409, 422),
)
async def create_binding_suggestion(
    id: UUID,
    body: schemas.BindingSuggestionCreate,
    request: Request,
    user: Creator,
    db: DbSession,
) -> schemas.BindingSuggestion:
    """Ask the AI to suggest bindings to the tables of a data source. The result comes from a
    background job: a change set waiting for review; poll the request for it."""
    return await binding_suggest.create_request(
        db, id, body, user_id=user.id, ip=client_ip(request)
    )


@router.get("/binding-suggestions/{id}", responses=problem_responses(401, 403, 404, 422))
async def get_binding_suggestion(
    id: UUID,
    user: Creator,
    db: DbSession,
) -> schemas.BindingSuggestion:
    """One of the user's own requests (404 `binding_suggestion.not_found` for others')."""
    return await binding_suggest.get_request(db, id, user_id=user.id)


@router.get(
    "/ontologies/{id}/binding-suggestions",
    responses=problem_responses(401, 403, 422),
)
async def list_binding_suggestions(
    id: UUID,
    user: Creator,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[schemas.BindingSuggestion]:
    """The user's latest requests about the ontology, newest first."""
    return await binding_suggest.list_requests(db, id, user_id=user.id, limit=limit)


@router.post(
    "/ontologies/{id}/qa/questions",
    status_code=202,
    responses=problem_responses(401, 403, 404, 409, 422, 429),
)
async def create_qa_question(
    id: UUID,
    body: schemas.QaQuestionCreate,
    user: CurrentUser,
    db: DbSession,
    settings: AppSettings,
) -> schemas.QaQuestion:
    db.info["qa_settings"] = settings
    return await qa.create_question(db, id, body, user_id=user.id)


@router.get("/ontologies/{id}/qa/questions", responses=problem_responses(401, 403, 422))
async def list_qa_questions(
    id: UUID,
    user: CurrentUser,
    db: DbSession,
    asked_by: Annotated[qa.AskedBy, Query(alias="askedBy")] = "me",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
) -> schemas.QaQuestionList:
    return await qa.list_questions(
        db, id, actor=user, asked_by=asked_by, limit=limit, cursor=cursor
    )


@router.get("/qa/questions/{id}", responses=problem_responses(401, 403, 404, 422))
async def get_qa_question(id: UUID, user: CurrentUser, db: DbSession) -> schemas.QaQuestion:
    return await qa.get_question(db, id, actor=user)


@router.post(
    "/qa/questions/{id}/gap-proposal",
    status_code=202,
    responses={
        200: {"model": schemas.QaQuestion},
        **problem_responses(401, 403, 404, 409, 422),
    },
)
async def create_qa_gap_proposal(
    id: UUID, user: Creator, db: DbSession, settings: AppSettings, response: Response
) -> schemas.QaQuestion:
    await qa.require_visible(db, id, user)
    question, created = await qa_gap.enqueue_gap_proposal(
        db, id, user_id=user.id, settings=settings
    )
    if not created:
        response.status_code = 200
    return question
