import asyncio
import sys
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.errors import AppError
from ontology_platform.modules.metrics import service as metrics
from ontology_platform.modules.metrics.schemas import RuleReport
from ontology_platform.modules.ontology import bindings
from ontology_platform.modules.ontology.models import Datatype
from ontology_platform.modules.ontology.schemas import ElementCopy
from ontology_platform.modules.query import cursor, schemas
from ontology_platform.modules.query import scan as scanning
from ontology_platform.modules.query import service as query
from query_path_support import qa_steel_fixture  # noqa: F401
from test_connectors_support import configure
from test_query_paging import SteelObjects


async def test_demo_inspection_rules_and_within(db: AsyncSession, qa_steel: SteelObjects) -> None:
    ids = qa_steel.ids
    subject = UUID(ids["QualityInspection"])
    ontology = qa_steel.ontology.id
    report = await metrics.check_rules(db, ontology, subject, limit=2)
    assert report.release.model_dump(mode="json") == qa_steel.release
    assert (report.type_id, report.scanned, report.checked_rules, report.unchecked_rules) == (
        subject,
        43,
        4,
        0,
    )
    [step] = report.steps
    assert (step.type_id, step.rows, step.truncated) == (subject, 43, False)
    by_shape = {str(row.constraint_id): row for row in report.results}
    assert {key: row.violations for key, row in by_shape.items()} == {
        ids["YieldStrengthShape"]: 3,
        ids["TensileStrengthShape"]: 0,
        ids["ElongationShape"]: 0,
        ids["ImpactEnergyShape"]: 0,
    }
    result = by_shape[ids["YieldStrengthShape"]]
    assert result.message == "资料 04 第 2 节：ReH ≥ 235 MPa。"
    assert str(result.property_id) == ids["yieldStrength"]
    assert result.checks == ["minInclusive"]
    assert [sample.object.source.key[0].value for sample in result.samples] == [
        "24010000-0000-4000-8000-000000000341",
        "24010000-0000-4000-8000-000000000342",
    ]
    assert [(f.check, str(f.expected), f.actual) for s in result.samples for f in s.failed] == [
        ("minInclusive", "235", 229),
        ("minInclusive", "235", 230),
    ]
    passing = cursor.encode_key(["24010000-0000-4000-8000-000000000011"])
    within = schemas.KeySet(subject, (passing, result.samples[1].object.key))
    limited = await metrics.check_rules(db, ontology, subject, within=within)
    assert limited.scanned == 2
    assert sum(row.violations for row in limited.results) == 1
    assert [s.object.key for r in limited.results for s in r.samples] == [within.keys[1]]


async def test_rules_row_cap_applies_before_sampling(
    db: AsyncSession, qa_steel: SteelObjects, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(monkeypatch, metric_rows_max=42)
    with pytest.raises(AppError) as caught:
        await metrics.check_rules(
            db, qa_steel.ontology.id, UUID(qa_steel.ids["QualityInspection"]), limit=1
        )
    assert (caught.value.status, caught.value.code) == (422, "query.too_many_rows")


_TYPE, _PROPERTY, _PARENT, _UNBOUND, _RELATION = (UUID(int=n) for n in range(1, 6))
_XSD = "http://www.w3.org/2001/XMLSchema#"


async def _report(
    monkeypatch: pytest.MonkeyPatch,
    datatype: Datatype,
    values: list[schemas.Scalar | None],
    *rules: dict[str, object],
    language: str = "zh",
) -> RuleReport:
    ontology, release = uuid4(), uuid4()
    now = datetime.now(UTC)

    def element(kind: str, name: str, **fields: object) -> ElementCopy:
        return ElementCopy.model_validate(
            {
                "id": uuid4(),
                "ontologyId": ontology,
                "kind": kind,
                "localName": name,
                "iri": None,
                "explicitIri": False,
                "labelZh": name,
                "labelEn": None,
                "definitionZh": None,
                "definitionEn": None,
                "synonyms": [],
                "parentId": None,
                "domainId": None,
                "rangeId": None,
                "inverseId": None,
                "datatype": None,
                "unit": None,
                "required": False,
                "multiple": False,
                "autoShape": True,
                "rules": None,
                "turtle": None,
                "subjectId": None,
                "flags": [],
                "status": "active",
                "origin": "manual",
                "revision": 1,
                "createdAt": now,
                "updatedAt": now,
                **fields,
            }
        )

    parent_rule = [{"pathId": _PROPERTY, "minCount": 1}]
    elements = (
        element("entity_type", "Parent", id=_PARENT),
        element("entity_type", "Child", id=_TYPE, parentId=_PARENT),
        element("property", "Reading", id=_PROPERTY, datatype=datatype),
        element("property", "Unbound", id=_UNBOUND, datatype="string"),
        element("relation_type", "Relation", id=_RELATION),
        element("constraint", "Parent shape", domainId=_PARENT, rules=parent_rule),
        element("constraint", "Old shape", domainId=_TYPE, status="deprecated", rules=parent_rule),
        element(
            "constraint",
            "Child shape",
            domainId=_TYPE,
            rules=[{"pathId": _PROPERTY, **rule} for rule in rules],
        ),
    )
    snapshot = bindings.ReleasedOntology(
        ontology, "demo", "Demo", None, release, 2, now, elements, frozenset({_TYPE})
    )
    prop = bindings.BoundProperty(_PROPERTY, uuid4(), "reading", "Reading", datatype, None, "v")
    table = bindings.BoundType(
        _TYPE, uuid4(), "Child", "Child", None, uuid4(), "demo", "child", ("id",), (prop,)
    )
    model = bindings.BoundModel(ontology, release, 2, (table,), ())
    projected = tuple(
        schemas.ObjectRow(
            type_id=_TYPE,
            key=str(i),
            values={_PROPERTY: value},
            truncated=[],
            source=schemas.ObjectSource(
                data_source_id=table.data_source_id,
                data_source_name="Demo",
                schema="demo",
                table="child",
                key=[schemas.SourceKey(column="id", value=str(i))],
            ),
        )
        for i, value in enumerate(values)
    )
    scanned = schemas.ScanResult(schemas.ReleaseRef(id=release, version=2), projected, ())
    monkeypatch.setattr(bindings, "released_ontology", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(bindings, "bound_model", AsyncMock(return_value=model))
    scan = AsyncMock(return_value=scanned)
    monkeypatch.setattr(query, "scan", scan)
    report = await metrics.check_rules(Mock(spec=AsyncSession), ontology, _TYPE, language=language)
    if scan.await_count:
        scan.assert_awaited_once()
        assert scan.await_args is not None
        assert set(scan.await_args.kwargs["property_ids"]) == {_PROPERTY}
    return report


async def test_rules_skip_parent_and_deprecated_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    report = await _report(monkeypatch, "string", [None])
    assert (report.results, report.checked_rules, report.unchecked_rules) == ([], 0, 0)


@pytest.mark.parametrize(
    ("datatype", "literal_type", "boundary", "below", "equal", "above"),
    [
        ("integer", _XSD + "decimal", "10.0", 9, 10, 11),
        ("decimal", "integer", "+0002", "1.99999999999999999", "2.00", "2.00000000000000001"),
        ("decimal", "double", "1.2E2", "119.9", "120", "120.1"),
        ("decimal", "decimal", "120", "1.19E2", "1.2E2", "1.21E2"),
        ("date", _XSD + "date", "2024-02-29", "2024-02-28", "2024-02-29", "2024-03-01"),
        (
            "dateTime",
            "dateTime",
            "2024-02-28T19:00:00-05:00",
            "2024-02-28",
            "2024-02-29",
            "2024-03-01",
        ),
        (
            "dateTime",
            _XSD + "dateTime",
            "2024-02-01T08:00:00+08:00",
            "2024-01-31T23:59:59Z",
            "2024-02-01T00:00:00",
            "2024-02-01T00:00:01Z",
        ),
        (
            "dateTime",
            "dateTime",
            "2024-02-01T00:00:00",
            "2024-01-31T23:59:59",
            "2024-01-31T19:00:00-05:00",
            "2024-02-01T00:00:01",
        ),
    ],
)
async def test_rules_typed_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    datatype: Datatype,
    literal_type: str,
    boundary: str,
    below: schemas.Scalar,
    equal: schemas.Scalar,
    above: schemas.Scalar,
) -> None:
    operand = {"datatype": literal_type, "lexical": boundary}
    names = ["minInclusive", "maxInclusive", "minExclusive", "maxExclusive"]
    report = await _report(
        monkeypatch, datatype, [below, equal, above, None], dict.fromkeys(names, operand)
    )
    [result] = report.results
    assert set(result.checks) == set(names)
    assert result.unchecked == []
    assert result.violations == 3
    assert [{f.check for f in s.failed} for s in result.samples] == [
        {"minInclusive", "minExclusive"},
        {"minExclusive", "maxExclusive"},
        {"maxInclusive", "maxExclusive"},
    ]


@pytest.mark.parametrize(
    ("boundary", "actual", "exact"),
    [
        ("12:00:00.1234561Z", "12:00:00.123456", False),
        ("12:00:00.123456Z", "12:00:00.12345601", False),
        ("12:00:00.12345600Z", "12:00:00.123456000", True),
    ],
)
async def test_rules_datetime_submicrosecond_precision(
    monkeypatch: pytest.MonkeyPatch, boundary: str, actual: str, *, exact: bool
) -> None:
    day = "2024-02-29T"
    report = await _report(
        monkeypatch,
        "dateTime",
        [day + actual],
        {"minExclusive": {"datatype": "dateTime", "lexical": day + boundary}},
    )
    [result] = report.results
    if exact:
        assert result.checks == ["minExclusive"]
        assert result.unchecked == []
        assert result.violations == 1
    else:
        assert [(u.check, u.reason) for u in result.unchecked] == [
            ("minExclusive", "value_mismatch")
        ]
        assert (result.checks, result.violations, result.samples) == ([], 0, [])


@pytest.mark.parametrize(
    ("datatype", "values", "literal_type", "lexical"),
    [
        ("integer", [1], "integer", "1.5"),
        ("integer", [1], "integer", "1e2"),
        ("decimal", ["1.0"], "double", "bad"),
        ("decimal", ["1.2E2"], _XSD + "decimal", "1.2E2"),
        ("date", ["2024-02-29"], "date", "2023-02-29"),
        ("dateTime", ["2024-02-29"], _XSD + "dateTime", "2024-02-29"),
        ("date", ["2024-02-29"], "dateTime", "2024-02-29T00:00:00"),
        ("integer", [1], "string", "2"),
        ("boolean", [True], "integer", "1"),
        ("integer", [1, "bad"], "integer", "2"),
        ("dateTime", ["2024-03-01T01:00:00", "bad"], "dateTime", "2024-03-02T00:00:00Z"),
    ],
)
async def test_rules_mismatch_discards_partial_violations(
    monkeypatch: pytest.MonkeyPatch,
    datatype: Datatype,
    values: list[schemas.Scalar | None],
    literal_type: str,
    lexical: str,
) -> None:
    operand = {"datatype": literal_type, "lexical": lexical}
    report = await _report(monkeypatch, datatype, values, {"minInclusive": operand})
    [result] = report.results
    assert (result.checks, result.violations, result.samples) == ([], 0, [])
    assert [(u.check, u.reason) for u in result.unchecked] == [("minInclusive", "value_mismatch")]
    assert (report.checked_rules, report.unchecked_rules) == (0, 1)


async def test_rules_text_presence_and_allowed_values(monkeypatch: pytest.MonkeyPatch) -> None:
    rule: dict[str, object] = {
        "allowedValues": [{"lexical": "AB", "lang": "en"}, {"lexical": "aB"}],
        "pattern": "^ab$",
        "flags": "i",
        "minCount": 2,
        "minLength": 2,
        "maxLength": 2,
    }
    report = await _report(monkeypatch, "string", ["AB", "aB", "A", "abc", "", None], rule)
    [result] = report.results
    assert result.violations == 4
    assert [s.object.values[_PROPERTY] for s in result.samples] == ["A", "abc", "", None]
    assert [{f.check for f in s.failed} for s in result.samples] == [
        {"allowedValues", "pattern", "minLength"},
        {"allowedValues", "pattern", "maxLength"},
        {"allowedValues", "pattern", "minLength"},
        {"minCount"},
    ]


async def test_rules_pattern_batch_reports_invalid_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn = AsyncMock(wraps=asyncio.create_subprocess_exec)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    report = await _report(
        monkeypatch,
        "string",
        ["A", "a", "B", None],
        {"pattern": "a", "flags": "i"},
        {"pattern": "A"},
        {"pattern": "["},
    )
    insensitive, sensitive, invalid = report.results
    assert [s.object.key for s in insensitive.samples] == ["2"]
    assert [s.object.key for s in sensitive.samples] == ["1", "2"]
    assert [(u.check, u.reason) for u in invalid.unchecked] == [("pattern", "value_mismatch")]
    assert (invalid.checks, invalid.violations) == ([], 0)
    spawn.assert_awaited_once()


@pytest.mark.parametrize("disconnect", [False, True], ids=["shared-deadline", "disconnect"])
async def test_rules_pattern_worker_is_reaped(
    monkeypatch: pytest.MonkeyPatch, *, disconnect: bool
) -> None:
    start = asyncio.create_subprocess_exec
    workers: list[asyncio.subprocess.Process] = []
    ready = asyncio.Event()

    async def start_sleeping(*args: str, **kwargs: Any) -> asyncio.subprocess.Process:
        worker = await start(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        workers.append(worker)
        ready.set()
        return worker

    monkeypatch.setattr(asyncio, "create_subprocess_exec", start_sleeping)
    monkeypatch.setattr(scanning, "QUERY_SECONDS", 10 if disconnect else 1.0)

    async def run() -> RuleReport:
        async with scanning.query_budget():
            return await _report(monkeypatch, "string", ["A"], {"pattern": "A"})

    task = asyncio.create_task(run())
    try:
        if disconnect:
            await asyncio.wait_for(ready.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(AppError) as caught:
                await task
            assert (caught.value.status, caught.value.code) == (504, "query.timeout")
        [worker] = workers
        assert worker.returncode is not None
        assert worker.returncode != 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for worker in workers:
            if worker.returncode is None:
                worker.kill()
                await worker.wait()


async def test_rules_paths_and_unsupported_components(monkeypatch: pytest.MonkeyPatch) -> None:
    report = await _report(
        monkeypatch,
        "string",
        ["v"],
        {"pathId": _RELATION, "minCount": 1},
        {"pathId": _UNBOUND, "minLength": 2},
        {
            "minCount": 1,
            "datatype": "string",
            "nodeKind": "Literal",
            "maxCount": 1,
            "classId": _PARENT,
            "pattern": "^v",
            "flags": "m",
            "allowedValuesLost": True,
        },
    )
    relation, unbound, mixed = report.results
    assert relation.property_id is None
    assert unbound.property_id == _UNBOUND
    assert [(u.check, u.reason) for u in relation.unchecked] == [("minCount", "path_not_property")]
    assert [(u.check, u.reason) for u in unbound.unchecked] == [("minLength", "path_not_bound")]
    assert mixed.checks == ["minCount"]
    assert {u.check for u in mixed.unchecked} == {
        "datatype",
        "nodeKind",
        "class",
        "maxCount",
        "pattern",
        "allowedValues",
    }
    assert {u.reason for u in mixed.unchecked} == {"check_not_supported"}
    assert all(r.violations == 0 for r in report.results)


@pytest.mark.parametrize(("language", "expected"), [("zh", "中文"), ("en", "English")])
async def test_rules_message_language_and_fallback(
    monkeypatch: pytest.MonkeyPatch, language: str, expected: str
) -> None:
    report = await _report(
        monkeypatch,
        "integer",
        [1],
        {
            "minCount": 1,
            "message": [
                {"lang": "en-US", "text": "English"},
                {"lang": "zh-CN", "text": "中文"},
            ],
        },
        {"minCount": 1, "message": [{"lang": "fr", "text": "Texte"}, {"text": "Default"}]},
        {"minCount": 1, "message": [{"lang": "fr", "text": "Texte"}]},
        language=language,
    )
    assert [r.message for r in report.results] == [expected, "Default", "Texte"]
