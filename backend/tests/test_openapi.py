"""The OpenAPI export used by `./dev.ps1 gen-api`."""

import json

import pytest

from ontology_platform import openapi

M0_PATHS = {
    "/api/health",
    "/api/health/ready",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
}


def test_openapi_export_documents_m0_api(capsys: pytest.CaptureFixture[str]) -> None:
    openapi.main()

    document = json.loads(capsys.readouterr().out)

    assert set(document["paths"]) == M0_PATHS
    login_responses = document["paths"]["/api/auth/login"]["post"]["responses"]
    assert "application/problem+json" in login_responses["401"]["content"]
    assert "application/problem+json" in login_responses["422"]["content"]
    schemas = document["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert set(schemas["UserInfo"]["properties"]) == {"id", "username", "displayName", "role"}
