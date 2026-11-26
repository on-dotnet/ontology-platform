"""Credentials never show, across the whole M3 flow (spec 003, section 15, the "全流程" part of
"凭据不回显"): the connector part (test_connectors_secrets.py) plus the AI suggestion, review,
release, query and MCP of test_m3_end_to_end.run_flow.

The marker is the data source's password: the flow has to connect with it, so it is the real
one, a random string from the external_source fixture. The access token's full text is checked
the same way everywhere but in the one response that hands it out.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.settings import Settings
from test_m3_end_to_end import run_flow

# Everything the flow leaves behind that could have picked a credential up.
KEPT = (
    "audit.events",
    "jobs.jobs",
    "ai.binding_suggestions",
    "ontology.change_sets",
    "ontology.change_items",
    "ontology.evidence",
    "ontology.releases",
    "connectors.data_sources",
    "connectors.catalog_tables",
    "identity.access_tokens",
)


async def _stored_text(db: AsyncSession) -> str:
    parts: list[str] = []
    for table in KEPT:
        rows = await db.execute(text(f"SELECT to_jsonb(t)::text FROM {table} t"))  # noqa: S608
        parts.extend(row[0] for row in rows)
    return "\n".join(parts)


async def test_the_password_and_the_token_never_show_in_the_whole_flow(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="sqlalchemy.pool")
    password = external_source.reader_password

    flow = await run_flow(app, client, db, external_source, settings, monkeypatch)

    paths = {response.request.url.path for response in flow.responses}
    # The flow really went through every part the scan covers.
    for part in ("/test", "/catalog/refresh", "/binding-suggestions", "/merge", "/releases"):
        assert any(path.endswith(part) for path in paths), part
    assert any("/related" in path for path in paths)
    assert "/mcp" in paths
    logs = "\n".join([record.getMessage() for record in caplog.records] + [caplog.text])
    stored = await _stored_text(db)
    for response in flow.responses:
        assert password not in response.text, response.request.url
        assert all(password not in value for value in response.headers.values())
    assert password not in logs
    assert password not in stored
    secret = await db.scalar(select(DataSource.secret).where(DataSource.id == flow.source_id))
    assert secret is not None
    assert password.encode() not in secret

    handed_out = [r for r in flow.responses if flow.token in r.text]
    assert [(r.request.method, r.request.url.path) for r in handed_out] == [
        ("POST", "/api/auth/tokens")
    ]
    for response in flow.responses:
        assert all(flow.token not in value for value in response.headers.values())
    assert flow.token not in logs
    assert flow.token not in stored
