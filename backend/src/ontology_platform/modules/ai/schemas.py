"""API models of the ai module."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints

from ontology_platform.modules.ai.models import (
    MESSAGE_MAX_LENGTH,
    AssistantStatus,
    AssistantStep,
    BindingSuggestionStep,
)
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


# ---------- AI binding suggestions (spec 003 §8) ----------

SUGGESTION_TABLES_MAX = 200
SUGGESTION_SCHEMAS_MAX = 50
SUGGESTION_TYPES_MAX = 300
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class TableRef(CamelModel):
    schema_name: Identifier = Field(alias="schema")
    name: Identifier


class BindingSuggestionCreate(CamelModel):
    """Which tables to look at: `tables` or `schemas` (one of them), and optionally which
    object types to suggest bindings for (default: every type without a binding)."""

    data_source_id: UUID
    tables: list[TableRef] | None = Field(
        default=None, min_length=1, max_length=SUGGESTION_TABLES_MAX
    )
    schemas: list[Identifier] | None = Field(
        default=None, min_length=1, max_length=SUGGESTION_SCHEMAS_MAX
    )
    type_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=SUGGESTION_TYPES_MAX)


class BindingSuggestion(CamelModel):
    id: UUID
    ontology_id: UUID
    data_source_id: UUID
    status: AssistantStatus
    # The step running or reached: catalog, match, columns, changeset.
    step: BindingSuggestionStep | None
    # Null when no suggestion passed the checks.
    change_set_id: UUID | None
    proposed: int
    dropped: int
    samples_sent: bool
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
