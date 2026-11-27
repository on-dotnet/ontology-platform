"""Review assistance job entry points."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import not_implemented
from ontology_platform.modules.ai import schemas
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.identity.service import Principal
from ontology_platform.modules.jobs.runner import Handler, JobContext
from ontology_platform.settings import Settings

JOB_KIND = "review.assist"


async def request_assist(
    db: AsyncSession,
    change_set_id: UUID,
    *,
    user: Principal,
    locale: schemas.Locale,
    settings: Settings,
) -> schemas.ReviewAssist:
    raise not_implemented("Review assistance request")


async def latest_assist(db: AsyncSession, change_set_id: UUID) -> schemas.ReviewAssist | None:
    raise not_implemented("Review assistance result")


def make_review_assistant(
    session_factory: async_sessionmaker[AsyncSession],
    gateway: ModelGateway | None,
    model: str | None,
    settings: Settings,
) -> Handler:
    async def handle(context: JobContext) -> None:
        # Batch 6: every way out (done, failure, timeout, lost lease) must move the row out of
        # queued/running, or the partial unique index keeps answering 409 for this change set.
        raise ValueError("review.assist is not implemented")

    return handle
