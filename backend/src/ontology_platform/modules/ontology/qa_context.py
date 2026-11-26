"""Business terms from the active release for question planning."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class QaContext:
    text: str
    refs: Mapping[str, UUID]


async def qa_context(db: AsyncSession, ontology_id: UUID) -> QaContext:
    raise NotImplementedError
