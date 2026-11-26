"""Compatibility with metric rows and the contracts handed to the next M4 batches."""

from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.ai.models import QaQuestionRow
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import (
    binding_proposals,
    bindings,
    compare,
    editing,
    releases,
    schemas,
)
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import (
    ChangeItem,
    ChangeSet,
    Element,
    Ontology,
    Release,
)
from support import csrf_headers
from test_mcp_support import call_tool, new_token
from test_ontology_editing import create, save
from test_ontology_import import upload
from test_ontology_support import (
    add_elements,
    add_ontology,
    change_set_items,
    element,
    merge,
    open_change_set,
    proposal,
    publish,
    sign_in,
)
from test_query_support import assert_problem, make_catalog, publish_bindings, search


@pytest.fixture
async def metric_rows(db: AsyncSession) -> tuple[Ontology, Element, Element]:
    ontology = await add_ontology(db)
    heat = element(ontology, "entity_type", "Heat", "炉次")
    count = element(
        ontology,
        "metric",
        "heatCount",
        "炉次数",
        subject_id=heat.id,
        metric={"aggregate": "count"},
    )
    await add_elements(db, heat, count)
    return ontology, heat, count


async def test_metric_release_and_comparison(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    base = f"/api/ontologies/{ontology.id}"
    detail = await client.get(f"{base}/elements/{metric.id}")
    assert detail.json()["metric"]["aggregate"] == "count"
    response = await publish(client, ontology)
    assert response.status_code == 201, response.text
    assert response.json()["bindingCount"] == 0
    release_id = UUID(response.json()["id"])
    release = await db.get(Release, release_id)
    assert release is not None
    semantic, stored = release.snapshot
    assert stored["metric"] == detail.json()["metric"]
    assert semantic["metric"] is None
    old = {k: v for k, v in semantic.items() if k != "metric"}
    assert schemas.Element.model_validate(old).metric is None
    event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "release.published"))
    assert event is not None
    assert event.detail["bindingCount"] == 0
    released = await bindings.released_ontology(db, ontology.id)
    assert released is not None
    assert [e.id for e in released.elements] == [heat.id]
    assert "metric" not in schemas.ElementCopy.model_fields
    assert [p.element_id for p in releases.release_problems([metric])] == [metric.id]
    metric.metric = {"aggregate": "count", "decimals": 0}
    await db.commit()
    [delta] = (await compare.compare(db, ontology.id, release_id, "working")).changes
    assert delta.element_id == metric.id
    assert [field.field for field in delta.fields] == ["metric"]
    token, _ = await new_token(client, db, Role.VIEWER, ["ontology:read"])
    client.cookies.clear()
    result = await call_tool(client, token, "search_elements", {"ontology": ontology.key})
    assert [item["id"] for item in result["structuredContent"]["items"]] == [
        str(heat.id),
        str(metric.id),
    ]


async def test_metric_working_views_and_proposals(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    impact = await editing.impact(db, ontology.id, heat.id)
    assert [item.element.id for item in impact.cascade] == [metric.id]
    base = f"/api/ontologies/{ontology.id}"
    bound = await client.get(f"{base}/elements", params={"kind": "type_binding"})
    assert bound.json() == []
    [view] = await bindings.binding_views(db, ontology.id, heat.id)
    assert view.type_id == heat.id
    assert view.table is None
    selection = await binding_proposals.first_passing(db, ontology.id, [])
    assert selection.taken == []
    exported = await client.get(f"{base}/export")
    assert exported.status_code == 200
    imported = await upload(client, exported.content, ontology_id=ontology.id)
    assert imported.status_code == 200
    assert imported.json()["changeSetId"] is None
    response = await save(client, ontology, create("entity_type", "Slab", "板坯"), apply=False)
    assert response.status_code == 200, response.text
    change_set = UUID(response.json()["changeSetId"])
    [item] = await change_set_items(client, change_set)
    reviewed = await client.patch(
        f"/api/change-sets/{change_set}/items/{item['id']}",
        json={"decision": "accepted", "edited": {"labelZh": "连铸板坯"}},
        headers=csrf_headers(client),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert (await merge(client, change_set)).json() == {"applied": 1, "skipped": []}
    extracted = await open_change_set(
        db, ontology, [proposal("create", "entity_type", localName="Ladle", labelZh="钢包")]
    )
    [proposed] = await change_set_items(client, extracted)
    assert proposed["proposed"]["localName"] == "Ladle"
    token, _ = await new_token(client, db, Role.EDITOR, ["changes:propose"])
    client.cookies.clear()
    operation = create("entity_type", "Coil", "钢卷") | {"rationale": "工艺记录"}
    result = await call_tool(
        client,
        token,
        "propose_changes",
        {"ontology": ontology.key, "title": "新增钢卷", "operations": [operation]},
    )
    assert result["structuredContent"]["changeSetId"]


async def test_metric_write_gate_and_legacy_merge(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    item = create(
        "metric", "otherCount", "计数", subjectRef=str(heat.id), metric={"aggregate": "count"}
    )
    saved = await save(client, ontology, item, apply=False)
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"] is False
    pending_id = UUID(saved.json()["changeSetId"])
    pending = await db.get(ChangeSet, pending_id)
    assert pending is not None
    assert pending.source == "manual"
    [draft] = await change_set_items(client, pending_id)
    assert (draft["kind"], draft["decision"]) == ("metric", "pending")
    assert await db.scalar(select(Element.id).where(Element.local_name == "otherCount")) is None
    with pytest.raises(ontology_service.InvalidProposalError) as caught:
        await open_change_set(db, ontology, [proposal("delete", "metric", target=metric.id)])
    assert caught.value.code == "changeset.invalid_item"
    change_set = ChangeSet(ontology_id=ontology.id, title="Metrics", source="manual")
    db.add(change_set)
    await db.flush()
    create_item = ChangeItem(
        change_set_id=change_set.id,
        seq=1,
        op="create",
        kind="metric",
        temp_ref="new:otherCount",
        proposed=item["fields"],
        decision="accepted",
    )
    delete_item = ChangeItem(
        change_set_id=change_set.id,
        seq=2,
        op="delete",
        kind="metric",
        target_element_id=metric.id,
        target_revision=1,
        proposed={},
        decision="accepted",
    )
    db.add_all([create_item, delete_item])
    await db.commit()
    result = await merge(client, change_set.id)
    assert result.json() == {"applied": 2, "skipped": []}
    rows = await db.scalars(
        select(Element).where(Element.kind == "metric", Element.status == "active")
    )
    [created] = rows
    await db.refresh(create_item)
    await db.refresh(metric)
    assert created.id == create_item.applied_element_id
    assert (created.local_name, created.subject_id) == ("otherCount", heat.id)
    assert metric.status == "deprecated"


@pytest.mark.parametrize("wrong_kind", [False, True])
async def test_metric_publish_requires_active_subject_type(
    client: AsyncClient,
    db: AsyncSession,
    metric_rows: tuple[Ontology, Element, Element],
    wrong_kind: bool,
) -> None:
    ontology, heat, metric = metric_rows
    if wrong_kind:
        metric.subject_id = metric.id
    else:
        heat.status = "deprecated"
    await db.commit()
    await sign_in(client, db, Role.ADMIN)
    result = await publish(client, ontology)
    assert_problem(result, 422, "release.invalid")
    assert [p["elementId"] for p in result.json()["problems"]] == [str(metric.id)]


async def test_batch_2_zero_hops(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    objects = await search(client, catalog, catalog.coil)
    assert objects.status_code == 200
    result = await client.post(
        f"{catalog.url}/traverse",
        json={"typeId": str(catalog.coil.id), "hops": [], "limit": 1},
        headers=csrf_headers(client),
    )
    assert result.status_code == 200
    [row] = result.json()["items"]
    assert row["via"] == [row["key"]]
    assert row["key"] in {item["key"] for item in objects.json()["items"]}
    assert result.json()["total"] > 1
    assert result.json()["truncated"]


async def test_batch_3_released_metric(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    release = await publish(client, ontology)
    result = await bindings.released_metrics(db, ontology.id)
    assert str(result.release.id) == release.json()["id"]
    [copy] = result.metrics
    assert (copy.id, copy.subject_id, copy.metric.aggregate) == (metric.id, heat.id, "count")


@pytest.mark.xfail(strict=True, reason="Batch 4: a metric shows its subject and binding status")
async def test_batch_4_metric_list(
    client: AsyncClient, db: AsyncSession, metric_rows: tuple[Ontology, Element, Element]
) -> None:
    ontology, heat, metric = metric_rows
    await sign_in(client, db, Role.ADMIN)
    release = await publish(client, ontology)
    response = await client.get(f"/api/ontologies/{ontology.id}/metrics")
    assert response.status_code == 200
    assert response.json()["release"]["id"] == release.json()["id"]
    [item] = response.json()["items"]
    assert (item["metricId"], item["subjectTypeId"], item["bound"]) == (
        str(metric.id),
        str(heat.id),
        False,
    )


@pytest.mark.xfail(strict=True, reason="Batch 5a: submitting a question queues it for the asker")
async def test_batch_5a_queue_question(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    metric_rows: tuple[Ontology, Element, Element],
) -> None:
    ontology, _, _ = metric_rows
    await sign_in(client, db, Role.ADMIN)
    assert (await publish(client, ontology)).status_code == 201
    app.state.settings.openai_api_key = SecretStr("test")
    await sign_in(client, db, Role.VIEWER)
    owner = (await client.get("/api/auth/me")).json()
    response = await client.post(
        f"/api/ontologies/{ontology.id}/qa/questions",
        json={"question": "有几个炉次？"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 202
    question = response.json()
    assert question["askedBy"]["id"] == owner["id"]
    assert (question["status"], question["origin"]) == ("queued", "user")


@pytest.mark.xfail(strict=True, reason="Batch 6: queued questions cannot generate gap proposals")
async def test_batch_6_gap_requires_unanswerable(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    await sign_in(client, db, Role.EDITOR)
    owner = UUID((await client.get("/api/auth/me")).json()["id"])
    row = QaQuestionRow(
        ontology_id=ontology.id,
        asked_by=owner,
        question="有几个炉次？",
        origin="user",
        status="queued",
    )
    db.add(row)
    await db.commit()
    app.state.settings.openai_api_key = SecretStr("test")
    response = await client.post(
        f"/api/qa/questions/{row.id}/gap-proposal", headers=csrf_headers(client)
    )
    assert_problem(response, 409, "qa.not_unanswerable")


@pytest.mark.xfail(strict=True, reason="Batch 7: editors can create and list competency questions")
async def test_batch_7_competency_question(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    await sign_in(client, db, Role.EDITOR)
    url = f"/api/ontologies/{ontology.id}/competency-questions"
    response = await client.post(
        url,
        json={"text": "能查到炉次吗？", "expect": {"kind": "answerable"}},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    [question] = (await client.get(url)).json()["items"]
    assert question["id"] == response.json()["id"]
    assert question["revision"] == 1
    assert question["expect"]["kind"] == "answerable"
