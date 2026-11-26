"""Metric reads against the published steel fixtures."""

import tomllib
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.metrics import service
from ontology_platform.modules.metrics.aggregate import _aggregate
from ontology_platform.modules.query import cursor, scan, schemas
from ontology_platform.modules.query import service as query
from query_path_support import demo_path, qa_steel_fixture  # noqa: F401
from support import csrf_headers
from test_connectors_support import configure
from test_ontology_editing import create, save
from test_ontology_support import elements_by_name, publish
from test_qa_demo_import import EX, FIXTURES
from test_query_paging import SteelObjects, steel_objects_fixture  # noqa: F401
from test_query_support import assert_problem


@pytest.fixture(name="inspection_metric")
async def inspection_metric_fixture(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects
) -> UUID:
    [item] = tomllib.loads((FIXTURES / "metrics.toml").read_text("utf-8"))["items"]
    fields = item["fields"]
    fields["subjectRef"] = qa_steel.ids[fields["subjectRef"].removeprefix(EX)]
    for condition in fields["metric"]["filters"] + fields["metric"]["numerator"]:
        condition["propertyRef"] = qa_steel.ids[condition["propertyRef"].removeprefix(EX)]
    item["tempRef"] = f"new:{fields['localName']}"
    saved = await save(client, qa_steel.ontology, item)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    release = await publish(client, qa_steel.ontology)
    assert release.status_code == 201, release.text
    return (await elements_by_name(db, qa_steel.ontology))[fields["localName"]].id


async def test_inspection_ratio_population_and_within(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects, inspection_metric: UUID
) -> None:
    ontology_id = qa_steel.ontology.id
    base = f"/api/ontologies/{ontology_id}/metrics"
    response = await client.get(base)
    assert response.status_code == 200
    [metric] = response.json()["items"]
    assert metric == {
        "metricId": str(inspection_metric),
        "label": "检验合格率",
        "definition": None,
        "unit": None,
        "subjectTypeId": qa_steel.ids["QualityInspection"],
        "subjectTypeLabel": "质量检验",
        "aggregate": "ratio",
        "bound": True,
    }
    url = f"{base}/{inspection_metric}/evaluate"
    all_rows = await client.post(url, json={}, headers=csrf_headers(client))
    assert all_rows.status_code == 200, all_rows.text
    result = all_rows.json()
    assert (result["population"], result["matched"], result["nulls"]) == (43, 40, 0)
    assert result["release"] == response.json()["release"]
    keys = await query.traverse_keys(db, ontology_id, demo_path(qa_steel))
    assert len(keys.keys) == 39
    response = await client.post(
        url,
        json={"within": {"typeId": str(keys.type_id), "keys": keys.keys}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["population"], result["matched"], result["display"]) == (39, 36, "92.3%")
    assert Decimal(result["value"]) == Decimal(36) / 39
    assert result["reason"] is None
    assert [step["rows"] for step in result["steps"]] == [39, 36]


async def test_empty_population(
    db: AsyncSession, qa_steel: SteelObjects, inspection_metric: UUID
) -> None:
    within = schemas.KeySet(UUID(qa_steel.ids["QualityInspection"]), ())
    result = await service.evaluate(db, qa_steel.ontology.id, inspection_metric, within=within)
    assert (result.population, result.matched, result.nulls) == (0, 0, 0)
    assert (result.value, result.display, result.reason) == (None, None, "empty_population")


async def test_ratio_only_counts_keys_in_its_original_population(
    db: AsyncSession,
    qa_steel: SteelObjects,
    inspection_metric: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ontology = qa_steel.ontology.id
    subject = UUID(qa_steel.ids["QualityInspection"])
    # A passing inspection appears between the population read and the numerator read.
    reads = []
    for suffix in ("341", "011"):
        key = cursor.encode_key([f"24010000-0000-4000-8000-000000000{suffix}"])
        reads.append(
            await query.scan(
                db,
                ontology,
                subject,
                [],
                within=schemas.KeySet(subject, (key,)),
                property_ids=[],
                max_rows=1,
            )
        )
    monkeypatch.setattr(query, "scan", AsyncMock(side_effect=reads))
    result = await service.evaluate(db, ontology, inspection_metric)
    assert (result.population, result.matched, result.display) == (1, 0, "0.0%")


async def test_metric_row_limit_and_shared_statement_budget(
    client: AsyncClient,
    qa_steel: SteelObjects,
    inspection_metric: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"/api/ontologies/{qa_steel.ontology.id}/metrics/{inspection_metric}/evaluate"
    configure(monkeypatch, metric_rows_max=42)
    assert_problem(
        await client.post(url, json={}, headers=csrf_headers(client)), 422, "metric.too_many_rows"
    )
    configure(monkeypatch, metric_rows_max=43, query_max_rows=100)
    monkeypatch.setattr(scan, "STATEMENTS_MAX", 1)
    assert_problem(
        await client.post(url, json={}, headers=csrf_headers(client)), 422, "qa.too_many_queries"
    )


async def test_filtered_numeric_aggregates_skip_nulls(
    client: AsyncClient, db: AsyncSession, steel_objects: SteelObjects
) -> None:
    steel = steel_objects
    expected = {"count": "4", "sum": "4971", "avg": "1657", "min": "1650", "max": "1664"}
    filters = [{"propertyRef": steel.ids["site"], "op": "eq", "value": "S1"}]
    items = [
        create(
            "metric",
            f"temp{aggregate}",
            aggregate,
            subjectRef=steel.ids["Heat"],
            metric={
                "aggregate": aggregate,
                "filters": filters,
                **({"propertyRef": steel.ids["temp"]} if aggregate != "count" else {}),
            },
        )
        for aggregate in expected
    ]
    saved = await save(client, steel.ontology, *items)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    assert (await publish(client, steel.ontology)).status_code == 201
    within = schemas.KeySet(
        UUID(steel.ids["Heat"]),
        tuple(cursor.encode_key([f"H2401{i:03}"]) for i in (1, 2, 3, 4, 11)),
    )
    elements = await elements_by_name(db, steel.ontology)
    for aggregate, value in expected.items():
        result = await service.evaluate(
            db, steel.ontology.id, elements[f"temp{aggregate}"].id, within=within
        )
        assert result.population == 4
        assert result.nulls == (0 if aggregate == "count" else 1)
        assert result.matched is None
        assert result.value is not None
        assert Decimal(result.value) == Decimal(value)
        assert result.reason is None
    only_null = schemas.KeySet(within.type_id, (cursor.encode_key(["H2401004"]),))
    result = await service.evaluate(db, steel.ontology.id, elements["tempavg"].id, within=only_null)
    assert (result.population, result.nulls, result.value, result.display) == (1, 1, None, None)
    assert result.reason is None


async def test_ratio_combines_population_and_numerator_filters(
    client: AsyncClient, db: AsyncSession, qa_steel: SteelObjects
) -> None:
    ids = qa_steel.ids
    metric = create(
        "metric",
        "failedRate",
        "低屈服强度检验合格率",
        subjectRef=ids["QualityInspection"],
        metric={
            "aggregate": "ratio",
            "filters": [{"propertyRef": ids["yieldStrength"], "op": "lt", "value": 235}],
            "numerator": [{"propertyRef": ids["passed"], "op": "eq", "value": True}],
        },
    )
    saved = await save(client, qa_steel.ontology, metric)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    assert (await publish(client, qa_steel.ontology)).status_code == 201
    metric_id = (await elements_by_name(db, qa_steel.ontology))["failedRate"].id
    result = await service.evaluate(db, qa_steel.ontology.id, metric_id)
    assert (result.population, result.matched, result.display) == (3, 0, "0.00")
    assert result.reason is None


async def test_metric_bound_requires_all_referenced_properties(
    client: AsyncClient, qa_steel: SteelObjects
) -> None:
    subject = qa_steel.ids["QualityInspection"]
    saved = await save(
        client,
        qa_steel.ontology,
        create("property", "reading", "读数", datatype="decimal", domainRef=subject),
        create(
            "metric",
            "readingCount",
            "读数计数",
            subjectRef=subject,
            metric={
                "aggregate": "count",
                "filters": [{"propertyRef": "new:reading", "op": "notNull"}],
            },
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    base = f"/api/ontologies/{qa_steel.ontology.id}/metrics"
    assert (await client.get(base)).json()["items"] == []
    assert (await publish(client, qa_steel.ontology)).status_code == 201
    [item] = (await client.get(base)).json()["items"]
    assert item["bound"] is False
    response = await client.post(
        f"{base}/{item['metricId']}/evaluate", json={}, headers=csrf_headers(client)
    )
    assert_problem(response, 409, "query.type_not_bound")


def test_decimal_precision_and_temporal_extrema() -> None:
    assert _aggregate("sum", "decimal", ["10000000000000000000000000000", "0.01"]) == Decimal(
        "10000000000000000000000000000.01"
    )
    assert _aggregate("min", "date", ["2024-03-01", "2024-02-29"]) == "2024-02-29"
    timestamps = ["2024-03-01T01:00:00+02:00", "2024-03-01T00:30:00"]
    assert _aggregate("max", "dateTime", timestamps) == "2024-03-01T00:30:00+00:00"
