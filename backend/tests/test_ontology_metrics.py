"""Manual review, publication and external access for metric elements."""

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.mcp import tools
from ontology_platform.modules.ontology import assistant, bindings, releases, schemas, service
from ontology_platform.modules.ontology.models import (
    ChangeItem,
    ChangeSet,
    ChangeSetSource,
    Datatype,
    Element,
    Ontology,
    Release,
)
from ontology_platform.modules.ontology.turtle import export_turtle
from support import csrf_headers, make_client
from test_ai_assistant import operation
from test_mcp_support import call_tool, new_token, tool_error
from test_ontology_bindings_support import admin_id
from test_ontology_changesets import detail_of, patch_item, post_merge
from test_ontology_editing import create, edit, save
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    change_set_items,
    decide,
    element,
    elements_by_name,
    merge,
    open_change_set,
    proposal,
    publish,
    sign_in,
)
from test_query_support import assert_problem


async def test_sum_rejects_a_string_property(client: AsyncClient, db: AsyncSession) -> None:
    await sign_in(client, db, Role.EDITOR)
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    grade = element(ontology, "property", "grade", "钢级", domain_id=heat.id, datatype="string")
    await add_elements(db, heat, grade)

    response = await save(
        client,
        ontology,
        create(
            "metric",
            "gradeSum",
            "钢级之和",
            subjectRef=str(heat.id),
            metric={"aggregate": "sum", "propertyRef": str(grade.id)},
        ),
        apply=False,
    )

    assert_problem(response, 422, "metric.invalid")
    assert await db.scalar(select(ChangeSet.id)) is None


async def _pending(client: AsyncClient, ontology: Ontology, *items: dict[str, Any]) -> UUID:
    response = await save(client, ontology, *items, apply=False)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["merged"] is False
    assert result["merge"] is None
    change_set = UUID(result["changeSetId"])
    detail = await detail_of(client, change_set)
    assert (detail["source"], detail["status"]) == ("manual", "open")
    assert {item["decision"] for item in detail["items"]} == {"pending"}
    return change_set


def _metric(subject: str, definition: dict[str, Any], **fields: Any) -> dict[str, Any]:
    return create(
        "metric", "heatMetric", "炉次指标", subjectRef=subject, metric=definition, **fields
    )


async def test_reviewed_metric_crud_resolves_temp_refs(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    app.state.settings.review_mode = "separate"
    await sign_in(client, db, Role.EDITOR)
    ontology = await add_ontology(db)
    subject = "new:Heat"
    ratio = {
        "aggregate": "ratio",
        "filters": [{"propertyRef": "new:weight", "op": "gt", "value": 0}],
        "numerator": [{"propertyRef": "new:grade", "op": "eq", "value": "A"}],
        "decimals": 3,
        "percent": True,
    }
    created = await _pending(
        client,
        ontology,
        _metric(subject, ratio, unit="%"),
        create("property", "weight", "重量", datatype="decimal", domainRef=subject),
        create("property", "grade", "钢级", datatype="string", domainRef=subject),
        create("entity_type", "Heat", "炉次"),
    )
    item = (await change_set_items(client, created))[0]
    assert item["proposed"]["subjectRef"] == subject
    assert item["proposed"]["metric"] == ratio
    assert await elements_by_name(db, ontology) == {}

    async with make_client(app) as reviewer:
        await sign_in(reviewer, db, Role.REVIEWER)
        unnamed = await patch_item(
            reviewer, created, item["id"], {"edited": {"iri": "urn:heat:metric", "labelZh": ""}}
        )
        assert_problem(unnamed, 422, "metric.invalid")
        explicit_iri = await patch_item(
            reviewer, created, item["id"], {"edited": {"iri": "urn:heat:metric"}}
        )
        assert_problem(explicit_iri, 422, "metric.invalid")
        original = (await change_set_items(reviewer, created))[0]
        assert original["proposed"] == item["proposed"]
        assert (original["edited"], original["decision"]) == (None, "pending")
        assert await accept_and_merge(reviewer, created) == {"applied": 4, "skipped": []}
        rows = await elements_by_name(db, ontology)
        metric = rows["heatMetric"]
        weight, grade = str(rows["weight"].id), str(rows["grade"].id)
        assert (metric.subject_id, metric.unit, metric.origin) == (rows["Heat"].id, "%", "manual")
        assert metric.metric is not None
        assert metric.metric["filters"] == [{"propertyId": weight, "op": "gt", "value": 0}]
        assert metric.metric["numerator"] == [{"propertyId": grade, "op": "eq", "value": "A"}]
        assert metric.metric["decimals"] == 3
        assert metric.metric["percent"] is True

        proposed = {"aggregate": "sum", "propertyRef": weight}
        changed = await _pending(
            client,
            ontology,
            edit("update", metric, metric=proposed, unit="t"),
            create("property", "net", "净重", datatype="decimal", domainRef=str(rows["Heat"].id)),
        )
        update, prop = await change_set_items(reviewer, changed)
        before = update["before"]["metric"]
        assert before["aggregate"] == "ratio"
        assert before["filters"] == [{"propertyRef": weight, "op": "gt", "value": 0}]
        assert before["numerator"] == [{"propertyRef": grade, "op": "eq", "value": "A"}]
        assert update["proposed"]["metric"] == proposed
        bad_fields = {"metric": {"aggregate": "sum", "propertyRef": grade}}
        invalid = await patch_item(
            reviewer,
            changed,
            update["id"],
            {"decision": "accepted", "edited": bad_fields},
        )
        assert_problem(invalid, 422, "metric.invalid")
        unchanged = (await change_set_items(reviewer, changed))[0]
        assert (unchanged["edited"], unchanged["decision"]) == (None, "pending")
        corrected = {"aggregate": "avg", "propertyRef": "new:net", "decimals": 4}
        accepted = await patch_item(
            reviewer,
            changed,
            update["id"],
            {"decision": "accepted", "edited": {"metric": corrected}},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["edited"]["metric"] == corrected
        await db.refresh(metric)
        assert (metric.revision, metric.metric["aggregate"]) == (1, "ratio")
        assert (await decide(reviewer, changed, [prop["id"]], "accepted")).status_code == 200
        assert (await merge(reviewer, changed)).json() == {"applied": 2, "skipped": []}
        rows = await elements_by_name(db, ontology)
        assert (metric.revision, metric.unit) == (2, "t")
        assert metric.metric["aggregate"] == "avg"
        assert metric.metric["propertyId"] == str(rows["net"].id)
        assert "propertyRef" not in metric.metric
        assert metric.metric["decimals"] == 4

        url = f"/api/ontologies/{ontology.id}/elements"
        listed = await client.get(url, params={"kind": "metric"})
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [str(metric.id)]
        assert str(metric.id) in {row["id"] for row in (await client.get(url)).json()}
        deleted = await _pending(client, ontology, edit("delete", metric))
        await db.refresh(metric)
        assert metric.status == "active"
        assert await accept_and_merge(reviewer, deleted) == {"applied": 1, "skipped": []}
        await db.refresh(metric)
        assert (metric.status, metric.revision) == ("deprecated", 3)
        assert (await client.get(url, params={"kind": "metric"})).json() == []


@pytest.fixture
async def heat_property(db: AsyncSession) -> tuple[Ontology, Element, Element]:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    weight = element(ontology, "property", "weight", "重量", domain_id=heat.id, datatype="decimal")
    await add_elements(db, heat, weight)
    return ontology, heat, weight


async def test_invalid_metric_definitions_leave_no_change_set(
    client: AsyncClient, db: AsyncSession, heat_property: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, weight = heat_property
    child = element(ontology, "entity_type", "SpecialHeat", "特殊炉次", parent_id=heat.id)
    await add_elements(db, child)
    await sign_in(client, db, Role.EDITOR)
    ref = str(weight.id)
    condition = {"propertyRef": ref, "op": "gt", "value": 0}
    cases: list[tuple[UUID, dict[str, Any]]] = [
        (child.id, {"aggregate": "avg", "propertyRef": ref}),
        (child.id, {"aggregate": "count", "filters": [condition]}),
        (child.id, {"aggregate": "ratio", "numerator": [condition]}),
        (weight.id, {"aggregate": "count"}),
        (heat.id, {"aggregate": "ratio", "filters": [condition]}),
        (heat.id, {"aggregate": "sum"}),
        (heat.id, {"aggregate": "count", "numerator": [condition]}),
        (heat.id, {"aggregate": "count", "filters": [condition | {"op": "contains"}]}),
    ]
    for subject, definition in cases:
        response = await save(client, ontology, _metric(str(subject), definition), apply=False)
        assert_problem(response, 422, "metric.invalid")
    assert await db.scalar(select(ChangeSet.id)) is None


async def test_manual_metric_rejects_invalid_datetime_operand(
    client: AsyncClient, db: AsyncSession, heat_property: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, _ = heat_property
    sampled = element(
        ontology, "property", "sampledAt", "采样时间", domain_id=heat.id, datatype="dateTime"
    )
    await add_elements(db, sampled)
    await sign_in(client, db, Role.EDITOR)
    condition = {"propertyRef": str(sampled.id), "op": "gt", "value": "abc"}
    item = _metric(str(heat.id), {"aggregate": "count", "filters": [condition]})

    response = await save(client, ontology, item, apply=False)

    assert_problem(response, 422, "metric.invalid")
    assert await db.scalar(select(ChangeSet.id)) is None


@pytest.mark.parametrize(
    ("datatype", "allowed"),
    [
        ("integer", {"sum", "avg", "min", "max"}),
        ("decimal", {"sum", "avg", "min", "max"}),
        ("date", {"min", "max"}),
        ("dateTime", {"min", "max"}),
        ("string", set()),
        ("boolean", set()),
    ],
)
async def test_ordered_aggregates_match_property_datatype(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    datatype: Datatype,
    allowed: set[str],
) -> None:
    ontology, heat, prop = heat_property
    prop.datatype = datatype
    await db.commit()
    await sign_in(client, db, Role.REVIEWER)
    for aggregate in ("sum", "avg", "min", "max"):
        item = create(
            "metric",
            f"{aggregate}Value",
            "聚合值",
            subjectRef=str(heat.id),
            metric={"aggregate": aggregate, "propertyRef": str(prop.id)},
        )
        response = await save(client, ontology, item)
        if aggregate in allowed:
            assert response.status_code == 200, response.text
            assert response.json()["merge"] == {"applied": 1, "skipped": []}
        else:
            assert_problem(response, 422, "metric.invalid")
    if allowed:
        published = await publish(client, ontology)
        assert published.status_code == 201, published.text


async def test_merge_rechecks_datatype_after_review(
    client: AsyncClient, db: AsyncSession, heat_property: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, weight = heat_property
    await sign_in(client, db, Role.ADMIN)
    item = _metric(str(heat.id), {"aggregate": "sum", "propertyRef": str(weight.id)})
    change_set = await _pending(client, ontology, item)
    [pending] = await change_set_items(client, change_set)
    assert (await decide(client, change_set, [pending["id"]], "accepted")).status_code == 200
    other = await save(client, ontology, edit("update", weight, datatype="string"))
    assert other.json()["merge"] == {"applied": 1, "skipped": []}

    result = await merge(client, change_set)

    assert result.status_code == 200
    assert result.json() == {
        "applied": 0,
        "skipped": [{"itemId": pending["id"], "code": "changeset.invalid_item"}],
    }
    assert "heatMetric" not in await elements_by_name(db, ontology)


@pytest.mark.parametrize(
    ("source", "aggregate"),
    [
        ("manual", "median"),
        ("ai_extraction", "count"),
        ("ai_extraction", "median"),
    ],
)
async def test_merge_skips_legacy_metric_and_applies_valid_sibling(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    source: ChangeSetSource,
    aggregate: str,
) -> None:
    ontology, heat, _ = heat_property
    await sign_in(client, db, Role.ADMIN)
    change_set = ChangeSet(ontology_id=ontology.id, title="历史变更集", source=source)
    db.add(change_set)
    await db.flush()
    metric = ChangeItem(
        change_set_id=change_set.id,
        seq=1,
        op="create",
        kind="metric",
        temp_ref="new:heatMetric",
        proposed=_metric(str(heat.id), {"aggregate": aggregate})["fields"],
        decision="accepted",
    )
    sibling = ChangeItem(
        change_set_id=change_set.id,
        seq=2,
        op="create",
        kind="entity_type",
        temp_ref="new:Slab",
        proposed={"localName": "Slab", "labelZh": "板坯"},
        decision="accepted",
    )
    db.add_all([metric, sibling])
    await db.commit()

    result = await client.post(
        f"/api/change-sets/{change_set.id}/merge", headers=csrf_headers(client)
    )

    assert result.status_code == 200, result.text
    assert result.json() == {
        "applied": 1,
        "skipped": [{"itemId": str(metric.id), "code": "changeset.invalid_item"}],
    }
    rows = await elements_by_name(db, ontology)
    assert "heatMetric" not in rows
    await db.refresh(metric)
    await db.refresh(sibling)
    assert metric.applied_element_id is None
    assert sibling.applied_element_id == rows["Slab"].id


async def test_legacy_metric_detail_supplies_token_for_same_name_merge(
    client: AsyncClient, db: AsyncSession, heat_property: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, _ = heat_property
    await sign_in(client, db, Role.REVIEWER)
    definition = "一次完整的冶炼作业。"
    sibling = proposal(
        "create", "entity_type", localName="MeltingHeat", labelZh="炉次", definitionZh=definition
    )
    change_set = await open_change_set(db, ontology, [sibling])
    [valid] = await change_set_items(client, change_set)
    assert (await decide(client, change_set, [valid["id"]], "accepted")).status_code == 200
    original = _metric(str(heat.id), {"aggregate": "median"})["fields"]
    bad = ChangeItem(
        change_set_id=change_set,
        seq=2,
        op="create",
        kind="metric",
        temp_ref="new:heatMetric",
        proposed=original,
        decision="accepted",
    )
    db.add(bad)
    await db.commit()

    shown = await detail_of(client, change_set)

    assert shown["source"] == "ai_extraction"
    token = shown["resolutionToken"]
    assert isinstance(token, str)
    assert token
    items = {item["id"]: item for item in shown["items"]}
    assert items[str(bad.id)]["proposed"] == {**original, "metric": None}
    target = items[valid["id"]]["resolution"]
    assert (target["mode"], target["elementId"]) == ("into", str(heat.id))
    await db.refresh(bad)
    assert bad.proposed == original

    assert_problem(await post_merge(client, change_set, None), 409, "changeset.resolution_changed")
    merged = await post_merge(client, change_set, token)
    assert merged.status_code == 200, merged.text
    assert merged.json() == {
        "applied": 1,
        "skipped": [{"itemId": str(bad.id), "code": "changeset.invalid_item"}],
    }
    rows = await elements_by_name(db, ontology)
    assert set(rows) == {"Heat", "weight"}
    assert (rows["Heat"].id, rows["Heat"].definition_zh) == (heat.id, definition)
    await db.refresh(bad)
    assert bad.applied_element_id is None
    assert bad.proposed == original


def _referencing(slot: str, ref: UUID) -> dict[str, Any]:
    if slot == "aggregate":
        return {"aggregate": "avg", "propertyId": str(ref)}
    condition = {"propertyId": str(ref), "op": "gt", "value": 0}
    return {"aggregate": "ratio" if slot == "numerator" else "count", slot: [condition]}


@pytest.mark.parametrize("slot", ["filters", "numerator", "aggregate"])
@pytest.mark.parametrize("keep_metric", [False, True], ids=["delete-both", "retain-dependent"])
async def test_property_delete_previews_and_respects_metric_cascade(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    slot: str,
    keep_metric: bool,
) -> None:
    ontology, heat, weight = heat_property
    metric = element(
        ontology,
        "metric",
        "heatMetric",
        "炉次指标",
        subject_id=heat.id,
        metric=_referencing(slot, weight.id),
    )
    await add_elements(db, metric)
    await sign_in(client, db, Role.ADMIN)
    impact = await client.get(f"/api/ontologies/{ontology.id}/elements/{weight.id}/impact")
    assert impact.status_code == 200
    assert [(c["op"], c["element"]["id"]) for c in impact.json()["cascade"]] == [
        ("delete", str(metric.id))
    ]
    change_set = await _pending(client, ontology, edit("delete", weight))
    items = await change_set_items(client, change_set)
    assert sorted((i["kind"], i["op"], i["targetElementId"]) for i in items) == [
        ("metric", "delete", str(metric.id)),
        ("property", "delete", str(weight.id)),
    ]
    if keep_metric:
        ids = {i["kind"]: i["id"] for i in items}
        assert (await decide(client, change_set, [ids["metric"]], "rejected")).status_code == 200
        assert (await decide(client, change_set, [ids["property"]], "accepted")).status_code == 200
        result = await merge(client, change_set)
        assert result.status_code == 200
        assert result.json() == {
            "applied": 0,
            "skipped": [{"itemId": ids["property"], "code": "changeset.has_dependents"}],
        }
    else:
        assert await accept_and_merge(client, change_set) == {"applied": 2, "skipped": []}
    await db.refresh(weight)
    await db.refresh(metric)
    expected = ("active", 1) if keep_metric else ("deprecated", 2)
    assert (weight.status, weight.revision) == (metric.status, metric.revision) == expected


async def test_deleting_subject_retires_even_a_metric_without_properties(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    count = element(
        ontology, "metric", "heatCount", "炉次数", subject_id=heat.id, metric={"aggregate": "count"}
    )
    await add_elements(db, heat, count)
    await sign_in(client, db, Role.ADMIN)
    change_set = await _pending(client, ontology, edit("delete", heat))
    items = await change_set_items(client, change_set)
    assert {(i["op"], i["targetElementId"]) for i in items} == {
        ("delete", str(heat.id)),
        ("delete", str(count.id)),
    }
    assert await accept_and_merge(client, change_set) == {"applied": 2, "skipped": []}
    await db.refresh(count)
    await db.refresh(heat)
    assert count.status == heat.status == "deprecated"


@pytest.mark.parametrize("defect", ["missing", "inactive", "wrong-owner", "wrong-kind"])
async def test_release_rejects_invalid_metric_properties(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    defect: str,
) -> None:
    ontology, heat, weight = heat_property
    ref = weight.id
    if defect == "missing":
        ref = uuid4()
    elif defect == "inactive":
        weight.status = "deprecated"
    elif defect == "wrong-owner":
        parent = element(ontology, "entity_type", "Batch", "批次")
        await add_elements(db, parent)
        heat.parent_id = weight.domain_id = parent.id
    else:
        ref = heat.id
    metrics = [
        element(
            ontology,
            "metric",
            f"{slot}Metric",
            "待发布指标",
            subject_id=heat.id,
            metric=_referencing(slot, ref),
        )
        for slot in ("aggregate", "filters", "numerator")
    ]
    await add_elements(db, *metrics)
    await sign_in(client, db, Role.REVIEWER)

    response = await publish(client, ontology)

    assert_problem(response, 422, "release.invalid")
    assert {p["elementId"] for p in response.json()["problems"]} == {str(m.id) for m in metrics}
    assert await db.scalar(select(Release.id)) is None


@pytest.mark.parametrize(
    ("aggregate", "datatype"),
    [("sum", "date"), ("avg", "dateTime"), ("min", "string"), ("max", "boolean")],
)
async def test_release_rejects_incompatible_aggregate_datatypes(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    aggregate: str,
    datatype: Datatype,
) -> None:
    ontology, heat, weight = heat_property
    weight.datatype = datatype
    metric = element(
        ontology,
        "metric",
        "heatMetric",
        "炉次指标",
        subject_id=heat.id,
        metric={"aggregate": aggregate, "propertyId": str(weight.id)},
    )
    await add_elements(db, metric)
    await sign_in(client, db, Role.REVIEWER)

    response = await publish(client, ontology)

    assert_problem(response, 422, "release.invalid")
    assert [p["elementId"] for p in response.json()["problems"]] == [str(metric.id)]
    assert await db.scalar(select(Release.id)) is None


@pytest.mark.parametrize(
    ("values", "valid"),
    [
        pytest.param(["1.25", 2, "abc"], False, id="invalid-last-member"),
        pytest.param(["1.25", 2, "-3.50"], True, id="numeric-strings"),
    ],
)
async def test_release_validates_each_decimal_in_operand(
    client: AsyncClient,
    db: AsyncSession,
    heat_property: tuple[Ontology, Element, Element],
    values: list[str | int],
    valid: bool,
) -> None:
    ontology, heat, weight = heat_property
    condition = {"propertyId": str(weight.id), "op": "in", "value": values}
    metric = element(
        ontology,
        "metric",
        "heatCount",
        "炉次数",
        subject_id=heat.id,
        metric={"aggregate": "count", "filters": [condition]},
    )
    await add_elements(db, metric)
    await sign_in(client, db, Role.REVIEWER)

    result = await publish(client, ontology)

    if valid:
        assert result.status_code == 201, result.text
        released = await bindings.released_metrics(db, ontology.id)
        assert [m.id for m in released.metrics] == [metric.id]
    else:
        assert_problem(result, 422, "release.invalid")
        assert [p["elementId"] for p in result.json()["problems"]] == [str(metric.id)]
        assert await db.scalar(select(Release.id)) is None


def test_assistant_model_output_rejects_metric_kind() -> None:
    with pytest.raises(ValidationError) as invalid:
        operation(
            "create", "metric", temp_ref="new:heatCount", local_name="heatCount", label_zh="炉次数"
        )
    [error] = invalid.value.errors()
    assert (error["loc"], error["type"]) == (("kind",), "literal_error")


@pytest.mark.parametrize("source", ["ai_assistant", "ai_qa"], ids=["assistant", "qa-gap"])
async def test_assistant_and_gap_cannot_propose_a_metric(
    db: AsyncSession, heat_property: tuple[Ontology, Element, Element], source: ChangeSetSource
) -> None:
    ontology, heat, weight = heat_property
    item = proposal(
        "create",
        "metric",
        temp_ref="new:heatWeight",
        localName="heatWeight",
        labelZh="炉次总重",
        subjectRef=str(heat.id),
        metric={"aggregate": "sum", "propertyRef": str(weight.id)},
    )
    actor = await admin_id(db)
    with pytest.raises(service.InvalidProposalError) as refused:
        await assistant.propose(
            db,
            ontology.id,
            message="添加炉次总重指标",
            created_by=actor,
            items=[item],
            source=source,
        )
    assert (refused.value.status, refused.value.code) == (422, "changeset.invalid_item")
    assert await db.scalar(select(ChangeSet.id)) is None
    assert await db.scalar(select(Element.id).where(Element.kind == "metric")) is None


@pytest.fixture
async def metric_rows(
    db: AsyncSession, heat_property: tuple[Ontology, Element, Element]
) -> tuple[Ontology, Element, Element]:
    ontology, heat, _ = heat_property
    count = element(
        ontology,
        "metric",
        "heatCount",
        "炉次数",
        subject_id=heat.id,
        metric={"aggregate": "count"},
    )
    await add_elements(db, count)
    return ontology, heat, count


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("search_elements", {"kinds": ["metric"], "query": "published alias"}),
        ("get_element", {"id": "heatCount"}),
        ("get_element", {"iri": "urn:example:heat-count"}),
    ],
)
async def test_mcp_reads_metric_from_same_release(
    client: AsyncClient,
    db: AsyncSession,
    metric_rows: tuple[Ontology, Element, Element],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    arguments: dict[str, Any],
) -> None:
    ontology, _, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    first = await publish(client, ontology)
    assert first.status_code == 201
    metric.iri = "urn:example:heat-count"
    metric.label_en = "Published count"
    metric.synonyms = [{"lang": "en", "text": "Published alias"}]
    metric.metric = {"aggregate": "count", "decimals": 0}
    await db.commit()
    second = await publish(client, ontology)
    assert second.status_code == 201
    release = await db.get(Release, UUID(first.json()["id"]))
    assert release is not None
    first_id, actor = release.id, release.created_by
    assert actor is not None
    read = bindings.released_ontology

    async def switch_after_read(
        session: AsyncSession, reference: UUID | str
    ) -> bindings.ReleasedOntology | None:
        chosen = await read(session, reference)
        await releases.activate_release(session, first_id, actor=actor, ip=None)
        return chosen

    monkeypatch.setattr(bindings, "released_ontology", switch_after_read)
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    client.cookies.clear()
    result = await call_tool(client, token, name, {"ontology": ontology.key, **arguments})
    content = result["structuredContent"]
    assert content["release"] == {"id": second.json()["id"], "version": 2}
    if name == "search_elements":
        [item] = content["items"]
    else:
        item = content
        assert item["metric"]["decimals"] == 0
    assert (item["kind"], item["id"], item["labelEn"], item["iri"]) == (
        "metric",
        str(metric.id),
        "Published count",
        "urn:example:heat-count",
    )


@pytest.mark.parametrize("name", ["get_element", "search_elements"])
async def test_mcp_metric_result_size_is_limited(
    client: AsyncClient,
    db: AsyncSession,
    metric_rows: tuple[Ontology, Element, Element],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    ontology, _, metric = metric_rows
    metric.definition_en = "a" * 2000
    await db.commit()
    await sign_in(client, db, Role.ADMIN)
    assert (await publish(client, ontology)).status_code == 201
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    client.cookies.clear()
    monkeypatch.setattr(tools, "RESULT_LIMIT_BYTES", 1024)
    arguments = {"id": str(metric.id)} if name == "get_element" else {"kinds": ["metric"]}
    result = await call_tool(client, token, name, {"ontology": ontology.key, **arguments})
    tool_error(result, "mcp.result_too_large")


async def test_released_metrics_follow_activation(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    with pytest.raises(AppError) as caught:
        await bindings.released_metrics(db, ontology.id)
    assert caught.value.code == "query.no_release"
    release = await publish(client, ontology)
    assert release.status_code == 201
    result = await bindings.released_metrics(db, ontology.id)
    assert str(result.release.id) == release.json()["id"]
    [copy] = result.metrics
    assert (copy.id, copy.subject_id, copy.metric.aggregate) == (metric.id, heat.id, "count")
    assert result.release.version == release.json()["version"] == 1
    prop = (await elements_by_name(db, ontology))["weight"]
    definition = {
        "aggregate": "avg",
        "propertyId": str(prop.id),
        "filters": [{"propertyId": str(prop.id), "op": "gt", "value": 0}],
        "numerator": [],
        "decimals": 3,
        "percent": False,
    }
    metric.metric = definition
    metric.label_zh, metric.label_en = "平均重量", "Average weight"
    metric.definition_zh, metric.definition_en, metric.unit = "平均炉重", "Mean heat weight", "t"
    await db.commit()
    assert await bindings.released_metrics(db, ontology.id) == result
    second = await publish(client, ontology)
    latest = await bindings.released_metrics(db, ontology.id)
    assert str(latest.release.id) == second.json()["id"]
    assert latest.release.version == 2
    [updated] = latest.metrics
    assert (updated.id, updated.subject_id, updated.local_name) == (metric.id, heat.id, "heatCount")
    assert (updated.label_zh, updated.label_en) == ("平均重量", "Average weight")
    assert (updated.definition_zh, updated.definition_en, updated.unit) == (
        "平均炉重",
        "Mean heat weight",
        "t",
    )
    assert updated.metric.model_dump(mode="json", by_alias=True) == definition
    activated = await client.post(
        f"/api/releases/{result.release.id}/activate", headers=csrf_headers(client)
    )
    assert activated.status_code == 200
    assert await bindings.released_metrics(db, ontology.id) == result

    working = await client.get(f"/api/ontologies/{ontology.id}/export")
    assert working.status_code == 200
    assert "heatCount" not in working.text
    turtle = await client.get(f"/api/releases/{result.release.id}/export")
    assert turtle.status_code == 200
    assert "Heat" in turtle.text
    assert "heatCount" not in turtle.text
    snapshot = await db.get(Release, result.release.id)
    assert snapshot is not None
    rendered = export_turtle(
        service.header_of(ontology),
        [schemas.Element.model_validate(row) for row in snapshot.snapshot],
        version=snapshot.version,
        created=snapshot.created_at,
    )
    assert rendered == snapshot.turtle


async def test_mcp_cannot_propose_a_metric(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, _, metric = metric_rows
    token, _ = await new_token(client, db, Role.EDITOR, ["changes:propose"])
    client.cookies.clear()
    rejected = await call_tool(
        client,
        token,
        "propose_changes",
        {
            "ontology": ontology.key,
            "title": "删除指标",
            "operations": [
                {"op": "delete", "kind": "metric", "target": str(metric.id), "rationale": "停用"}
            ],
        },
    )
    tool_error(rejected, "validation.failed")
    assert await db.scalar(select(ChangeSet.id)) is None
