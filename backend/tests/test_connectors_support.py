"""Helpers shared by the connection-layer tests. This module has no tests of its own."""

import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from pydantic import SecretStr
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors import config
from ontology_platform.modules.connectors.connection import ConnectionParams
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.connectors.secrets import seal
from ontology_platform.settings import Settings

# Just enough of spec 003, 5.5 to cache tables for these tests; the catalog tests check the real
# discovery separately.
_FAMILIES = {
    "bpchar": "string",
    "varchar": "string",
    "text": "string",
    "uuid": "opaque",
    "int2": "integer",
    "int4": "integer",
    "int8": "integer",
    "numeric": "decimal",
    "float4": "decimal",
    "float8": "decimal",
    "bool": "boolean",
    "date": "date",
    "timestamp": "dateTime",
    "timestamptz": "dateTime",
}

_COLUMNS = """
    SELECT a.attname, format_type(a.atttypid, a.atttypmod), t.typtype, t.typname,
           NOT a.attnotnull, a.attnum
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped
    ORDER BY a.attnum
"""


def configure(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> Settings:
    """Settings for the connector in this test only."""
    settings = Settings(**overrides)
    monkeypatch.setattr(config, "_configured", settings)
    return settings


def reader_params(source: ExternalSource, **changes: Any) -> ConnectionParams:
    values: dict[str, Any] = {
        "host": source.host,
        "port": source.port,
        "database": source.database,
        "username": source.reader,
        "password": SecretStr(source.reader_password),
    }
    values.update(changes)
    return ConnectionParams(**values)


def writer_params(source: ExternalSource) -> ConnectionParams:
    return reader_params(source, username=source.writer, password=SecretStr(source.writer_password))


def admin_rows(source: ExternalSource, statement: str, *args: Any) -> list[tuple[Any, ...]]:
    with psycopg.connect(source.admin_dsn, autocommit=True) as conn:
        cursor = conn.execute(statement.encode(), args or None)
        return cursor.fetchall() if cursor.description else []


async def add_source(
    db: AsyncSession,
    source: ExternalSource,
    *,
    writer: bool = False,
    allow_samples: bool = False,
    password: str | None = None,
) -> DataSource:
    """A saved data source on the external database, with sealed credentials."""
    params = writer_params(source) if writer else reader_params(source)
    row = DataSource(
        id=uuid4(),
        name=f"MES {uuid4().hex[:8]}",
        kind="postgresql",
        host=params.host,
        port=params.port,
        database=params.database,
        username=params.username,
        ssl_mode="prefer",
        allow_samples=allow_samples,
    )
    sealed = seal(
        config.current(),
        row.id,
        SecretStr(password) if password is not None else params.password,
    )
    row.secret, row.secret_key_id = sealed.secret, sealed.key_id
    db.add(row)
    await db.commit()
    return row


async def cache_table(
    db: AsyncSession, data_source_id: UUID, source: ExternalSource, schema: str, table: str
) -> None:
    """Put one table of the external database into the catalog cache, as a refresh would."""
    columns = [
        {
            "name": name,
            "type": type_name,
            "family": "opaque" if typtype == "e" else _FAMILIES.get(typname, "other"),
            "nullable": nullable,
            "comment": None,
            "position": position,
        }
        for name, type_name, typtype, typname, nullable, position in admin_rows(
            source, _COLUMNS, schema, table
        )
    ]
    assert columns, f"{schema}.{table} has no columns"
    db.add(
        CatalogTable(
            data_source_id=data_source_id,
            schema_name=schema,
            table_name=table,
            kind="table",
            columns=columns,
            primary_key=None,
        )
    )
    await db.commit()


@contextmanager
def external_statements() -> Iterator[list[tuple[str, Any]]]:
    """Every statement sent on a connector connection while the block runs. Connector engines
    have an empty URL (the connection settings stay in the creator); the platform's do not."""
    seen: list[tuple[str, Any]] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, many: bool
    ) -> None:
        if not conn.engine.url.host:
            seen.append((statement, parameters))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", record)


@pytest.fixture(name="scratch")
def scratch_fixture(external_source: ExternalSource) -> Iterator[str]:
    """A schema of the external database for one test's own objects, readable by the reader and
    dropped afterwards, so that the steel sample in `mes` stays exactly as loaded."""
    schema = f"op_test_{secrets.token_hex(4)}"
    admin_rows(
        external_source,
        f'CREATE SCHEMA "{schema}"; GRANT USAGE ON SCHEMA "{schema}" TO "{external_source.reader}"',
    )
    try:
        yield schema
    finally:
        admin_rows(external_source, f'DROP SCHEMA "{schema}" CASCADE')
