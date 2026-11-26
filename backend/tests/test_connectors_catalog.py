"""Catalog discovery, refresh jobs and browsing the persisted catalog (spec 003, 5.5)."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from external_source import ExternalSource
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors import catalog, config, connection, errors, jobs, service
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs import service as queue
from ontology_platform.modules.jobs.models import Job
from ontology_platform.settings import Settings
from support import csrf_headers
from test_ontology_support import sign_in

BASE = "/api/data-sources"
PRIMARY_KEYS: dict[str, list[str] | None] = {
    "casting_sequence": ["cast_no"],
    "coil": ["coil_no"],
    "heat": ["heat_no"],
    "quality_inspection": ["inspection_id"],
    "rolling_event": ["rolling_id"],
    "slab": ["slab_no"],
    "slab_rolling": ["slab_no", "rolling_id"],
    "surface_defect": ["defect_id"],
    "v_coil_quality": None,
}
TABLE_COMMENTS = {
    "casting_sequence": "浇次，记录连铸机一次连续浇铸的生产过程",
    "coil": "钢卷，记录热轧卷取后的规格、重量和流转状态",
    "heat": "炉次，记录一次转炉冶炼及精炼后的钢水成分",
    "quality_inspection": "钢卷质量检验，每行记录一次取样或复检的力学性能和判定",
    "rolling_event": "轧制事件，按同一厂区热轧机组的作业批次记录",
    "slab": "板坯，记录连铸切割后的定尺钢坯及其冶炼来源",
    "slab_rolling": "板坯参与轧制的记录，一行对应一块板坯参与一个轧制事件",
    "surface_defect": "钢卷表面缺陷，记录精整时发现的缺陷类型、位置和严重程度",
    "v_coil_quality": "按钢卷汇总检验次数、合格次数和最近检验日期，包含尚未检验的钢卷",
}

# In PostgreSQL, view columns carry no NOT NULL constraint, even for count(*).
STEEL_COLUMNS: dict[str, list[tuple[str, str, str, bool, str]]] = {
    "casting_sequence": [
        ("cast_no", "character varying(16)", "string", False, "浇次号"),
        ("org_id", "character varying(12)", "string", False, "组织编号"),
        ("site_id", "character varying(8)", "string", False, "厂区编号"),
        ("started_at", "timestamp with time zone", "dateTime", False, "连铸开浇时间，含时区"),
        ("superheat_c", "smallint", "integer", False, "中间包钢水过热度，单位为摄氏度"),
        (
            "casting_speed_m_min",
            "double precision",
            "decimal",
            False,
            "浇次平均拉速，单位为米每分钟",
        ),
    ],
    "coil": [
        (
            "coil_no",
            "character varying(16)",
            "string",
            False,
            "钢卷号，与来源板坯共用炉次和切割顺序段",
        ),
        (
            "rolling_id",
            "character varying(16)",
            "string",
            False,
            "完成卷取并产出本钢卷的轧制事件编号",
        ),
        ("org_id", "character varying(12)", "string", False, "组织编号"),
        ("site_id", "character varying(8)", "string", False, "厂区编号"),
        ("thickness_mm", "numeric(5,2)", "decimal", False, "成品带钢厚度，单位为毫米"),
        ("width_mm", "smallint", "integer", False, "成品带钢宽度，单位为毫米"),
        ("weight_t", "numeric(8,3)", "decimal", True, "钢卷实称重量，单位为吨，未称重时为空"),
        (
            "status",
            "mes.coil_status",
            "opaque",
            False,
            "钢卷流转状态，区分已产出、已检验、已发运和暂扣",
        ),
    ],
    "heat": [
        ("heat_no", "character varying(16)", "string", False, "炉次号"),
        ("cast_no", "character varying(16)", "string", False, "接收本炉钢水的浇次号"),
        ("org_id", "character varying(12)", "string", False, "组织编号"),
        ("site_id", "character varying(8)", "string", False, "厂区编号"),
        ("steel_grade", "character varying(12)", "string", False, "精炼后确认的钢种牌号"),
        ("tap_temp_c", "smallint", "integer", True, "出钢温度，单位为摄氏度，未测得时为空"),
        ("c_pct", "numeric(5,3)", "decimal", False, "成品样中碳的质量分数，单位为百分比"),
        ("si_pct", "numeric(5,3)", "decimal", False, "成品样中硅的质量分数，单位为百分比"),
        ("mn_pct", "numeric(5,3)", "decimal", False, "成品样中锰的质量分数，单位为百分比"),
        ("p_pct", "numeric(5,3)", "decimal", False, "成品样中磷的质量分数，单位为百分比"),
        ("s_pct", "numeric(5,3)", "decimal", False, "成品样中硫的质量分数，单位为百分比"),
    ],
    "quality_inspection": [
        ("inspection_id", "uuid", "opaque", False, "质检记录唯一标识"),
        ("coil_no", "character varying(16)", "string", False, "取样钢卷号"),
        ("lot_no", "character varying(20)", "string", False, "同一炉次、同厚度规格的检验批号"),
        ("inspected_on", "date", "date", False, "完成力学性能检验的日期"),
        ("yield_mpa", "smallint", "integer", False, "上屈服强度，单位为兆帕"),
        ("tensile_mpa", "smallint", "integer", False, "抗拉强度，单位为兆帕"),
        ("elongation_pct", "numeric(4,1)", "decimal", False, "断后伸长率，单位为百分比"),
        ("impact_j", "smallint", "integer", False, "二十摄氏度下的冲击吸收能量，单位为焦耳"),
        ("passed", "boolean", "boolean", False, "本次力学性能检验是否合格"),
    ],
    "rolling_event": [
        ("rolling_id", "character varying(16)", "string", False, "轧制事件编号"),
        ("org_id", "character varying(12)", "string", False, "组织编号"),
        ("site_id", "character varying(8)", "string", False, "厂区编号"),
        (
            "started_local",
            "timestamp without time zone",
            "dateTime",
            False,
            "轧制开始时间，按厂区当地时间记录",
        ),
        ("furnace_exit_c", "smallint", "integer", False, "本批板坯平均出炉温度，单位为摄氏度"),
        ("finish_temp_c", "smallint", "integer", False, "本批带钢平均终轧温度，单位为摄氏度"),
        ("coiling_temp_c", "smallint", "integer", False, "本批带钢平均卷取温度，单位为摄氏度"),
        (
            "params",
            "jsonb",
            "other",
            False,
            "轧制作业参数，含加热时长（分钟）和粗轧出口厚度（毫米）",
        ),
    ],
    "slab": [
        ("slab_no", "character varying(16)", "string", False, "板坯号，由炉次流水号和切割顺序标识"),
        ("cast_no", "character varying(16)", "string", False, "产出这块板坯的浇次号"),
        ("heat_no", "character varying(16)", "string", False, "板坯所属炉次号"),
        ("org_id", "character varying(12)", "string", False, "组织编号"),
        ("site_id", "character varying(8)", "string", False, "厂区编号"),
        ("thickness_mm", "smallint", "integer", False, "板坯厚度，单位为毫米"),
        ("width_mm", "smallint", "integer", False, "板坯宽度，单位为毫米"),
        ("length_mm", "integer", "integer", False, "板坯切割长度，单位为毫米"),
        ("weight_t", "numeric(8,3)", "decimal", False, "板坯理论重量，单位为吨"),
    ],
    "slab_rolling": [
        ("slab_no", "character varying(16)", "string", False, "参与轧制的板坯号"),
        ("rolling_id", "character varying(16)", "string", False, "板坯参与的轧制事件编号"),
    ],
    "surface_defect": [
        ("defect_id", "bigint", "integer", False, "表面缺陷记录编号"),
        ("coil_no", "character varying(16)", "string", False, "发现缺陷的钢卷号"),
        ("defect_type", "text", "string", False, "表面缺陷种类"),
        ("position_m", "numeric(7,1)", "decimal", False, "缺陷距卷头的长度，单位为米"),
        ("severity", "text", "string", False, "缺陷严重等级，分为轻微、一般和严重"),
    ],
    "v_coil_quality": [
        ("coil_no", "character varying(16)", "string", True, "钢卷号"),
        ("status", "mes.coil_status", "opaque", True, "钢卷当前流转状态"),
        ("inspection_count", "bigint", "integer", True, "钢卷取样及复检的总次数"),
        ("passed_count", "bigint", "integer", True, "钢卷力学性能检验合格的次数"),
        ("last_inspected_on", "date", "date", True, "钢卷最近一次检验的日期，尚未检验时为空"),
    ],
}

REFERENCES: dict[str, list[tuple[str, str, str, str]]] = {
    "casting_sequence": [],
    "coil": [
        ("fk_coil_rolling", "rolling_id", "rolling_event", "rolling_id"),
    ],
    "heat": [
        ("fk_heat_cast", "cast_no", "casting_sequence", "cast_no"),
    ],
    "quality_inspection": [
        ("fk_inspection_coil", "coil_no", "coil", "coil_no"),
    ],
    "rolling_event": [],
    "slab": [
        ("fk_slab_cast", "cast_no", "casting_sequence", "cast_no"),
        ("fk_slab_heat", "heat_no", "heat", "heat_no"),
    ],
    "slab_rolling": [
        ("fk_slab_rolling_event", "rolling_id", "rolling_event", "rolling_id"),
        ("fk_slab_rolling_slab", "slab_no", "slab", "slab_no"),
    ],
    "surface_defect": [
        ("fk_defect_coil", "coil_no", "coil", "coil_no"),
    ],
    "v_coil_quality": [],
}


@pytest.fixture
def worker(
    app: FastAPI, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    monkeypatch.setattr(config, "_configured", settings)
    monkeypatch.setattr(runner, "_handlers", {})
    jobs.register_handlers(factory, settings)
    return factory


@pytest.fixture
async def source(client: AsyncClient, db: AsyncSession, external_source: ExternalSource) -> UUID:
    await sign_in(client, db, Role.ADMIN)
    response = await client.post(
        BASE,
        headers=csrf_headers(client),
        json={
            "name": "钢铁 MES",
            "kind": "postgresql",
            "host": external_source.host,
            "port": external_source.port,
            "database": external_source.database,
            "username": external_source.reader,
            "password": external_source.reader_password,
            "sslMode": "disable",
            "schemas": ["mes"],
        },
    )
    assert response.status_code == 201
    await sign_in(client, db, Role.EDITOR)
    return UUID(response.json()["id"])


def _problem(response: Response, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.json()["code"] == code


async def _request(client: AsyncClient, source: UUID) -> None:
    response = await client.post(f"{BASE}/{source}/catalog/refresh", headers=csrf_headers(client))
    assert response.status_code == 202
    assert response.json()["id"] == str(source)
    info = response.json()["catalog"]
    assert (info["status"], info["errorCode"]) == ("refreshing", None)


async def _claim(
    db: AsyncSession, worker: async_sessionmaker[AsyncSession], source: UUID
) -> runner.JobContext:
    # claim() compares run_after with now(), the start of the current transaction: start a new
    # one, or a job queued after this session's last read is not due yet.
    await db.commit()
    job = await queue.claim(db, "catalog-test")
    assert job is not None
    assert job.kind == jobs.REFRESH_CATALOG
    assert job.payload == {"dataSourceId": str(source)}
    await db.commit()
    return runner.JobContext(
        job.id, job.payload, worker, attempts=job.attempts, worker_id="catalog-test"
    )


async def _run(db: AsyncSession, worker: async_sessionmaker[AsyncSession], source: UUID) -> None:
    claim = await _claim(db, worker, source)
    await runner._execute(jobs.REFRESH_CATALOG, claim, "catalog-test")
    completed = await db.get(Job, claim.id, populate_existing=True)
    assert completed is not None
    assert (completed.status, completed.error_code, completed.error_detail) == (
        "succeeded",
        None,
        None,
    )


async def _audits(db: AsyncSession, source: UUID) -> list[dict[str, Any]]:
    return list(
        await db.scalars(
            select(AuditEvent.detail)
            .where(
                AuditEvent.action == "datasource.catalog_refreshed",
                AuditEvent.target_type == "data_source",
                AuditEvent.target_id == str(source),
            )
            .order_by(AuditEvent.id)
        )
    )


async def _info(client: AsyncClient, source: UUID) -> dict[str, Any]:
    result = await client.get(f"{BASE}/{source}")
    assert result.status_code == 200
    info: dict[str, Any] = result.json()["catalog"]
    return info


async def test_refresh_caches_the_steel_sample(
    client: AsyncClient, db: AsyncSession, worker: async_sessionmaker[AsyncSession], source: UUID
) -> None:
    await _request(client, source)
    await _run(db, worker, source)
    info = await _info(client, source)
    assert info["status"] == "ready"
    assert info["errorCode"] is None
    assert datetime.fromisoformat(info["refreshedAt"]).tzinfo is not None
    assert info["tableCount"] == 9
    assert await _audits(db, source) == [{"tableCount": 9}]
    tables = await service.list_catalog_tables_for(db, source)
    assert [(t.schema_name, t.name) for t in tables] == [("mes", n) for n in sorted(PRIMARY_KEYS)]
    for table in tables:
        assert table.kind == ("view" if table.name == "v_coil_quality" else "table")
        assert table.primary_key == (
            tuple(key) if (key := PRIMARY_KEYS[table.name]) is not None else None
        )
        assert table.comment == TABLE_COMMENTS[table.name]
        assert [
            (c.position, c.name, c.type, c.family, c.nullable, c.comment) for c in table.columns
        ] == [(i, *metadata) for i, metadata in enumerate(STEEL_COLUMNS[table.name], 1)]
        assert sorted(
            (fk.name or "", fk.columns, fk.ref_schema, fk.ref_table, fk.ref_columns)
            for fk in table.foreign_keys
        ) == [
            (name, [col], "mes", target, [ref]) for name, col, target, ref in REFERENCES[table.name]
        ]
    heat = await client.get(f"{BASE}/{source}/catalog/tables/mes/heat")
    assert heat.status_code == 200
    assert heat.json()["foreignKeys"] == [
        {
            "name": "fk_heat_cast",
            "columns": ["cast_no"],
            "refSchema": "mes",
            "refTable": "casting_sequence",
            "refColumns": ["cast_no"],
        }
    ]


async def test_inspection_includes_special_relations_and_preserves_postgresql_metadata(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # conftest creates this disposable database with the test administrator. Only setup
    # needs its FDW privilege. Discovery runs with read privileges and all DDL rolls back.
    ddl = (
        "CREATE SCHEMA catalog_test",
        "CREATE SCHEMA catalog_ref",
        "CREATE SCHEMA pgreports",
        "CREATE TABLE pgreports.daily ()",
        "SET LOCAL search_path TO catalog_ref, public",
        "CREATE TABLE catalog_ref.parent (z int, a int, PRIMARY KEY (z, a)) PARTITION BY RANGE (z)",
        "CREATE TABLE public.catalog_parent_partition PARTITION OF catalog_ref.parent "
        "FOR VALUES FROM (0) TO (100)",
        'CREATE TABLE public.catalog_public_parent ("first, key" int, last_key int, '
        'PRIMARY KEY ("first, key", last_key))',
        "CREATE TYPE catalog_test.state AS ENUM ('ready')",
        'CREATE TABLE catalog_test.child (gone int, y int NOT NULL, "x, local" int, states int[], '
        "s catalog_test.state, v varchar(20), n numeric(10,3), t timestamp(3) with time zone, "
        'b bytea, j jsonb, i interval, h time, CONSTRAINT fk_pair FOREIGN KEY (y,"x, local") '
        'REFERENCES catalog_ref.parent(z,a), CONSTRAINT fk_public FOREIGN KEY ("x, local",y) '
        'REFERENCES public.catalog_public_parent("first, key",last_key))',
        "ALTER TABLE catalog_test.child DROP COLUMN gone",
        "COMMENT ON TABLE catalog_test.child IS '子表'",
        "COMMENT ON COLUMN catalog_test.child.y IS '首列'",
        "CREATE MATERIALIZED VIEW catalog_test.mv AS SELECT 1 AS v WITH NO DATA",
        "CREATE FOREIGN DATA WRAPPER catalog_test_fdw NO HANDLER",
        "CREATE SERVER catalog_test_server FOREIGN DATA WRAPPER catalog_test_fdw",
        "CREATE FOREIGN TABLE catalog_test.ft (v text) SERVER catalog_test_server",
        "CREATE TABLE catalog_test.empty ()",
        "CREATE TEMP TABLE catalog_temp_only (id int)",
        "SET LOCAL ROLE pg_read_all_data",
    )
    for statement in ddl:
        await db.execute(text(statement))
    conn = await db.connection()
    all_tables = await conn.run_sync(catalog.inspect_catalog, ())
    assert not any(
        t.schema in catalog.SYSTEM_SCHEMAS or t.schema.startswith(("pg_temp_", "pg_toast_temp_"))
        for t in all_tables
    )
    assert any(t.name == "parent" and t.schema == "catalog_ref" for t in all_tables)
    assert any(t.name == "daily" and t.schema == "pgreports" for t in all_tables)
    selected = await conn.run_sync(
        catalog.inspect_catalog, ("pg_catalog", "catalog_test", "missing", "catalog_test")
    )
    assert [(t.schema, t.name, t.kind) for t in selected] == [
        ("catalog_test", "child", "table"),
        ("catalog_test", "empty", "table"),
        ("catalog_test", "ft", "foreign_table"),
        ("catalog_test", "mv", "materialized_view"),
    ]
    child, empty, foreign, materialized = selected
    assert empty.columns == ()
    assert [c.name for c in foreign.columns] == ["v"]
    assert [c.name for c in materialized.columns] == ["v"]
    assert child.comment == "子表"
    assert [(c.name, c.type, c.family) for c in child.columns] == [
        ("y", "integer", "integer"),
        ("x, local", "integer", "integer"),
        ("states", "integer[]", "other"),
        ("s", "catalog_test.state", "opaque"),
        ("v", "character varying(20)", "string"),
        ("n", "numeric(10,3)", "decimal"),
        ("t", "timestamp(3) with time zone", "dateTime"),
        ("b", "bytea", "other"),
        ("j", "jsonb", "other"),
        ("i", "interval", "other"),
        ("h", "time without time zone", "other"),
    ]
    assert [c.position for c in child.columns] == list(range(1, 12))
    assert not child.columns[0].nullable
    assert child.columns[0].comment == "首列"
    assert all(c.nullable and c.comment is None for c in child.columns[1:])
    assert child.primary_key is None
    assert sorted(
        (fk.name or "", fk.columns, fk.ref_schema, fk.ref_table, fk.ref_columns)
        for fk in child.foreign_keys
    ) == [
        ("fk_pair", ["y", "x, local"], "catalog_ref", "parent", ["z", "a"]),
        (
            "fk_public",
            ["x, local", "y"],
            "public",
            "catalog_public_parent",
            ["first, key", "last_key"],
        ),
    ]
    scoped = ("catalog_test", "catalog_ref")
    monkeypatch.setattr(catalog, "MAX_TABLES", 5)
    monkeypatch.setattr(catalog, "MAX_COLUMNS", 15)
    parent, *rest = await conn.run_sync(catalog.inspect_catalog, scoped)
    assert (parent.name, parent.kind, parent.primary_key) == ("parent", "table", ("z", "a"))
    assert rest == selected
    monkeypatch.setattr(catalog, "MAX_COLUMNS", 14)
    with pytest.raises(errors.CatalogTooLargeError):
        await conn.run_sync(catalog.inspect_catalog, scoped)


def _cached(source: UUID, schema: str, name: str, comment: str | None = None) -> CatalogTable:
    return CatalogTable(
        data_source_id=source,
        schema_name=schema,
        table_name=name,
        kind="table",
        comment=comment,
        columns=[
            {
                "name": "id",
                "type": "bigint",
                "family": "integer",
                "nullable": False,
                "comment": "编号",
                "position": 1,
            }
        ],
        primary_key=["id"],
        foreign_keys=[],
    )


async def _cache_another_source(db: AsyncSession) -> UUID:
    other = DataSource(
        id=uuid4(),
        name="other",
        kind="postgresql",
        host="localhost",
        port=5432,
        database="other",
        username="reader",
    )
    db.add(other)
    await db.flush()
    db.add(_cached(other.id, "other", "heat"))
    await db.commit()
    return other.id


async def test_failed_refresh_keeps_last_good_snapshot_and_empty_success_replaces_it(
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = await _cache_another_source(db)
    other_snapshot = await service.list_catalog_tables_for(db, other)
    assert len(other_snapshot) == 1
    await _request(client, source)
    await _run(db, worker, source)
    original = await service.list_catalog_tables_for(db, source)
    assert len(original) == 9
    before = await _info(client, source)
    monkeypatch.setattr(catalog, "MAX_TABLES", 1)
    await _request(client, source)
    await _run(db, worker, source)
    assert await _info(client, source) == {
        **before,
        "status": "failed",
        "errorCode": "catalog.too_large",
    }
    assert await service.list_catalog_tables_for(db, source) == original
    response = await client.get(f"{BASE}/{source}/catalog/schemas")
    assert response.status_code == 200
    assert response.json() == [{"name": "mes", "tableCount": 9}]

    await db.execute(update(DataSource).where(DataSource.id == source).values(schemas=["missing"]))
    await db.commit()
    await _request(client, source)
    await _run(db, worker, source)
    after = await _info(client, source)
    assert (after["status"], after["errorCode"], after["tableCount"]) == ("ready", None, 0)
    assert datetime.fromisoformat(after["refreshedAt"]) >= datetime.fromisoformat(
        before["refreshedAt"]
    )
    assert await service.list_catalog_tables_for(db, source) == ()
    assert await service.list_catalog_tables_for(db, other) == other_snapshot
    assert await _audits(db, source) == [
        {"tableCount": 9},
        {"errorCode": "catalog.too_large"},
        {"tableCount": 0},
    ]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("unreachable", "datasource.connect_failed"),
        ("credential", "datasource.credential_unreadable"),
        ("platform", "datasource.platform_database"),
        ("timeout", "datasource.connect_failed"),
        ("other", "datasource.connect_failed"),
    ],
)
async def test_refresh_records_only_stable_errors(
    failure: str,
    code: str,
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    external_source: ExternalSource,
) -> None:
    if failure == "unreachable":
        await db.execute(
            update(DataSource).where(DataSource.id == source).values(host="127.0.0.1", port=1)
        )
    elif failure == "credential":
        await db.execute(
            update(DataSource).where(DataSource.id == source).values(secret=b"invalid")
        )
    else:
        exception = {
            "platform": errors.PlatformDatabaseError,
            "timeout": errors.QueryTimeoutError,
            "other": errors.ConnectorError,
        }[failure]

        async def fail(
            db: AsyncSession, params: connection.ConnectionParams, schema_names: Sequence[str]
        ) -> list[catalog.DiscoveredTable]:
            raise exception()

        monkeypatch.setattr(connection, "read_catalog", fail)
    await db.commit()
    await _request(client, source)
    await _run(db, worker, source)
    assert await _info(client, source) == {
        "status": "failed",
        "errorCode": code,
        "tableCount": 0,
        "refreshedAt": None,
    }
    assert await _audits(db, source) == [{"errorCode": code}]
    events = await db.scalars(select(AuditEvent))
    for event in events:
        assert external_source.reader_password not in repr(
            (event.action, event.target_type, event.target_id, event.detail, event.ip)
        )


async def test_refresh_ignores_a_missing_source_after_queueing(
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    await _request(client, source)
    await db.execute(delete(DataSource).where(DataSource.id == source))
    await db.commit()
    await _run(db, worker, source)
    assert await service.list_catalog_tables_for(db, source) == ()
    assert await _audits(db, source) == []


@pytest.mark.parametrize("with_snapshot", [False, True], ids=["never-read", "last-good-snapshot"])
async def test_archiving_while_refresh_is_queued_restores_the_last_catalog_state(
    with_snapshot: bool,
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unused(db: AsyncSession, source_id: UUID) -> list[service.TableUsage]:
        assert source_id == source
        return []

    monkeypatch.setattr(service, "_usage_provider", unused)
    if with_snapshot:
        await _request(client, source)
        await _run(db, worker, source)
    before = await _info(client, source)
    assert before["status"] == ("ready" if with_snapshot else "never")
    snapshot = await service.list_catalog_tables_for(db, source)
    assert len(snapshot) == (9 if with_snapshot else 0)
    previous_events = await _audits(db, source)
    assert previous_events == ([{"tableCount": 9}] if with_snapshot else [])

    await _request(client, source)
    await sign_in(client, db, Role.ADMIN)
    archived = await client.post(f"{BASE}/{source}/archive", headers=csrf_headers(client))
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    assert archived.json()["catalog"] == before
    await _run(db, worker, source)
    assert await _info(client, source) == before
    assert await service.list_catalog_tables_for(db, source) == snapshot
    assert await _audits(db, source) == previous_events
    response = await client.post(f"{BASE}/{source}/catalog/refresh", headers=csrf_headers(client))
    _problem(response, 409, "datasource.archived")
    assert await db.scalar(select(Job.id).where(Job.status == "queued")) is None


async def test_two_queued_refreshes_read_once_and_a_later_request_reads_again(
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _request(client, source)
    await _request(client, source)
    queued_ids = select(Job.id).where(Job.kind == jobs.REFRESH_CATALOG, Job.status == "queued")
    assert len(set(await db.scalars(queued_ids))) == 2
    await _run(db, worker, source)
    ready = await _info(client, source)
    assert (ready["status"], ready["tableCount"]) == ("ready", 9)
    assert await _audits(db, source) == [{"tableCount": 9}]
    cached = await service.list_catalog_tables_for(db, source)
    assert len(cached) == 9

    async def unexpected_read(
        db: AsyncSession, params: connection.ConnectionParams, schema_names: Sequence[str]
    ) -> list[catalog.DiscoveredTable]:
        pytest.fail("A queued duplicate read an already refreshed catalog")

    with monkeypatch.context() as patch:
        patch.setattr(connection, "read_catalog", unexpected_read)
        await _run(db, worker, source)
    assert await _info(client, source) == ready
    assert await service.list_catalog_tables_for(db, source) == cached
    assert await _audits(db, source) == [{"tableCount": 9}]
    assert await db.scalar(queued_ids) is None
    explicit_read = AsyncMock(wraps=connection.read_catalog)
    monkeypatch.setattr(connection, "read_catalog", explicit_read)
    await _request(client, source)
    await _run(db, worker, source)
    explicit_read.assert_awaited_once()
    assert await _audits(db, source) == [{"tableCount": 9}, {"tableCount": 9}]
    assert (await _info(client, source))["status"] == "ready"


@pytest.mark.parametrize("fails", [False, True], ids=["successful-read", "failed-read"])
async def test_worker_without_lease_cannot_commit_cache_status_or_audit(
    fails: bool,
    source: UUID,
    worker: async_sessionmaker[AsyncSession],
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.add(_cached(source, "old", "snapshot"))
    await db.commit()
    original = await service.list_catalog_tables_for(db, source)
    if fails:
        monkeypatch.setattr(catalog, "MAX_COLUMNS", 1)
    await _request(client, source)
    claim = await _claim(db, worker, source)
    stale = replace(claim, attempts=claim.attempts + 1)
    with pytest.raises(runner.JobLeaseLostError):
        await runner._handlers[jobs.REFRESH_CATALOG](stale)
    assert await service.list_catalog_tables_for(db, source) == original
    assert await _audits(db, source) == []
    assert await _info(client, source) == {
        "status": "refreshing",
        "errorCode": None,
        "tableCount": 1,
        "refreshedAt": None,
    }


async def test_catalog_requires_existing_source_ready_cache_and_editor(
    client: AsyncClient, db: AsyncSession, source: UUID
) -> None:
    missing = uuid4()
    for path in ("schemas", "tables", "tables/mes/heat"):
        _problem(await client.get(f"{BASE}/{missing}/catalog/{path}"), 404, "datasource.not_found")
        _problem(await client.get(f"{BASE}/{source}/catalog/{path}"), 409, "catalog.not_ready")
    response = await client.post(f"{BASE}/{missing}/catalog/refresh", headers=csrf_headers(client))
    _problem(response, 404, "datasource.not_found")
    await sign_in(client, db, Role.VIEWER)
    _problem(await client.get(f"{BASE}/{source}/catalog/tables"), 403, "auth.forbidden")
    response = await client.post(f"{BASE}/{source}/catalog/refresh", headers=csrf_headers(client))
    _problem(response, 403, "auth.forbidden")
    assert await db.scalar(select(Job.id)) is None


async def test_browse_cached_tables_by_schema_search_cursor_and_working_type(
    client: AsyncClient, db: AsyncSession, source: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys = [
        ("a", "alpha"),
        ("a", "heat"),
        ("a", "part_1"),
        ("a", "z"),
        ("b", "alpha"),
        ("b", "heat"),
        ("b", "yield"),
    ]
    for schema, name in reversed(keys):
        db.add(_cached(source, schema, name, "Yield 10%" if name == "heat" else None))
    await _cache_another_source(db)
    await db.execute(
        update(DataSource).where(DataSource.id == source).values(catalog_status="ready")
    )
    await db.commit()
    type_id = uuid4()

    async def usage(db: AsyncSession, source_id: UUID) -> list[service.TableUsage]:
        assert source_id == source
        return [
            service.TableUsage("b", "heat", uuid4(), "已发布", False, True),
            service.TableUsage("b", "heat", type_id, "炉次", True, False),
            service.TableUsage("b", "yield", uuid4(), "仅发布", False, True),
        ]

    monkeypatch.setattr(service, "_usage_provider", usage)
    base = f"{BASE}/{source}/catalog"
    schemas = await client.get(f"{base}/schemas")
    assert schemas.status_code == 200
    assert schemas.json() == [{"name": "a", "tableCount": 4}, {"name": "b", "tableCount": 3}]
    params: dict[str, str | int] = {"limit": 3}
    result = []
    for size in (3, 3, 1):
        page = await client.get(f"{base}/tables", params=params)
        assert page.status_code == 200
        items = page.json()["items"]
        assert len(items) == size
        result.extend(items)
        cursor = page.json()["nextCursor"]
        if size == 3:
            assert isinstance(cursor, str)
            assert cursor
            params["cursor"] = cursor
        else:
            assert cursor is None
    assert [(item["schema"], item["name"]) for item in result] == keys
    bound = {"id": str(type_id), "label": "炉次"}
    for item in result:
        assert item["columnCount"] == 1
        key = item["schema"], item["name"]
        assert item["boundType"] == (bound if key == ("b", "heat") else None)
    for filters, expected in [
        ({"schema": "b"}, keys[4:]),
        ({"schema": "B"}, []),
        ({"schema": "b", "q": "yIeLd"}, [("b", "heat"), ("b", "yield")]),
        ({"q": "%"}, [("a", "heat"), ("b", "heat")]),
        ({"q": "_"}, [("a", "part_1")]),
    ]:
        page = await client.get(f"{base}/tables", params=filters)
        assert page.status_code == 200
        assert [(i["schema"], i["name"]) for i in page.json()["items"]] == expected
    for invalid in ({"limit": "0"}, {"limit": "201"}, {"cursor": "bad-cursor!"}):
        _problem(await client.get(f"{base}/tables", params=invalid), 422, "validation.failed")
    _problem(await client.get(f"{base}/tables/b/missing"), 404, "catalog.table_not_found")
    detail = await client.get(f"{base}/tables/b/heat")
    assert detail.status_code == 200
    cached = await db.get(CatalogTable, (source, "b", "heat"))
    assert cached is not None
    fields = detail.json()
    refreshed_at = fields.pop("refreshedAt")
    assert datetime.fromisoformat(refreshed_at) == cached.refreshed_at
    assert fields == {
        **result[5],
        "columns": cached.columns,
        "primaryKey": ["id"],
        "foreignKeys": [],
    }
    monkeypatch.setattr(service, "_usage_provider", None)
    page = await client.get(f"{base}/tables")
    assert page.status_code == 200
    assert all(item["boundType"] is None for item in page.json()["items"])
