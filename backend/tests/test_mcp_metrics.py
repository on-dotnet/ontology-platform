"""Metric evaluation and rule checks through the MCP transport."""

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.mcp import tools
from ontology_platform.modules.query.cursor import encode_key
from query_path_support import qa_steel_fixture  # noqa: F401
from support import csrf_headers
from test_connectors_support import configure
from test_mcp_support import call_tool, new_token, tool_error
from test_metrics_evaluate import inspection_metric_fixture  # noqa: F401
from test_ontology_editing import create, save
from test_ontology_support import publish
from test_qa_demo_import import EX
from test_query_paging import SteelObjects


async def _object_token(client: AsyncClient, db: AsyncSession) -> str:
    token, _ = await new_token(client, db, Role.VIEWER, ["objects:read"])
    client.cookies.clear()
    return token


def _content(result: dict[str, Any]) -> dict[str, Any]:
    assert result["isError"] is False, result
    content: dict[str, Any] = result["structuredContent"]
    return content


async def test_metric_tools_require_objects_read(client: AsyncClient, db: AsyncSession) -> None:
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    client.cookies.clear()
    for name, arguments in (
        ("evaluate_metric", {"ontology": "steel", "metric": "inspectionPassRate"}),
        ("check_rules", {"ontology": "steel", "type": "QualityInspection"}),
    ):
        tool_error(await call_tool(client, token, name, arguments), "auth.insufficient_scope")


async def test_metric_tools_validate_key_and_sample_limits(
    client: AsyncClient, db: AsyncSession
) -> None:
    token = await _object_token(client, db)
    keys = [str(i) for i in range(101)]
    within = {"type": "Inspection", "keys": keys}
    cases: list[tuple[str, dict[str, Any]]] = [
        ("evaluate_metric", {"metric": "inspectionPassRate", "within": within}),
        ("check_rules", within),
        ("check_rules", {"type": "Inspection", "limit": 0}),
        ("check_rules", {"type": "Inspection", "limit": 201}),
    ]
    for name, arguments in cases:
        result = await call_tool(client, token, name, {"ontology": "steel", **arguments})
        tool_error(result, "validation.failed")


async def test_evaluate_metric_resolves_references_and_forwards_within(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects, inspection_metric: UUID
) -> None:
    ontology = qa_steel.ontology
    type_id = qa_steel.ids["QualityInspection"]
    # One passing and one failing inspection, plus absent keys up to the public limit.
    inspection_ids = (11, 341, *range(900, 998))
    keys = [encode_key([f"24010000-0000-4000-8000-{i:012}"]) for i in inspection_ids]
    expected = await client.post(
        f"/api/ontologies/{ontology.id}/metrics/{inspection_metric}/evaluate",
        json={"within": {"typeId": type_id, "keys": keys}},
        headers=csrf_headers(client),
    )
    assert expected.status_code == 200, expected.text
    assert (expected.json()["population"], expected.json()["matched"]) == (2, 1)
    token = await _object_token(client, db)
    for metric, subject in (
        (str(inspection_metric), type_id),
        (ontology.base_iri + "inspectionPassRate", EX + "QualityInspection"),
        ("inspectionPassRate", "QualityInspection"),
    ):
        result = await call_tool(
            client,
            token,
            "evaluate_metric",
            {"ontology": ontology.key, "metric": metric, "within": {"type": subject, "keys": keys}},
        )
        assert _content(result) == expected.json()


async def test_check_rules_forwards_keys_and_sample_limit(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects
) -> None:
    type_id = qa_steel.ids["QualityInspection"]
    keys = [encode_key([f"24010000-0000-4000-8000-00000000034{i}"]) for i in (1, 2)]
    shape = create(
        "constraint",
        "InspectionRequired",
        "检验要求",
        domainRef=type_id,
        rules=[
            {
                "pathRef": qa_steel.ids["passed"],
                "minCount": 1,
                "message": [
                    {"lang": "zh", "text": "须记录结果"},
                    {"lang": "en", "text": "Result required"},
                ],
            }
        ],
    )
    saved = await save(client, qa_steel.ontology, shape)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    assert (await publish(client, qa_steel.ontology)).status_code == 201
    client.headers["Accept-Language"] = "zh;q=0.5, en-US"
    response = await client.post(
        f"/api/ontologies/{qa_steel.ontology.id}/rules/check",
        json={"typeId": type_id, "within": {"typeId": type_id, "keys": keys}, "limit": 1},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    assert "Result required" in {r["message"] for r in response.json()["results"]}
    expected = response.json()
    assert expected["scanned"] == 2
    [failed] = [rule for rule in expected["results"] if rule["violations"]]
    assert failed["violations"] == 2
    [sample] = failed["samples"]
    assert sample["object"]["key"] in keys
    token = await _object_token(client, db)
    args = {"ontology": str(qa_steel.ontology.id), "type": EX + "QualityInspection"}
    result = await call_tool(client, token, "check_rules", {**args, "keys": keys, "limit": 1})
    assert _content(result) == expected
    empty = await call_tool(client, token, "check_rules", {**args, "keys": []})
    assert _content(empty)["scanned"] == 0


async def test_metric_tools_report_lookup_and_scan_errors(
    client: AsyncClient,
    db: AsyncSession,
    qa_steel: SteelObjects,
    inspection_metric: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await _object_token(client, db)
    args = {"ontology": qa_steel.ontology.key}
    long_iri = "urn:" + "x" * 2044
    for ref in ("MissingMetric", qa_steel.ids["QualityInspection"], long_iri):
        result = await call_tool(client, token, "evaluate_metric", {**args, "metric": ref})
        tool_error(result, "metric.not_found")
    missing = await call_tool(client, token, "check_rules", {**args, "type": long_iri})
    tool_error(missing, "element.not_found")
    missing = await call_tool(
        client,
        token,
        "evaluate_metric",
        {**args, "metric": str(inspection_metric), "within": {"type": long_iri, "keys": []}},
    )
    tool_error(missing, "element.not_found")
    configure(monkeypatch, metric_rows_max=1)
    overflow = await call_tool(
        client, token, "evaluate_metric", {**args, "metric": str(inspection_metric)}
    )
    tool_error(overflow, "metric.too_many_rows")
    overflow = await call_tool(client, token, "check_rules", {**args, "type": "QualityInspection"})
    tool_error(overflow, "query.too_many_rows")


async def test_metric_tools_enforce_result_size(
    client: AsyncClient,
    db: AsyncSession,
    qa_steel: SteelObjects,
    inspection_metric: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await _object_token(client, db)
    args = {"ontology": qa_steel.ontology.key, "type": "QualityInspection"}
    full = _content(await call_tool(client, token, "check_rules", args))
    cap = len(tools.text(full).encode()) - 1
    monkeypatch.setattr(tools, "RESULT_LIMIT_BYTES", cap)
    cut = _content(await call_tool(client, token, "check_rules", args))
    assert len(tools.text(cut).encode()) <= cap
    assert cut["truncated"]
    assert cut["notice"]
    assert 0 < len(cut["results"]) < len(full["results"])
    assert cut["results"] == full["results"][: len(cut["results"])]

    monkeypatch.setattr(tools, "RESULT_LIMIT_BYTES", 128)
    metric = {"ontology": qa_steel.ontology.key, "metric": str(inspection_metric)}
    for name, arguments in (("evaluate_metric", metric), ("check_rules", args)):
        tool_error(await call_tool(client, token, name, arguments), "mcp.result_too_large")
