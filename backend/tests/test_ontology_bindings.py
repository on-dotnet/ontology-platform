"""Data bindings (spec 003, section 6). Batch 4a implements them and extends this file."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_support import add_elements, add_ontology, element, publish, sign_in


@pytest.mark.xfail(strict=True, reason="M3 batch 4a: data bindings")
async def test_a_merged_and_published_binding_is_in_the_snapshot(
    client: AsyncClient, db: AsyncSession
) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)
    source = DataSource(
        id=uuid4(),
        name="MES",
        kind="postgresql",
        host="steel-mes.example",
        port=5432,
        database="steel_mes",
        username="steel_reader",
    )
    db.add(source)
    await db.flush()
    # Bindings are checked against the cached catalog when they are proposed (spec 003, 6.2).
    db.add(
        CatalogTable(
            data_source_id=source.id,
            schema_name="mes",
            table_name="heat",
            kind="table",
            comment="炉次",
            columns=[
                {
                    "name": "heat_no",
                    "type": "character varying(20)",
                    "family": "string",
                    "nullable": False,
                    "comment": "炉次号",
                    "position": 1,
                }
            ],
            primary_key=["heat_no"],
            foreign_keys=[],
        )
    )
    await db.commit()
    await sign_in(client, db, Role.ADMIN)

    saved = await client.post(
        f"/api/ontologies/{steel.id}/edits",
        json={
            "items": [
                {
                    "op": "create",
                    "kind": "type_binding",
                    "tempRef": "heat-table",
                    "fields": {
                        "subjectRef": str(heat.id),
                        "binding": {
                            "target": "table",
                            "dataSourceId": str(source.id),
                            "schema": "mes",
                            "table": "heat",
                            "keyColumns": ["heat_no"],
                        },
                    },
                }
            ],
            "apply": True,
        },
        headers=csrf_headers(client),
    )
    published = await publish(client, steel)

    assert saved.status_code == 200
    assert saved.json()["merged"] is True
    assert published.status_code == 201
    assert published.json()["bindingCount"] == 1
