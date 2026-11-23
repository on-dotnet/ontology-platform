"""Constants and helpers shared by the tests."""

from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin-test-password"
PROBLEM_JSON = "application/problem+json"
# For direct inspection of the test database; see migrations/env.py on search_path.
PUBLIC_SEARCH_PATH = {"options": "-c search_path=public"}


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
