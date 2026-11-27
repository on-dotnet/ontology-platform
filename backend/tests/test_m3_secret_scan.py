"""Credentials never show, across the whole M3 flow (spec 003, section 15, the "全流程" part of
"凭据不回显"): the connector part (test_connectors_secrets.py) plus the AI suggestion, review,
release, query and MCP of test_m3_end_to_end.run_flow.

The marker is the data source's password: the flow has to connect with it, so it is the real
one, a random string from the external_source fixture. The access token's full text is checked
the same way everywhere but in the one response that hands it out. Stored data is read from
every table of the platform's database, so a new table is scanned without being listed.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import column, select, table, text
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors.models import DataSource
from ontology_platform.settings import Settings
from test_m3_end_to_end import run_flow

# Tables the flow must have written to, so that the scan of every table cannot pass empty.
WRITTEN = (
    "audit.events",
    "jobs.jobs",
    "ai.binding_suggestions",
    "ontology.change_items",
    "ontology.evidence",
    "ontology.elements",
    "ontology.releases",
    "connectors.data_sources",
    "connectors.catalog_tables",
    "identity.access_tokens",
)


async def _stored(db: AsyncSession) -> dict[str, str]:
    """Every row of every table of the platform's database, as text, by table."""
    tables = await db.execute(
        text(
            "SELECT table_schema || '.' || table_name FROM information_schema.tables"
            " WHERE table_type = 'BASE TABLE'"
            " AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
    )
    stored: dict[str, str] = {}
    for (name,) in tables:
        rows = await db.execute(text(f"SELECT to_jsonb(t)::text FROM {name} t"))  # noqa: S608
        stored[name] = "\n".join(row[0] for row in rows)
    return stored


async def _binary_columns(db: AsyncSession) -> dict[str, list[bytes]]:
    columns = await db.execute(
        text(
            "SELECT table_schema, table_name, column_name FROM information_schema.columns"
            " JOIN information_schema.tables USING (table_catalog, table_schema, table_name)"
            " WHERE table_type = 'BASE TABLE' AND udt_schema = 'pg_catalog' AND udt_name = 'bytea'"
            " AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
    )
    stored: dict[str, list[bytes]] = {}
    for schema, name, field in columns:
        relation = table(name, column(field), schema=schema)
        binary = relation.c[field]
        values = await db.scalars(select(binary).where(binary.is_not(None)))
        stored[f"{schema}.{name}.{field}"] = [bytes(value) for value in values]
    return stored


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
    assert any(
        record.levelno == logging.DEBUG
        and record.name.startswith("sqlalchemy.pool.")
        and "checked out from pool" in record.getMessage()
        for record in caplog.records
    )
    logs = "\n".join([record.getMessage() for record in caplog.records] + [caplog.text])
    by_table = await _stored(db)
    assert [table for table in WRITTEN if not by_table.get(table)] == []
    stored = "\n".join(by_table.values())
    markers = (password, flow.token)
    assert len(flow.gateway.instructions) == len(flow.gateway.texts)
    assert all(flow.gateway.instructions)
    assert all(
        marker not in instruction for instruction in flow.gateway.instructions for marker in markers
    ), "credential in model instructions"
    shown = "\n".join(text for _, text in flow.gateway.texts)
    assert shown
    assert password not in shown
    assert flow.token not in shown
    for response in flow.responses:
        assert password not in response.text, response.request.url
        for name, value in response.headers.multi_items():
            assert all(marker.lower() not in name.lower() for marker in markers), (
                "credential in response header name"
            )
            assert all(marker not in value for marker in markers), (
                "credential in response header value"
            )
    assert password not in logs
    assert password not in stored
    secret = await db.scalar(select(DataSource.secret).where(DataSource.id == flow.source_id))
    assert secret is not None
    binary_columns = await _binary_columns(db)
    assert secret in binary_columns["connectors.data_sources.secret"]
    encoded = [marker.encode("utf-8") for marker in markers]
    for field, values in binary_columns.items():
        assert all(marker not in value for value in values for marker in encoded), (
            f"credential in bytea column {field}"
        )

    handed_out = [r for r in flow.responses if flow.token in r.text]
    assert [(r.request.method, r.request.url.path) for r in handed_out] == [
        ("POST", "/api/auth/tokens")
    ]
    assert flow.token not in logs
    assert flow.token not in stored
