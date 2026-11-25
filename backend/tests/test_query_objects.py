"""Browsing objects by ontology (spec 003, section 7). Batch 5 implements it and extends this
file; the bindings it needs come from hand-made change sets, not from AI suggestions."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from test_ontology_support import add_elements, add_ontology, element, sign_in


@pytest.mark.xfail(strict=True, reason="M3 batch 5: object queries")
async def test_nothing_is_queried_before_a_release(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await add_elements(db, element(steel, "entity_type", "Heat", "炉次"))
    await db.commit()
    await sign_in(client, db, Role.VIEWER)

    response = await client.get(f"/api/ontologies/{steel.id}/objects/types")

    assert response.status_code == 409
    assert response.json()["code"] == "query.no_release"
