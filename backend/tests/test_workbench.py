"""Workbench summary: counts across ontologies and recent work, without sign-in noise."""

from pathlib import Path

import pytest
from httpx import AsyncClient

from ontology_platform.settings import Settings
from support import csrf_headers, login


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(update={"documents_dir": str(tmp_path)})


async def test_summary_requires_login(client: AsyncClient) -> None:
    response = await client.get("/api/workbench/summary")
    assert response.status_code == 401


async def test_summary_counts_and_recent_activity(client: AsyncClient) -> None:
    me = (await login(client)).json()
    empty = (await client.get("/api/workbench/summary")).json()
    assert empty == {
        "pendingChangeSets": 0,
        "entityTypes": 0,
        "processingDocuments": 0,
        "recentActivity": [],
    }

    created = await client.post(
        "/api/ontologies", json={"name": "钢铁冶金"}, headers=csrf_headers(client)
    )
    assert created.status_code == 201
    ontology_id = created.json()["id"]
    uploaded = await client.post(
        "/api/documents",
        files={"file": ("规程.txt", "炉次与浇次".encode(), "text/plain")},
        data={"ontologyId": ontology_id},
        headers=csrf_headers(client),
    )
    assert uploaded.status_code == 201

    summary = (await client.get("/api/workbench/summary")).json()
    assert summary["processingDocuments"] == 1
    activity = summary["recentActivity"]
    assert [item["action"] for item in activity] == ["document.uploaded", "ontology.created"]
    assert {item["actorName"] for item in activity} == {me["displayName"]}
    assert activity[0]["targetId"] == uploaded.json()["id"]
