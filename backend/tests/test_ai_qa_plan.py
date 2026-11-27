import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.ai.qa_plan import check_plan
from ontology_platform.modules.ai.qa_prompts import QaAnswerOut, QaPlanOut
from ontology_platform.modules.ai.schemas import QaGaps, QaPlan
from ontology_platform.modules.documents import service as documents
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Datatype, Evidence
from ontology_platform.modules.ontology.qa_context import (
    QaContext,
    active_release_id,
    qa_context,
    qa_documents,
)
from ontology_platform.modules.ontology.schemas import ElementCopy, MetricDefinition, ReleaseRef
from ontology_platform.modules.query.schemas import ObjectProperty, ObjectTypeInfo, ObjectTypeList
from test_ontology_support import add_elements, add_ontology, publish, sign_in
from test_ontology_support import element as stored_element

COIL, INSPECTION, STATUS, PASSED, RELATION, METRIC = (UUID(int=i) for i in range(1, 7))


def element(id_: UUID, kind: str, label: str, **fields: object) -> ElementCopy:
    now = datetime.now(UTC)
    return ElementCopy.model_validate(
        dict.fromkeys(
            ("parentId", "domainId", "rangeId", "inverseId", "datatype", "unit", "subjectId")
        )
        | {
            "id": id_,
            "kind": kind,
            "ontologyId": UUID(int=0),
            "labelZh": label,
            "labelEn": None,
            "definitionZh": None,
            "definitionEn": None,
            "localName": None,
            "iri": None,
            "explicitIri": False,
            "synonyms": [],
            "required": False,
            "multiple": False,
            "autoShape": True,
            "rules": None,
            "flags": [],
            "turtle": None,
            "status": "active",
            "origin": "manual",
            "revision": 1,
            "createdAt": now,
            "updatedAt": now,
            **fields,
        }
    )


@pytest.fixture
def context() -> QaContext:
    grade = bindings.BoundProperty(STATUS, uuid4(), "status", "状态", "string", None, "db_status")
    passed = bindings.BoundProperty(PASSED, uuid4(), "passed", "合格", "boolean", None, "db_pass")
    source = uuid4()
    coil = bindings.BoundType(
        COIL,
        uuid4(),
        "Coil",
        "钢卷",
        None,
        source,
        "private_schema",
        "coil_rows",
        ("pk",),
        (grade,),
    )
    inspection = replace(coil, type_id=INSPECTION, label="检验", properties=(passed,))
    relation = bindings.BoundRelation(
        RELATION,
        uuid4(),
        "inspects",
        "检验对象",
        INSPECTION,
        COIL,
        bindings.ForeignKeyHop("source", ("fk",), ("pk",)),
        None,
        None,
    )
    release = ReleaseRef(id=uuid4(), version=2)
    model = bindings.BoundModel(UUID(int=0), release.id, 2, (coil, inspection), (relation,))
    elements = (
        element(COIL, "entity_type", "钢卷", labelEn="Coil", definitionZh="卷" * 201),
        element(INSPECTION, "entity_type", "检验"),
        element(STATUS, "property", "状态", domainId=COIL, datatype="string"),
        element(PASSED, "property", "合格", domainId=INSPECTION, datatype="boolean"),
        element(RELATION, "relation_type", "检验对象", domainId=INSPECTION, rangeId=COIL),
    )
    ontology = bindings.ReleasedOntology(
        model.ontology_id,
        "steel",
        "钢铁",
        "private description",
        release.id,
        2,
        datetime.now(UTC),
        elements,
        frozenset({COIL, INSPECTION}),
    )
    metric = bindings.MetricCopy(
        METRIC,
        "passRate",
        "合格率",
        None,
        "率" * 201,
        None,
        INSPECTION,
        None,
        MetricDefinition.model_validate(
            {"aggregate": "ratio", "numerator": [{"propertyId": PASSED, "op": "eq", "value": True}]}
        ),
    )
    refs = {"T1": COIL, "T2": INSPECTION, "P1": STATUS, "P2": PASSED, "R1": RELATION, "M1": METRIC}
    return QaContext("", refs, ontology, model, bindings.ReleasedMetrics(release, (metric,)))


def types(context: QaContext) -> ObjectTypeList:
    items = []
    for bound in context.model.types:
        properties = [
            ObjectProperty(
                property_id=prop.property_id,
                label=prop.label,
                datatype=prop.datatype or "string",
                unit=prop.unit,
                ops=["eq", "ne", "in", "isNull", "notNull"],
            )
            for prop in bound.properties
        ]
        items.append(
            ObjectTypeInfo(
                type_id=bound.type_id,
                label=bound.label,
                local_name=bound.local_name,
                iri=None,
                key_columns=list(bound.key_columns),
                problem=None,
                properties=properties,
                relations=[],
            )
        )
    return ObjectTypeList(release=context.metrics.release, items=items)


def plan(**fields: object) -> QaPlanOut:
    return QaPlanOut.model_validate(
        {
            "intent": "objects",
            "start": "T1",
            "filters": [],
            "path": [],
            "target": None,
            "metric": None,
            "missing": [],
            "assumptions": [],
            **fields,
        }
    )


def check(context: QaContext, **fields: object) -> QaPlan | QaGaps:
    return check_plan(plan(**fields), context, context.model, types(context))


def condition(
    prop: str = "P1", op: str = "eq", value: str | None = "库存", values: list[str] | None = None
) -> dict[str, object]:
    return {"property": prop, "op": op, "value": value, "values": values}


def hop(direction: str = "in", *filters: dict[str, object]) -> dict[str, object]:
    return {"relation": "R1", "direction": direction, "filters": list(filters)}


def test_unbound_relation_without_declared_range_needs_binding(context: QaContext) -> None:
    ontology = replace(
        context.ontology,
        elements=tuple(
            e.model_copy(update={"range_id": None}) if e.id == RELATION else e
            for e in context.ontology.elements
        ),
    )
    context = replace(context, ontology=ontology, model=replace(context.model, relations=()))
    result = check(context, start="T2", path=[hop("out")])
    assert isinstance(result, QaGaps)
    assert [binding.type_id for binding in result.bindings] == [INSPECTION]


def test_q5_reports_model_gaps_and_resolves_near(context: QaContext) -> None:
    result = check(
        context,
        intent="unanswerable",
        start=None,
        missing=[
            {"kind": kind, "label_zh": label, "description": "找不到" + label, "near": ["T1"]}
            for kind, label in (("entity_type", "表面缺陷"), ("relation_type", "具有缺陷"))
        ],
    )
    assert isinstance(result, QaGaps)
    assert [(e.kind, e.label_zh, e.description) for e in result.elements] == [
        ("entity_type", "表面缺陷", "找不到表面缺陷"),
        ("relation_type", "具有缺陷", "找不到具有缺陷"),
    ]
    assert [[(n.id, n.label) for n in e.near] for e in result.elements] == [[(COIL, "钢卷")]] * 2
    assert result.bindings == []


@pytest.mark.parametrize(
    ("fields", "kind"),
    [
        ({"start": "T999"}, "entity_type"),
        ({"path": [{**hop(), "relation": "R999"}]}, "relation_type"),
        ({"filters": [condition("P999")]}, "property"),
        ({"intent": "metric", "metric": "M999"}, "metric"),
    ],
)
def test_unknown_ref_precedes_structure(
    context: QaContext, fields: dict[str, object], kind: str
) -> None:
    gaps = check(context, target=100, assumptions=["缺少表面检验"], **fields)
    assert isinstance(gaps, QaGaps)
    assert [(e.kind, e.label_zh) for e in gaps.elements] == [(kind, "缺少表面检验")]
    assert gaps.bindings == []


@pytest.mark.parametrize(
    "fields",
    [
        {"target": -1},
        {"target": 2, "path": [hop()]},
        {"path": [hop()] * 6},
        {"filters": [condition()] * 11},
        {"path": [hop("in", *[condition("P2")] * 11)]},
        {"start": "P1"},
        {"filters": [condition("P2")]},
        {"path": [hop("out")]},
        {"path": [hop("in", condition("P2", value="no"))]},
        {"filters": [condition(op="isNull")]},
        {"filters": [condition(op="in", value="bad")]},
        {"filters": [condition(value=None)]},
        {"filters": [condition(values=["wrong"])]},
        {"intent": "rules", "start": None},
        {"intent": "metric"},
        {"intent": "metric", "metric": "M1", "path": [hop()], "target": 0},
        {"intent": "metric", "metric": "M1"},
        {"intent": "metric", "metric": "M1", "filters": [condition()]},
        {"intent": "unanswerable", "missing": []},
    ],
)
def test_invalid_plan(context: QaContext, fields: dict[str, object]) -> None:
    with pytest.raises(AppError) as caught:
        check(context, **fields)
    assert caught.value.code == "qa.invalid_plan"


def test_opaque_column_uses_operators_from_list_types(context: QaContext) -> None:
    out = plan(filters=[condition(op="contains")])
    catalog = types(context)
    with pytest.raises(AppError) as caught:
        check_plan(out, context, context.model, catalog)
    assert caught.value.code == "qa.invalid_plan"
    catalog.items[0].properties[0].ops.append("contains")
    assert isinstance(check_plan(out, context, context.model, catalog), QaPlan)


def test_inverse_binding_uses_current_type_and_direction(context: QaContext) -> None:
    inverse = element(uuid4(), "relation_type", "受检", domainId=COIL, rangeId=INSPECTION)
    context = replace(
        context,
        refs={**context.refs, "R2": inverse.id},
        ontology=replace(context.ontology, elements=(*context.ontology.elements, inverse)),
        model=replace(
            context.model,
            relations=(replace(context.model.relations[0], inverse_id=inverse.id),),
        ),
    )
    result = check(context, path=[{**hop("out"), "relation": "R2"}])
    assert isinstance(result, QaPlan)
    assert result.hops[0].target_type_id == INSPECTION
    with pytest.raises(AppError) as caught:
        check(context, path=[{**hop("in"), "relation": "R2"}])
    assert caught.value.code == "qa.invalid_plan"


def test_missing_bindings_are_deduplicated_after_structure(context: QaContext) -> None:
    coil, inspection = context.model.types
    unbound = replace(context.model, types=(replace(coil, properties=()),), relations=())
    context = replace(context, model=unbound)
    gaps = check(
        context, filters=[condition()] * 2, path=[hop("in", condition("P2", value="true"))]
    )
    assert isinstance(gaps, QaGaps)
    assert gaps.elements == []
    assert sorted(b.type_id for b in gaps.bindings) == [coil.type_id, inspection.type_id]
    with pytest.raises(AppError) as caught:
        check(context, path=[hop("in", condition("P2", value="no"))])
    assert caught.value.code == "qa.invalid_plan"


def test_metric_checks_bindings_of_aggregate_filters_and_numerator(context: QaContext) -> None:
    metric = context.metrics.metrics[0]
    for definition in [
        {"aggregate": "sum", "propertyId": uuid4()},
        {"aggregate": "count", "filters": [{"propertyId": uuid4(), "op": "isNull"}]},
        {"aggregate": "ratio", "numerator": [{"propertyId": uuid4(), "op": "notNull"}]},
    ]:
        metrics = (replace(metric, metric=MetricDefinition.model_validate(definition)),)
        gaps = check(
            replace(context, metrics=replace(context.metrics, metrics=metrics)),
            intent="metric",
            start=None,
            metric="M1",
        )
        assert isinstance(gaps, QaGaps)
        assert [(b.type_id, b.label) for b in gaps.bindings] == [(INSPECTION, "检验")]


@pytest.mark.parametrize(
    ("datatype", "value", "converted", "bad"),
    [
        ("integer", "+010", 10, "1.5"),
        ("boolean", "false", False, "yes"),
        ("decimal", "123456789.0123456789", "123456789.0123456789", "1_000"),
        ("date", "2024-02-29", "2024-02-29", "2025-02-29"),
        ("dateTime", "2024-02-29T12:00:00+08:00", "2024-02-29T12:00:00+08:00", "2024-02-29"),
    ],
)
def test_filter_conversions(
    context: QaContext, datatype: Datatype, value: str, converted: object, bad: str
) -> None:
    elements = tuple(
        e.model_copy(update={"datatype": datatype}) if e.id == STATUS else e
        for e in context.ontology.elements
    )
    coil, inspection = context.model.types
    properties = (replace(coil.properties[0], datatype=datatype),)
    context = replace(
        context,
        model=replace(context.model, types=(replace(coil, properties=properties), inspection)),
        ontology=replace(context.ontology, elements=elements),
    )
    result = check(context, filters=[condition(value=value)])
    assert isinstance(result, QaPlan)
    assert result.start is not None
    assert result.start.filters[0].value == converted
    if datatype != "boolean":
        result = check(context, filters=[condition(op="in", value=None, values=[value, value])])
        assert isinstance(result, QaPlan)
        assert result.start is not None
        assert result.start.filters[0].value == [converted, converted]
    with pytest.raises(AppError) as caught:
        check(context, filters=[condition(value=bad)])
    assert caught.value.code == "qa.invalid_plan"


def test_checked_plan_uses_position_labels_and_assumptions(context: QaContext) -> None:
    result = check(
        context,
        filters=[condition()],
        path=[hop("in", condition("P2", value="false"))],
        target=0,
        assumptions=["只看现有库存"],
    )
    assert isinstance(result, QaPlan)
    assert result.start is not None
    assert (result.start.type_id, result.target, result.metric_id) == (COIL, 0, None)
    assert result.hops[0].relation_id == RELATION
    assert result.hops[0].target_type_id == INSPECTION
    assert result.hops[0].filters[0].value is False
    assert result.assumptions == ["只看现有库存"]
    assert all(s in result.description for s in ("钢卷", "状态", "库存", "检验对象", "合格"))
    assert "只看现有库存" not in result.description
    end = check(context, intent="metric", path=[hop()], metric="M1")
    assert isinstance(end, QaPlan)
    assert (end.target, end.metric_id) == (1, METRIC)
    global_metric = check(context, intent="metric", start=None, metric="M1")
    assert isinstance(global_metric, QaPlan)
    assert global_metric.start is None


async def test_release_id_sees_publication_with_cached_ontology(
    db: AsyncSession, client: AsyncClient
) -> None:
    with pytest.raises(AppError) as absent:
        await active_release_id(db, uuid4())
    assert (absent.value.status, absent.value.code) == (404, "ontology.not_found")
    ontology = await add_ontology(db)
    await add_elements(db, stored_element(ontology, "entity_type", "Coil", "钢卷"))
    with pytest.raises(AppError) as unpublished:
        await active_release_id(db, ontology.id)
    assert (unpublished.value.status, unpublished.value.code) == (409, "query.no_release")
    await sign_in(client, db, Role.ADMIN)
    release = await publish(client, ontology)
    assert release.status_code == 201
    assert ontology.active_release_id is None
    assert await active_release_id(db, ontology.id) == UUID(release.json()["id"])


async def test_context_limits_and_business_fields(
    context: QaContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    rules = [
        {
            "pathId": STATUS,
            "allowedValues": [{"lexical": f"S{i}"} for i in range(22)],
            "message": [{"lang": "zh", "text": "private document quote"}],
        }
    ]
    shape = element(uuid4(), "constraint", "private shape", domainId=COIL, rules=rules)
    foreign = element(
        uuid4(),
        "constraint",
        "other",
        domainId=INSPECTION,
        rules=[{"pathId": STATUS, "allowedValues": [{"lexical": "foreign value"}]}],
    )
    extras = tuple(element(uuid4(), "entity_type", f"A{i}") for i in range(405))
    elements = (*extras, foreign, shape, *context.ontology.elements)
    ontology = replace(context.ontology, elements=elements)
    for name, value in [
        ("released_ontology", ontology),
        ("bound_model", context.model),
        ("released_metrics", context.metrics),
    ]:
        monkeypatch.setattr(bindings, name, AsyncMock(return_value=value))
    async with AsyncSession() as db:
        actual = await qa_context(db, ontology.ontology_id)
    rows = json.loads(actual.text)
    assert len(rows) == len(actual.refs) == 400
    by_id = {actual.refs[r["ref"]]: r for r in rows}
    assert by_id.keys() >= set(context.refs.values())
    assert by_id[COIL]["definition"] == "卷" * 200
    assert by_id[METRIC]["definition"] == "率" * 200
    assert by_id[STATUS]["allowedValues"] == [f"S{i}" for i in range(20)]
    assert actual.refs[by_id[STATUS]["domain"]] == COIL
    assert actual.refs[by_id[RELATION]["range"]] == COIL
    assert actual.refs[by_id[METRIC]["subject"]] == INSPECTION
    assert by_id[METRIC]["aggregate"] == "ratio"
    assert all(by_id[i]["bound"] for i in (COIL, INSPECTION, STATUS, PASSED, RELATION))
    assert all(not by_id[e.id]["bound"] for e in extras if e.id in by_id)
    private = ("private", "coil_rows", "db_status", "db_pass", "foreign value", '"pk"', '"fk"')
    assert all(s not in actual.text for s in (*private, str(COIL)))


async def test_evidence_respects_release_and_reads_shared_document_once(
    db: AsyncSession, context: QaContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    ontology = await add_ontology(db)
    elements = [stored_element(ontology, "entity_type", name, name) for name in ("A", "B")]
    await add_elements(db, *elements)
    cutoff = context.ontology.published_at
    context = replace(context, ontology=replace(context.ontology, ontology_id=ontology.id))
    doc_id, chunk_id = uuid4(), uuid4()
    for when, quote in [(cutoff, "已发布"), (cutoff + timedelta(seconds=1), "尚未发布")]:
        changes = ChangeSet(
            ontology_id=ontology.id, source="manual", title=quote, status="merged", merged_at=when
        )
        db.add(changes)
        await db.flush()
        for seq, obj in enumerate(elements, start=1):
            item = ChangeItem(
                change_set_id=changes.id,
                seq=seq,
                kind="entity_type",
                op="create",
                proposed={},
                applied_element_id=obj.id,
            )
            db.add(item)
            await db.flush()
            db.add(
                Evidence(change_item_id=item.id, document_id=doc_id, chunk_id=chunk_id, quote=quote)
            )
    await db.flush()
    get = AsyncMock(return_value=SimpleNamespace(ontology_id=ontology.id, filename="资料"))
    chunks = AsyncMock(return_value=[SimpleNamespace(id=chunk_id, seq=7)])
    monkeypatch.setattr(documents, "get", get)
    monkeypatch.setattr(documents, "list_chunks", chunks)
    evidence = await qa_documents(db, context, [obj.id for obj in elements])
    for obj in elements:
        [entry] = evidence[obj.id]
        assert entry == (doc_id, "资料", 7, "已发布")
    get.assert_awaited_once_with(db, doc_id)
    chunks.assert_awaited_once_with(db, doc_id)


def test_gateway_shapes_are_closed_and_fields_required() -> None:
    for model in (QaPlanOut, QaAnswerOut):
        schema = model.model_json_schema()
        for shape in (schema, *schema.get("$defs", {}).values()):
            if shape.get("type") == "object":
                assert shape["additionalProperties"] is False
                assert set(shape["required"]) == set(shape["properties"])
    with pytest.raises(ValidationError):
        QaAnswerOut.model_validate(
            {"answer": "已查到", "cited_keys": [], "counterpoints": [], "sql": ""}
        )
