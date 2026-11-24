"""Constants and helpers shared by the tests."""

import psycopg
from alembic.config import Config
from argon2 import PasswordHasher, Type
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from psycopg import sql
from sqlalchemy.engine import make_url

from ontology_platform import models  # noqa: F401  (registers every module's tables)
from ontology_platform.db import Base

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-test-password"
PROBLEM_JSON = "application/problem+json"
# For direct inspection of the test database; see migrations/env.py on search_path.
PUBLIC_SEARCH_PATH = {"options": "-c search_path=public"}
# Still Argon2id, but with the smallest cost: the production profile spends about 80 ms and
# 64 MiB per hash, and every app start hashes the admin password. See conftest.py.
TEST_HASHER = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1, type=Type.ID)


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", "ontology_platform:migrations")
    config.attributes["database_url"] = database_url
    return config


def make_client(app: FastAPI, *, raise_app_exceptions: bool = True) -> AsyncClient:
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def login(
    client: AsyncClient,
    username: str = ADMIN_USERNAME,
    password: str = ADMIN_PASSWORD,
) -> Response:
    return await client.post("/api/auth/login", json={"username": username, "password": password})


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["op_csrf"]}


def cookie_attributes(response: Response) -> dict[str, set[str]]:
    """Cookie name -> lower-cased attributes (such as "httponly", "path=/") from Set-Cookie."""
    cookies: dict[str, set[str]] = {}
    for header in response.headers.get_list("set-cookie"):
        name_value, *attributes = (part.strip() for part in header.split(";"))
        cookies[name_value.split("=", 1)[0]] = {attribute.lower() for attribute in attributes}
    return cookies


def libpq_dsn(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def truncate_tables(database_url: str) -> None:
    # Every table registered by the application's modules, so new modules need no change here.
    tables = sorted(Base.metadata.tables)
    if not tables:
        return
    identifiers = sql.SQL(", ").join(sql.Identifier(*name.split(".", 1)) for name in tables)
    with psycopg.connect(libpq_dsn(database_url), autocommit=True) as conn:
        conn.execute(sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(identifiers))
