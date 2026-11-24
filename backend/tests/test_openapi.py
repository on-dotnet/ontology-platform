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
M1_PATHS = {
    "/api/ontologies",
    "/api/ontologies/{id}",
    "/api/ontologies/{id}/elements",
    "/api/ontologies/{id}/elements/{elementId}",
    "/api/ontologies/{id}/graph",
    "/api/ontologies/{id}/export",
    "/api/ontologies/{id}/releases",
    "/api/change-sets",
    "/api/change-sets/{id}",
    "/api/change-sets/{id}/items/{itemId}",
    "/api/change-sets/{id}/decisions",
    "/api/change-sets/{id}/merge",
    "/api/change-sets/{id}/reject",
    "/api/releases/{id}",
    "/api/releases/{id}/export",
    "/api/releases/{id}/activate",
    "/api/documents",
    "/api/documents/{id}",
    "/api/documents/{id}/chunks/{chunkId}",
    "/api/documents/{id}/file",
    "/api/documents/{id}/retry",
    "/api/ai/status",
    "/api/workbench/summary",
}
M2_PATHS = {
    "/api/ontologies/import",
    "/api/ontologies/{id}/import",
    "/api/ontologies/{id}/turtle",
    "/api/ontologies/{id}/edits",
    "/api/ontologies/{id}/elements/{elementId}/impact",
    "/api/settings/platform",
}


def test_openapi_export_documents_the_api(capsys: pytest.CaptureFixture[str]) -> None:
    openapi.main()

    document = json.loads(capsys.readouterr().out)

    assert set(document["paths"]) == M0_PATHS | M1_PATHS | M2_PATHS
    login_responses = document["paths"]["/api/auth/login"]["post"]["responses"]
    assert "application/problem+json" in login_responses["401"]["content"]
    assert "application/problem+json" in login_responses["422"]["content"]
    schemas = document["components"]["schemas"]
    assert "HTTPValidationError" not in schemas
    assert set(schemas["UserInfo"]["properties"]) == {"id", "username", "displayName", "role"}
