"""Every error is application/problem+json with a stable code."""

from fastapi import FastAPI
from httpx import AsyncClient

from support import PROBLEM_JSON, make_client


async def test_validation_error_lists_issues_without_echoing_input(client: AsyncClient) -> None:
    payload = {"username": "", "password": "typed-secret-value"}

    response = await client.post("/api/auth/login", json=payload)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    problem = response.json()
    assert problem["code"] == "validation.failed"
    assert problem["status"] == 422
    assert {"type", "title", "detail"} <= set(problem)
    issues = [(issue["loc"], issue["type"]) for issue in problem["errors"]]
    assert issues == [(["body", "username"], "string_too_short")]
    assert all(set(issue) == {"loc", "msg", "type"} for issue in problem["errors"])
    assert "typed-secret-value" not in response.text


async def test_missing_body_is_a_validation_error(client: AsyncClient) -> None:
    response = await client.post("/api/auth/login")

    assert response.status_code == 422
    assert response.json()["code"] == "validation.failed"


async def test_unknown_route_is_a_problem(client: AsyncClient) -> None:
    response = await client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "http.not_found"


async def test_unexpected_error_does_not_leak_details(app: FastAPI) -> None:
    async def explode() -> None:
        raise RuntimeError("connection password is hunter2")

    app.add_api_route("/api/test/explode", explode)

    async with make_client(app, raise_app_exceptions=False) as client:
        response = await client.get("/api/test/explode")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["code"] == "internal.error"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
