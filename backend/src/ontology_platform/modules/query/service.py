"""Browsing objects by ontology (spec 003, section 7).

A request is planned against the bindings of the release in effect and turned into structured
`SelectQuery` values for the connectors module. This module never writes SQL and never opens a
connection. The skeleton fixes the shape; the implementation arrives with batch 5.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import not_implemented
from ontology_platform.modules.query import schemas


async def list_types(db: AsyncSession, ontology_id: UUID) -> schemas.ObjectTypeList:
    """The object types of the release in effect that are bound to data."""
    raise not_implemented("Browsing objects")


async def search(
    db: AsyncSession,
    ontology_id: UUID,
    body: schemas.ObjectSearch,
) -> schemas.ObjectPage:
    raise not_implemented("Browsing objects")


async def get_object(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    key: str,
) -> schemas.ObjectDetail:
    raise not_implemented("Browsing objects")


async def related(
    db: AsyncSession,
    ontology_id: UUID,
    type_id: UUID,
    key: str,
    *,
    relation_id: UUID,
    direction: schemas.Direction,
    limit: int,
    cursor: str | None,
) -> schemas.ObjectPage:
    """One hop along a relation, forwards (`out`) or backwards (`in`)."""
    raise not_implemented("Browsing objects")
