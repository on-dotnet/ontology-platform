"""The OpenAPI export used by `./dev.ps1 gen-api`."""

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform import openapi
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_mcp_support import new_token
from test_ontology_support import add_ontology, sign_in
from test_query_support import assert_problem

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
    "/api/ontologies/{id}/compare",
    "/api/ontologies/{id}/assistant/requests",
    "/api/assistant/requests/{id}",
}


# /mcp is deliberately not in the document (spec 003, 9.2); the optional R2RML export (6c)
# adds its own path when it lands.
M3_PATHS = {
    "/api/auth/tokens",
    "/api/auth/tokens/{id}",
    "/api/data-sources",
    "/api/data-sources/test",
    "/api/data-sources/{id}",
    "/api/data-sources/{id}/archive",
    "/api/data-sources/{id}/test",
    "/api/data-sources/{id}/catalog/refresh",
    "/api/data-sources/{id}/catalog/schemas",
    "/api/data-sources/{id}/catalog/tables",
    "/api/data-sources/{id}/catalog/tables/{schema}/{table}",
    "/api/ontologies/{id}/binding-suggestions",
    "/api/binding-suggestions/{id}",
    "/api/ontologies/{id}/bindings",
    "/api/ontologies/{id}/objects/types",
    "/api/ontologies/{id}/objects/search",
    "/api/ontologies/{id}/objects/{typeId}/{key}",
    "/api/ontologies/{id}/objects/{typeId}/{key}/related",
    "/api/releases/{id}/r2rml",
}

ONTOLOGY = "/api/ontologies/{id}"
CQ = "/competency-questions"
# Expected responses for an authorized caller with a working ontology and no release.
CQ_DETAIL = "/api/competency-questions/{id}"
QA_LIST = f"{ONTOLOGY}/qa/questions"
QA_DETAIL = "/api/qa/questions/{id}"
QA_GAP = f"{QA_DETAIL}/gap-proposal"
M4_IMPLEMENTED: dict[tuple[str, str], tuple[int, str | None]] = {
    ("post", f"{ONTOLOGY}/objects/traverse"): (409, "query.no_release"),
    ("get", f"{ONTOLOGY}/metrics"): (409, "query.no_release"),
    ("post", f"{ONTOLOGY}/metrics/{{metricId}}/evaluate"): (409, "query.no_release"),
    ("post", f"{ONTOLOGY}/rules/check"): (409, "query.no_release"),
    ("post", QA_LIST): (409, "query.no_release"),
    ("get", QA_LIST): (200, None),
    ("get", QA_DETAIL): (200, None),
    ("post", QA_GAP): (409, "qa.not_unanswerable"),
    ("get", ONTOLOGY + CQ): (200, None),
    ("post", ONTOLOGY + CQ): (201, None),
    ("patch", CQ_DETAIL): (200, None),
    ("post", CQ_DETAIL + "/archive"): (200, None),
    ("post", ONTOLOGY + CQ + "/import"): (422, "cq.invalid_import"),
    ("post", CQ_DETAIL + "/check"): (409, "query.no_release"),
    ("post", ONTOLOGY + CQ + "/check"): (409, "query.no_release"),
    ("get", ONTOLOGY + CQ + "/coverage"): (200, None),
}
M4_OPERATIONS = {
    f"{ONTOLOGY}/objects/traverse": {"post": 200},
    f"{ONTOLOGY}/metrics": {"get": 200},
    f"{ONTOLOGY}/metrics/{{metricId}}/evaluate": {"post": 200},
    f"{ONTOLOGY}/rules/check": {"post": 200},
    f"{ONTOLOGY}/qa/questions": {"post": 202, "get": 200},
    "/api/qa/questions/{id}": {"get": 200},
    QA_GAP: {"post": 202},
    ONTOLOGY + CQ: {"get": 200, "post": 201},
    "/api/competency-questions/{id}": {"patch": 200},
    "/api/competency-questions/{id}/archive": {"post": 200},
    ONTOLOGY + CQ + "/import": {"post": 200},
    "/api/competency-questions/{id}/check": {"post": 202},
    ONTOLOGY + CQ + "/check": {"post": 202},
    ONTOLOGY + CQ + "/coverage": {"get": 200},
}


def test_openapi_export_documents_the_api(capsys: pytest.CaptureFixture[str]) -> None:
    openapi.main()

    document = json.loads(capsys.readouterr().out)

    paths = document["paths"]
    assert set(paths) == M0_PATHS | M1_PATHS | M2_PATHS | M3_PATHS | M4_OPERATIONS.keys()
    for path, methods in M4_OPERATIONS.items():
        assert paths[path].keys() == methods.keys()
        for method, success in methods.items():
            responses = paths[path][method]["responses"]
            assert "schema" in responses[str(success)]["content"]["application/json"]
            if CQ in path or path in (QA_LIST, QA_DETAIL, QA_GAP):
                assert "501" not in responses
                assert "application/problem+json" in responses["403"]["content"]
                if CQ in path:
                    for status in ("401", "404", "422"):
                        assert "application/problem+json" in responses[status]["content"]
                    if method == "patch" or path.endswith(("/check", "/archive", "/coverage")):
                        assert "application/problem+json" in responses["409"]["content"]
                if path == QA_GAP:
                    for status in ("200", "202"):
                        assert responses[status]["content"]["application/json"]["schema"] == {
                            "$ref": "#/components/schemas/QaQuestion"
                        }
                    assert "application/problem+json" in responses["409"]["content"]
            else:
                assert "application/problem+json" in responses["501"]["content"]
    media = paths[ONTOLOGY + CQ + "/import"]["post"]["requestBody"]["content"]
    assert {"text/plain", "multipart/form-data"} <= media.keys()
    schemas = document["components"]["schemas"]
    assert "answerKeys" not in schemas["QaQuestion"]["properties"]
    assert set(schemas["MetricDefinition"]["required"]) == {
        "aggregate",
        "propertyId",
        "filters",
        "numerator",
        "decimals",
        "percent",
    }
    assert set(schemas["PathQuery"]["required"]) == {"typeId", "hops"}
    assert schemas["RuleCheckRequest"]["required"] == ["typeId"]
    login_responses = document["paths"]["/api/auth/login"]["post"]["responses"]
    assert "application/problem+json" in login_responses["401"]["content"]
    assert "application/problem+json" in login_responses["422"]["content"]
    assert "HTTPValidationError" not in schemas
    assert set(schemas["UserInfo"]["properties"]) == {"id", "username", "displayName", "role"}


@pytest.mark.parametrize(
    "caller", ["anonymous", "viewer", "editor", "reviewer", "admin", "token", "limited"]
)
async def test_m4_operation_permissions(client: AsyncClient, db: AsyncSession, caller: str) -> None:
    ontology = await add_ontology(db)
    await sign_in(client, db, Role.EDITOR)
    owner = UUID((await client.get("/api/auth/me")).json()["id"])
    question = QaQuestionRow(
        ontology_id=ontology.id,
        asked_by=owner,
        question="有多少炉次？",
        origin="user",
        status="queued",
    )
    db.add(question)
    await db.commit()
    cq_body = {"text": "有多少炉次？", "expect": {"kind": "answerable"}}
    cq_url = f"/api/ontologies/{ontology.id}{CQ}"
    seed = await client.post(cq_url, json=cq_body, headers=csrf_headers(client))
    assert seed.status_code == 201
    cq_id = seed.json()["id"]
    archive_id = cq_id
    headers = {}
    if caller in ("token", "limited"):
        scope = "objects:read" if caller == "token" else "ontology:read"
        token, _ = await new_token(client, db, Role.ADMIN, [scope])
        headers = {"Authorization": f"Bearer {token}"}
        client.cookies.clear()
    elif caller == "anonymous":
        client.cookies.clear()
    else:
        await sign_in(client, db, Role(caller))
        headers = csrf_headers(client)
    type_id = str(uuid4())
    payloads: dict[str, dict[str, Any]] = {
        f"{ONTOLOGY}/objects/traverse": {"typeId": type_id, "hops": []},
        f"{ONTOLOGY}/metrics/{{metricId}}/evaluate": {},
        f"{ONTOLOGY}/rules/check": {"typeId": type_id},
        f"{ONTOLOGY}/qa/questions": {"question": "有多少炉次？"},
        ONTOLOGY + CQ: {"text": "有多少炉次？", "expect": {"kind": "answerable"}},
        "/api/competency-questions/{id}": {"revision": 1, "position": 2},
    }
    for path, methods in M4_OPERATIONS.items():
        detail = path.startswith("/api/qa/questions/")
        target_id = str(question.id if detail else ontology.id)
        if path.startswith(CQ_DETAIL):
            target_id = archive_id if path.endswith("/archive") else cq_id
        url = path.format(id=target_id, metricId=type_id)
        scoped = "/qa/" not in path and CQ not in path
        for method in methods:
            options: dict[str, Any] = {}
            if method != "get" and path in payloads:
                options["json"] = payloads[path]
            if path.endswith("/import"):
                options["files"] = {"file": ("questions.toml", b"question = []", "text/plain")}
            response = await client.request(method, url, headers=headers, **options)
            if caller == "anonymous":
                assert_problem(response, 401, "auth.not_authenticated")
            elif caller in ("token", "limited") and not scoped:
                assert_problem(response, 403, "auth.token_not_allowed")
            elif caller == "limited":
                assert_problem(response, 403, "auth.insufficient_scope")
            elif caller == "viewer" and method != "get" and (CQ in path or detail):
                assert_problem(response, 403, "auth.forbidden")
            elif detail and caller in ("viewer", "reviewer"):
                assert_problem(response, 404, "qa.not_found")
            else:
                status, code = M4_IMPLEMENTED[method, path]
                if code is not None:
                    assert_problem(response, status, code)
                else:
                    assert response.status_code == status, response.text
                    if path == QA_DETAIL:
                        assert response.json()["id"] == str(question.id)
                    elif path == QA_LIST:
                        expected = [str(question.id)] if caller == "editor" else []
                        assert [q["id"] for q in response.json()["items"]] == expected
                    elif path == ONTOLOGY + CQ and method == "post":
                        archive_id = response.json()["id"]
                        assert response.json()["revision"] == 1
                    elif path == ONTOLOGY + CQ:
                        assert [item["id"] for item in response.json()["items"]] == [cq_id]
                    elif path == CQ_DETAIL:
                        assert response.json()["revision"] == 2
                    elif path.endswith("/archive"):
                        assert response.json()["archivedAt"] is not None
                    elif path.endswith("/coverage"):
                        assert response.json() == {
                            "release": None,
                            "items": [
                                {"questionId": cq_id, "status": "never_checked", "elements": []}
                            ],
                        }
    if caller in ("viewer", "editor", "reviewer", "admin"):
        response = await client.get(f"/api/ontologies/{ontology.id}/qa/questions?askedBy=all")
        if caller == "admin":
            assert response.status_code == 200
            assert [q["id"] for q in response.json()["items"]] == [str(question.id)]
        else:
            assert_problem(response, 403, "auth.forbidden")
