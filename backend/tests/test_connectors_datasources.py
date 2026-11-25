"""Data sources (spec 003, section 5). Batch 3 implements them and extends this file."""

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_ontology_support import sign_in


@pytest.mark.xfail(strict=True, reason="M3 batch 3: data sources")
async def test_a_new_data_source_never_returns_its_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    secret = "s3cret-" + uuid4().hex
    body = {
        "name": "钢铁 MES",
        "kind": "postgresql",
        "host": "steel-mes.example",
        "port": 5432,
        "database": "steel_mes",
        "username": "steel_reader",
        "password": secret,
    }

    created = await client.post("/api/data-sources", json=body, headers=csrf_headers(client))
    listed = await client.get("/api/data-sources")
    stored = await db.scalar(select(DataSource.secret).where(DataSource.name == "钢铁 MES"))

    assert created.status_code == 201
    assert created.json()["hasCredential"] is True
    assert secret not in created.text
    assert secret not in listed.text
    assert stored is not None
    assert secret.encode() not in stored
