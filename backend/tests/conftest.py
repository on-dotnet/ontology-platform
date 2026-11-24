"""Fixtures: a throwaway database per test process and a fresh app per test.

Under pytest-xdist every worker process gets its own database from the session fixture below,
so workers share nothing but the PostgreSQL server.
"""

import os
import secrets
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from alembic import command
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import AsyncClient
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.main import create_app
from ontology_platform.modules.identity import service as identity_service
from ontology_platform.settings import Settings
from support import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    TEST_HASHER,
    alembic_config,
    libpq_dsn,
    make_client,
    truncate_tables,
)


@pytest.fixture(scope="session", autouse=True)
def production_hasher() -> Iterator[PasswordHasher]:
    """Hash with TEST_HASHER for the whole run; yields the hasher production uses."""
    production = identity_service._hasher
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(identity_service, "_hasher", TEST_HASHER)
        yield production


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    admin_url = os.environ.get("OP_TEST_ADMIN_DATABASE_URL")
    if not admin_url:
        pytest.fail("OP_TEST_ADMIN_DATABASE_URL is not set", pytrace=False)
    name = f"ontology_test_{secrets.token_hex(6)}"
    with psycopg.connect(libpq_dsn(admin_url), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = make_url(admin_url).set(database=name).render_as_string(hide_password=False)
    try:
        command.upgrade(alembic_config(url), "head")
        yield url
    finally:
        with psycopg.connect(libpq_dsn(admin_url), autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        env="development",
        database_url=database_url,
        admin_username=ADMIN_USERNAME,
        admin_password=SecretStr(ADMIN_PASSWORD),
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    truncate_tables(settings.database_url)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as async_client:
        yield async_client


@pytest.fixture
async def db(app: FastAPI) -> AsyncIterator[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as session:
        yield session
