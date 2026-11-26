"""Who may call the data source routes (spec 003, section 13 and the appendix).

These rows were in test_m3_skeleton.py until batch 3 implemented the routes: a session is
needed for every one, and the role check comes first, without side effects.
"""

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs.models import Job
from support import csrf_headers
from test_ontology_support import sign_in

ID = "00000000-0000-4000-8000-000000000000"
Call = tuple[str, str, dict[str, Any] | None]

DATA_SOURCE = {
    "name": "钢铁 MES",
    "kind": "postgresql",
    "host": "steel-mes.example",
    "port": 5432,
    "database": "steel_mes",
    "username": "steel_reader",
    "password": "not-a-real-password",
}
CONNECTION_TEST = {key: value for key, value in DATA_SOURCE.items() if key != "name"}

EVERYONE: list[Call] = [
    ("GET", "/api/data-sources", None),
    ("GET", f"/api/data-sources/{ID}", None),
]
EDITORS: list[Call] = [
    ("POST", f"/api/data-sources/{ID}/test", None),
    ("POST", f"/api/data-sources/{ID}/catalog/refresh", None),
    ("GET", f"/api/data-sources/{ID}/catalog/schemas", None),
    ("GET", f"/api/data-sources/{ID}/catalog/tables", None),
    ("GET", f"/api/data-sources/{ID}/catalog/tables/mes/heat", None),
]
ADMINS: list[Call] = [
    ("POST", "/api/data-sources", DATA_SOURCE),
    ("PATCH", f"/api/data-sources/{ID}", {"name": "MES", "revision": 1}),
    ("POST", f"/api/data-sources/{ID}/archive", None),
    ("POST", "/api/data-sources/test", CONNECTION_TEST),
]
ALL_CALLS = [*EVERYONE, *EDITORS, *ADMINS]


async def _call(client: AsyncClient, request: Call) -> Response:
    method, path, body = request
    headers = csrf_headers(client) if "op_csrf" in client.cookies else {}
    return await client.request(method, path, json=body, headers=headers)


async def _side_effects(db: AsyncSession) -> tuple[int, int, int]:
    counts = []
    for model in (DataSource, AuditEvent, Job):
        counts.append(await db.scalar(select(func.count()).select_from(model)) or 0)
    await db.commit()
    return counts[0], counts[1], counts[2]


async def test_every_data_source_route_needs_a_session(client: AsyncClient) -> None:
    assert len(ALL_CALLS) == 11
    for request in ALL_CALLS:
        response = await _call(client, request)
        assert response.status_code == 401, request
        assert response.json()["code"] == "auth.not_authenticated"


@pytest.mark.parametrize("role", list(Role))
async def test_roles_come_first_and_refusals_change_nothing(
    client: AsyncClient, db: AsyncSession, role: Role
) -> None:
    await sign_in(client, db, role)
    allowed = {
        "everyone": True,
        "editors": role in {Role.ADMIN, Role.EDITOR, Role.REVIEWER},
        "admins": role is Role.ADMIN,
    }
    for group, requests in (("everyone", EVERYONE), ("editors", EDITORS), ("admins", ADMINS)):
        for request in requests:
            before = await _side_effects(db)
            response = await _call(client, request)
            if allowed[group]:
                assert response.status_code not in (401, 403, 501), request
            else:
                assert response.status_code == 403, request
                assert response.json()["code"] == "auth.forbidden"
                assert await _side_effects(db) == before, request
