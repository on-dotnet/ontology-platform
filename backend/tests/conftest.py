"""Fixtures: a throwaway database for the whole run and a fresh app per test."""

import os
import secrets
from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from alembic import command
from fastapi import FastAPI
from httpx import AsyncClient
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.main import create_app
from ontology_platform.settings import Settings
from support import ADMIN_PASSWORD, ADMIN_USERNAME, alembic_config, make_client


def libpq_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


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


def truncate_tables(database_url: str) -> None:
    with psycopg.connect(libpq_dsn(database_url), autocommit=True) as conn:
        conn.execute("TRUNCATE identity.sessions, identity.users, audit.events RESTART IDENTITY")


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
