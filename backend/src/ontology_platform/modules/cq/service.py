from typing import Never
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import not_implemented
from ontology_platform.modules.ai.schemas import QaQuestion
from ontology_platform.modules.cq.schemas import CoverageItem


async def record_result(db: AsyncSession, question: QaQuestion) -> None:
    raise NotImplementedError


async def coverage(db: AsyncSession, ontology_id: UUID) -> list[CoverageItem]:
    raise NotImplementedError


def unavailable() -> Never:
    raise not_implemented("Competency questions")
