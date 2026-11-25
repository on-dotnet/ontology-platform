"""AI binding suggestions (spec 003, section 8). Batch 4b implements them and extends this file
with a fake gateway that runs the whole job."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import ChangeSet, Element
from support import csrf_headers
from test_ontology_support import add_elements, add_ontology, element, sign_in


@pytest.mark.xfail(strict=True, reason="M3 batch 4b: AI binding suggestions")
async def test_a_suggestion_request_only_queues_work(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await add_elements(db, element(steel, "entity_type", "Heat", "炉次"))
    source = DataSource(
        id=uuid4(),
        name="MES",
        kind="postgresql",
        host="steel-mes.example",
        port=5432,
        database="steel_mes",
        username="steel_reader",
        catalog_status="ready",
    )
    db.add(source)
    await db.commit()
    await sign_in(client, db, Role.EDITOR)
    elements_before = await db.scalar(select(func.count()).select_from(Element))

    response = await client.post(
        f"/api/ontologies/{steel.id}/binding-suggestions",
        json={"dataSourceId": str(source.id), "schemas": ["mes"]},
        headers=csrf_headers(client),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["changeSetId"] is None
    assert await db.scalar(select(func.count()).select_from(Element)) == elements_before
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0
