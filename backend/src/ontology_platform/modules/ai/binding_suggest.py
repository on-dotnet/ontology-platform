"""AI binding suggestions (spec 003, section 8): the model matches object types to tables,
properties to columns and relations to foreign keys from catalog metadata, deterministic code
checks every match, and what passes becomes a change set for review.

Like every AI proposal, the only output is a change set (source `ai_binding`) whose items all
wait for review. The skeleton fixes the shape; the pipeline arrives with batch 4b.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import not_implemented
from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.jobs.runner import JobContext

# Payload: {"suggestionId": "<uuid>"}
JOB_KIND = "bindings.suggest"


async def create_request(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.BindingSuggestionCreate,
    *,
    user_id: UUID,
    ip: str | None,
) -> schemas.BindingSuggestion:
    """Store the request and queue the job that answers it."""
    raise not_implemented("AI binding suggestions")


async def get_request(
    db: AsyncSession,
    suggestion_id: UUID,
    *,
    user_id: UUID,
) -> schemas.BindingSuggestion:
    """A request of the user's own (404 `binding_suggestion.not_found` for others')."""
    raise not_implemented("AI binding suggestions")


async def list_requests(
    db: AsyncSession,
    ontology_id: UUID,
    *,
    user_id: UUID,
    limit: int,
) -> list[schemas.BindingSuggestion]:
    """The user's latest requests about the ontology, newest first."""
    raise not_implemented("AI binding suggestions")


def make_handler(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway,
    model: str,
) -> Callable[[JobContext], Awaitable[None]]:
    """The handler of `bindings.suggest` jobs."""

    async def handle(job: JobContext) -> None:
        raise not_implemented("AI binding suggestions")

    return handle
