"""Change-set proposals for gaps identified in a question."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.errors import not_implemented
from ontology_platform.modules.ai.gateway import ModelGateway
from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.jobs.runner import Handler, JobContext

JOB_KIND = "qa.gap"


async def create_gap_proposal(db: AsyncSession, question_id: UUID, *, user_id: UUID) -> QaQuestion:
    raise NotImplementedError


def make_gap_proposer(
    session_factory: async_sessionmaker[AsyncSession], gateway: ModelGateway, model: str
) -> Handler:
    async def handle(job: JobContext) -> None:
        raise not_implemented("Proposing a question gap change set")

    return handle
