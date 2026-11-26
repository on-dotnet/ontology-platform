"""The steel sample as an "external" data source for the M3 tests (spec 003, section 11).

A throwaway database in the same PostgreSQL server per test process, loaded from
fixtures/connectors/steel, with a read-only account and an account that may write (for proving
that the connector still cannot). Role names get a random suffix, since roles are shared by the
whole server and several workspaces run tests at the same time; the database and both roles are
dropped at the end of the session.
"""

import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url

from support import libpq_dsn

STEEL_SQL = Path(__file__).parent / "fixtures" / "connectors" / "steel"
SQL_FILES = ("01-schema.sql", "02-data.sql")


@dataclass(frozen=True, slots=True)
class ExternalSource:
    host: str
    port: int
    database: str
    reader: str
    # Kept out of reprs: failure output and the log scans of batch 6a must not show them.
    reader_password: str = field(repr=False)
    # An account with write privileges: the read-only guarantees must hold even for it.
    writer: str
    writer_password: str = field(repr=False)
    # libpq DSN of a superuser connection to this database, for setting up test objects and
    # for looking at pg_stat_activity. Never handed to the connector.
    admin_dsn: str = field(repr=False)


def _admin_url() -> str:
    url = os.environ.get("OP_TEST_ADMIN_DATABASE_URL")
    if not url:
        pytest.fail("OP_TEST_ADMIN_DATABASE_URL is not set", pytrace=False)
    return url


@pytest.fixture(scope="session")
def external_source() -> Iterator[ExternalSource]:
    admin_url = make_url(_admin_url())
    suffix = secrets.token_hex(6)
    database = f"ontology_ext_{suffix}"
    reader, writer = f"op_ext_reader_{suffix}", f"op_ext_writer_{suffix}"
    reader_password, writer_password = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    server_dsn = libpq_dsn(admin_url.render_as_string(hide_password=False))
    database_dsn = libpq_dsn(
        admin_url.set(database=database).render_as_string(hide_password=False)
    )
    with psycopg.connect(server_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        for role, password in ((reader, reader_password), (writer, writer_password)):
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
    try:
        with psycopg.connect(database_dsn, autocommit=True) as conn:
            for name in SQL_FILES:
                # Without parameters psycopg uses the simple protocol: several statements at once.
                conn.execute((STEEL_SQL / name).read_bytes())
            conn.execute(
                sql.SQL(
                    "GRANT CONNECT ON DATABASE {db} TO {r}, {w};"
                    "GRANT USAGE ON SCHEMA mes TO {r}, {w};"
                    "GRANT SELECT ON ALL TABLES IN SCHEMA mes TO {r};"
                    "GRANT ALL ON ALL TABLES IN SCHEMA mes TO {w};"
                    "GRANT CREATE ON SCHEMA mes TO {w};"
                    "GRANT CREATE ON DATABASE {db} TO {w};"
                    "ALTER ROLE {r} SET default_transaction_read_only = on"
                ).format(
                    db=sql.Identifier(database), r=sql.Identifier(reader), w=sql.Identifier(writer)
                )
            )
        yield ExternalSource(
            host=admin_url.host or "localhost",
            port=admin_url.port or 5432,
            database=database,
            reader=reader,
            reader_password=reader_password,
            writer=writer,
            writer_password=writer_password,
            admin_dsn=database_dsn,
        )
    finally:
        with psycopg.connect(server_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database))
            )
            for role in (reader, writer):
                conn.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))
