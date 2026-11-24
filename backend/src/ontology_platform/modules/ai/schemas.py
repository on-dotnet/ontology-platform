"""API models of the ai module."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

from ontology_platform.modules.ai.models import MESSAGE_MAX_LENGTH, AssistantStatus, AssistantStep
from ontology_platform.schemas import CamelModel


class AiStatus(CamelModel):
    configured: bool
    reachable: bool | None
    model: str | None


# ---------- AI assistant (spec 002 §10) ----------

Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX_LENGTH),
]
Page = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class AssistantContext(CamelModel):
    """Where the user was when they asked: the page and the element they had selected."""

    page: Page
    element_id: UUID | None = None


class AssistantRequestCreate(CamelModel):
    message: Message
    context: AssistantContext


class AssistantRequest(CamelModel):
    id: UUID
    ontology_id: UUID
    message: str
    context: AssistantContext
    status: AssistantStatus
    # The step running or reached: context, model, changeset.
    step: AssistantStep | None
    reply: str | None
    # Proposed operations left out because they failed the checks.
    dropped: int
    change_set_id: UUID | None
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
