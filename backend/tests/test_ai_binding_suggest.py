"""AI binding suggestions (spec 003, section 8): requests, the job that turns the model's matches
into a change set for review, the checks that drop what the catalog or the ontology does not
have, sample values only where the data source allows them, and failures."""

import json
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from external_source import ExternalSource
from ontology_platform.errors import AppError
from ontology_platform.modules.ai import binding_suggest
from ontology_platform.modules.ai.binding_prompts import (
    COLUMNS_PURPOSE,
    MATCH_PURPOSE,
    ColumnsOut,
    ForeignKeyOut,
    LinkTableOut,
    MatchOut,
    PropertyMatchOut,
    RelationMatchOut,
    TableMatchOut,
)
from ontology_platform.modules.ai.binding_suggest import JOB_KIND, make_handler
from ontology_platform.modules.ai.gateway import AiUnavailableError, InputFile
from ontology_platform.modules.ai.models import BindingSuggestion
from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors import config as connectors_config
from ontology_platform.modules.connectors import jobs as connectors_jobs
from ontology_platform.modules.connectors.errors import SourceDisabledError
from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.jobs import runner
from ontology_platform.modules.jobs import service as queue
from ontology_platform.modules.jobs.models import Job
from ontology_platform.modules.jobs.runner import JobContext, RetryableJobError
from ontology_platform.modules.ontology import bindings as ontology_bindings
from ontology_platform.modules.ontology.bindings import ForeignKeyHop, LinkTableHop
from ontology_platform.modules.ontology.models import (
    ChangeItem,
    ChangeSet,
    Element,
    Evidence,
    Ontology,
)
from ontology_platform.settings import Settings
from support import csrf_headers
from test_connectors_support import add_source
from test_ontology_bindings_support import Steel, bind, bindings, steel
from test_ontology_import import STEEL, import_and_merge
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    element,
    publish,
    sign_in,
)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


SECRETS = ("steel-mes.example", "steel_mes", "steel_reader", "5432")


class CatalogGateway:
    """Answers the match step with `matches` and the columns step of a type with
    `columns[type id]` (nothing for other types); records what it was shown."""

    def __init__(self, matches: list[TableMatchOut], columns: dict[UUID, ColumnsOut]) -> None:
        self.matches = matches
        self.columns = columns
        self.texts: list[tuple[str, str]] = []

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
        effort: str | None = None,
    ) -> T:
        self.texts.append((purpose, text))
        if purpose == MATCH_PURPOSE:
            answer: BaseModel = MatchOut(matches=self.matches)
        else:
            assert purpose == COLUMNS_PURPOSE
            shown = text.split("Its table:")[0]
            answer = next(
                (out for type_id, out in self.columns.items() if f'"{type_id}"' in shown),
                ColumnsOut(properties=[], relations=[]),
            )
        assert isinstance(answer, schema)
        return answer

    async def ping(self) -> bool:
        return True


class FailingGateway(CatalogGateway):
    def __init__(self, error: Exception) -> None:
        super().__init__([], {})
        self.error = error

    async def structured[T: BaseModel](self, **_: Any) -> T:
        raise self.error


def table_match(
    type_: Element | str, table: str, keys: list[str] | None = None, confidence: float = 0.9
) -> TableMatchOut:
    return TableMatchOut(
        type_id=str(type_.id) if isinstance(type_, Element) else type_,
        schema_name="mes",
        table=table,
        key_columns=keys or [],
        confidence=confidence,
        rationale="表注释写明是炉次。",
    )


def column(property_: Element | str, name: str) -> PropertyMatchOut:
    return PropertyMatchOut(
        property_id=str(property_.id) if isinstance(property_, Element) else property_,
        column=name,
        confidence=0.8,
        rationale="列名一致。",
    )


def foreign_key(
    relation: Element, source: Element, target: Element, columns: list[str], refs: list[str]
) -> RelationMatchOut:
    return RelationMatchOut(
        relation_id=str(relation.id),
        source_type_id=str(source.id),
        target_type_id=str(target.id),
        foreign_key=ForeignKeyOut(side="source", columns=columns, references=refs),
        link_table=None,
        confidence=0.85,
        rationale="外键约束。",
    )


async def ready(db: AsyncSession, s: Steel, *, samples: bool = False) -> None:
    for source in (s.mes, s.other):
        source.catalog_status = "ready"
    s.mes.allow_samples = samples
    await db.commit()


async def ask(client: AsyncClient, s: Steel, **scope: Any) -> dict[str, Any]:
    response = await client.post(
        f"/api/ontologies/{s.ontology.id}/binding-suggestions",
        json={"dataSourceId": str(s.mes.id), "schemas": ["mes"], **scope},
        headers=csrf_headers(client),
    )
    assert response.status_code == 202, response.text
    body: dict[str, Any] = response.json()
    return body


async def answer(app: FastAPI, suggestion_id: str, gateway: Any, attempts: int = 1) -> None:
    handler = make_handler(app.state.session_factory, gateway, "test-model")
    await handler(
        JobContext(
            id=uuid4(),
            payload={"suggestionId": suggestion_id},
            session_factory=app.state.session_factory,
            attempts=attempts,
        )
    )


async def stored(app: FastAPI, suggestion_id: str) -> BindingSuggestion:
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    async with factory() as db:
        row = await db.get(BindingSuggestion, UUID(suggestion_id))
        assert row is not None
        return row


async def items_of(db: AsyncSession, change_set_id: UUID) -> list[ChangeItem]:
    rows = await db.scalars(
        select(ChangeItem)
        .where(ChangeItem.change_set_id == change_set_id)
        .order_by(ChangeItem.seq)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def audit_events(db: AsyncSession, action: str) -> list[AuditEvent]:
    rows = await db.scalars(
        select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.id)
    )
    return list(rows)


def heat_gateway(s: Steel) -> CatalogGateway:
    """炉次 and 浇次 matched with their columns and the foreign key between them, among
    suggestions the checks must drop."""
    return CatalogGateway(
        [
            # The table has a primary key: it wins over the model's choice.
            table_match(s.heat, "heat", ["cast_no"]),
            table_match(s.cast, "cast", ["cast_no"]),
            table_match(s.batch, "no_such_table"),
            table_match(str(uuid4()), "heat"),
            table_match(s.heat, "heat_v"),  # a second table for the same type
        ],
        {
            s.heat.id: ColumnsOut(
                properties=[
                    column(s.weight, "weight_t"),
                    column(s.external_id, "heat_no"),
                    column(s.batch_code, "batch"),
                    column(s.remark, "note"),  # jsonb cannot hold a string property
                    column(s.cast_no, "cast_no"),  # not a property of 炉次
                    column(s.weight, "no_such_column"),
                ],
                relations=[
                    foreign_key(s.in_cast, s.heat, s.cast, ["cast_no"], ["cast_no"]),
                    foreign_key(s.in_cast, s.heat, s.cast, ["no_such"], ["cast_no"]),
                ],
            ),
            s.cast.id: ColumnsOut(properties=[column(s.cast_no, "cast_no")], relations=[]),
        },
    )


async def test_a_suggestion_request_only_queues_work(client: AsyncClient, db: AsyncSession) -> None:
    steel_ontology = await add_ontology(db)
    await add_elements(db, element(steel_ontology, "entity_type", "Heat", "炉次"))
    source = DataSource(
        id=uuid4(),
        name="MES",
        kind="postgresql",
        host="steel-mes.example",
        port=5432,
        database="steel_mes",
        username="steel_reader",
        catalog_status="ready",
    )
    db.add(source)
    await db.flush()
    db.add(
        CatalogTable(
            data_source_id=source.id,
            schema_name="mes",
            table_name="heat",
            kind="table",
            comment="炉次",
            columns=[
                {
                    "name": "heat_no",
                    "type": "character varying(20)",
                    "family": "string",
                    "nullable": False,
                    "comment": "炉次号",
                    "position": 1,
                }
            ],
            primary_key=["heat_no"],
            foreign_keys=[],
        )
    )
    await db.commit()
    await sign_in(client, db, Role.EDITOR)
    elements_before = await db.scalar(select(func.count()).select_from(Element))

    response = await client.post(
        f"/api/ontologies/{steel_ontology.id}/binding-suggestions",
        json={"dataSourceId": str(source.id), "schemas": ["mes"]},
        headers=csrf_headers(client),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["changeSetId"] is None
    assert await db.scalar(select(func.count()).select_from(Element)) == elements_before
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0
    job = await db.scalar(select(Job).where(Job.kind == JOB_KIND))
    assert job is not None
    assert job.payload == {"suggestionId": response.json()["id"]}
    (event,) = await audit_events(db, "binding.suggested")
    assert event.detail == {
        "suggestionId": response.json()["id"],
        "dataSourceId": str(source.id),
        "tables": 1,
        "columns": 1,
        "samples": False,
    }


async def test_suggestions_become_one_change_set_for_review_and_nothing_else(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    elements_before = await db.scalar(select(func.count()).select_from(Element))
    gateway = heat_gateway(s)

    body = await ask(client, s)
    await answer(app, body["id"], gateway)

    row = await stored(app, body["id"])
    assert (row.status, row.step, row.error_code) == ("succeeded", "changeset", None)
    assert row.change_set_id is not None
    change_set = await db.get(ChangeSet, row.change_set_id)
    assert change_set is not None
    assert (change_set.source, change_set.status) == ("ai_binding", "open")
    assert change_set.title == "AI 绑定建议：MES"
    # The working version is untouched: no binding until a reviewer accepts and merges.
    assert await db.scalar(select(func.count()).select_from(Element)) == elements_before
    assert await bindings(db, s.ontology, active=False) == []

    items = await items_of(db, row.change_set_id)
    assert all(item.decision == "pending" and item.op == "create" for item in items)
    shown = {
        (item.kind, item.proposed["subjectRef"], canonical(item.proposed["binding"]))
        for item in items
    }
    heat_table = next(i for i in items if i.proposed["subjectRef"] == str(s.heat.id))
    cast_table = next(i for i in items if i.proposed["subjectRef"] == str(s.cast.id))
    assert heat_table.proposed["binding"]["keyColumns"] == ["heat_no"]
    assert heat_table.flags == []
    assert shown == {
        ("type_binding", str(s.heat.id), canonical(heat_table.proposed["binding"])),
        ("type_binding", str(s.cast.id), canonical(cast_table.proposed["binding"])),
        (
            "property_binding",
            str(s.weight.id),
            canonical({"target": "column", "column": "weight_t"}),
        ),
        (
            "property_binding",
            str(s.external_id.id),
            canonical({"target": "column", "column": "heat_no"}),
        ),
        (
            "property_binding",
            str(s.batch_code.id),
            canonical({"target": "column", "column": "batch"}),
        ),
        (
            "property_binding",
            str(s.cast_no.id),
            canonical({"target": "column", "column": "cast_no"}),
        ),
        (
            "relation_binding",
            str(s.in_cast.id),
            canonical(
                {
                    "target": "join",
                    "join": {
                        "kind": "foreign_key",
                        "side": "source",
                        "columns": ["cast_no"],
                        "references": ["cast_no"],
                    },
                }
            ),
        ),
    }
    relation = next(i for i in items if i.kind == "relation_binding")
    assert relation.proposed["domainRef"] == heat_table.temp_ref
    assert relation.proposed["rangeRef"] == cast_table.temp_ref
    weight = next(i for i in items if i.proposed["subjectRef"] == str(s.weight.id))
    assert weight.proposed["parentRef"] == heat_table.temp_ref
    assert (weight.confidence, weight.rationale) == (0.8, "列名一致。")
    # Left out by this module: a missing table, a view without the model's key, a missing
    # column, a missing join column, an unknown type, a property of another type; by the
    # binding rules: the jsonb column.
    assert (row.proposed, row.dropped) == (7, 7)
    assert row.samples_sent is False
    # What became of them is audited with the reasons, as counts.
    (finished,) = await audit_events(db, "binding.suggestion_finished")
    assert finished.detail == {
        "suggestionId": body["id"],
        "changeSetId": str(row.change_set_id),
        "proposed": 7,
        "dropped": 7,
        "reasons": {
            "binding.type_mismatch": 1,
            "suggestion.not_in_catalog": 4,
            "suggestion.unknown_element": 2,
        },
    }
    assert sum(finished.detail["reasons"].values()) == finished.detail["dropped"]
    assert (finished.actor_id, finished.target_id) == (row.user_id, str(s.ontology.id))


async def test_the_evidence_comes_from_the_catalog_and_matches_it(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    await answer(app, body["id"], heat_gateway(s))
    row = await stored(app, body["id"])
    assert row.change_set_id is not None
    items = {
        (item.kind, item.proposed["subjectRef"]): item
        for item in await items_of(db, row.change_set_id)
    }

    def facts(kind: str, subject: Element) -> list[tuple[Any, ...]]:
        return sorted(
            (e.source["fact"], e.source.get("column"), e.source["table"], e.quote)
            for e in evidence[items[(kind, str(subject.id))].id]
        )

    evidence: dict[UUID, list[Evidence]] = {}
    for item in items.values():
        evidence[item.id] = list(
            await db.scalars(select(Evidence).where(Evidence.change_item_id == item.id))
        )
    assert all(
        e.kind == "catalog" and e.source["dataSourceId"] == str(s.mes.id)
        for found in evidence.values()
        for e in found
    )
    assert facts("type_binding", s.heat) == [
        ("primary_key", None, "heat", "PRIMARY KEY (heat_no)"),
        ("table", None, "heat", "TABLE mes.heat"),
    ]
    assert facts("property_binding", s.weight) == [
        ("column", "weight_t", "heat", "weight_t numeric(8,2)"),
    ]
    assert facts("property_binding", s.external_id) == [
        ("column", "heat_no", "heat", "heat_no character varying(20) NOT NULL"),
    ]
    assert facts("relation_binding", s.in_cast) == [
        ("foreign_key", None, "heat", "FOREIGN KEY (cast_no) REFERENCES mes.cast (cast_no)"),
    ]


async def test_the_model_sees_metadata_only_without_samples_or_where_the_source_is(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await steel(db)
    await ready(db, s, samples=False)
    await sign_in(client, db, Role.EDITOR)

    async def no_reads(*_: Any) -> Any:
        raise AssertionError("no rows may be read while samples are off")

    monkeypatch.setattr(binding_suggest.connectors, "sample_values", no_reads)
    gateway = heat_gateway(s)
    body = await ask(client, s)
    await answer(app, body["id"], gateway)

    assert [purpose for purpose, _ in gateway.texts].count(MATCH_PURPOSE) == 1
    assert COLUMNS_PURPOSE in {purpose for purpose, _ in gateway.texts}
    everything = "\n".join(text for _, text in gateway.texts)
    assert "heat_no" in everything
    assert "numeric(8,2)" in everything
    for secret in SECRETS:
        assert secret not in everything
    assert '"samples"' not in everything
    row = await stored(app, body["id"])
    assert row.samples_sent is False
    assert row.change_set_id is not None
    quotes = await db.scalars(
        select(Evidence.source["fact"].astext)
        .join(ChangeItem, ChangeItem.id == Evidence.change_item_id)
        .where(ChangeItem.change_set_id == row.change_set_id)
    )
    assert "sample" not in set(quotes)
    assert await audit_events(db, "datasource.sampled") == []


async def test_samples_are_read_once_per_table_sent_and_kept_as_evidence_when_allowed(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await steel(db)
    await ready(db, s, samples=True)
    await sign_in(client, db, Role.EDITOR)
    reads: list[tuple[str, tuple[str, ...]]] = []

    async def sample_values(
        _: AsyncSession, source_id: UUID, table: Any, columns: tuple[str, ...]
    ) -> dict[str, tuple[Any, ...]]:
        assert source_id == s.mes.id
        reads.append((table.name, columns))
        return {name: ("H24-001", "H24-002") if name == "heat_no" else () for name in columns}

    monkeypatch.setattr(binding_suggest.connectors, "sample_values", sample_values)
    gateway = heat_gateway(s)
    body = await ask(client, s)
    await answer(app, body["id"], gateway)

    assert sorted(name for name, _ in reads) == ["cast", "heat"]
    columns_texts = [text for purpose, text in gateway.texts if purpose == COLUMNS_PURPOSE]
    assert any('"H24-001"' in text for text in columns_texts)
    match_text = next(text for purpose, text in gateway.texts if purpose == MATCH_PURPOSE)
    assert "H24-001" not in match_text  # samples come with the columns step only
    row = await stored(app, body["id"])
    assert row.samples_sent is True
    assert row.change_set_id is not None
    external = next(
        item
        for item in await items_of(db, row.change_set_id)
        if item.proposed["subjectRef"] == str(s.external_id.id)
    )
    found = list(await db.scalars(select(Evidence).where(Evidence.change_item_id == external.id)))
    assert sorted((e.source["fact"], e.quote) for e in found) == [
        ("column", "heat_no character varying(20) NOT NULL"),
        ("sample", "heat_no：H24-001、H24-002"),
    ]
    events = await audit_events(db, "datasource.sampled")
    assert [event.target_id for event in events] == [str(s.mes.id)] * 2
    assert {event.detail["columns"] for event in events} == {2, 6}
    (suggested,) = await audit_events(db, "binding.suggested")
    assert suggested.detail["samples"] is True


async def test_samples_switched_off_after_the_request_are_not_read(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await steel(db)
    await ready(db, s, samples=True)
    await sign_in(client, db, Role.EDITOR)
    calls: list[object] = []

    async def switched_off(*args: Any) -> Any:
        calls.append(args)
        raise SourceDisabledError

    monkeypatch.setattr(binding_suggest.connectors, "sample_values", switched_off)
    body = await ask(client, s)
    await answer(app, body["id"], heat_gateway(s))

    row = await stored(app, body["id"])
    assert (row.status, row.samples_sent) == ("succeeded", False)
    assert len(calls) == 1  # the first refusal stops the reads
    assert await audit_events(db, "datasource.sampled") == []


async def test_a_view_without_a_primary_key_takes_the_models_key_marked_unverified(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    gateway = CatalogGateway(
        [table_match(s.heat, "heat_v", ["heat_no"]), table_match(s.cast, "heat_v", ["nope"])], {}
    )
    body = await ask(client, s, typeIds=[str(s.heat.id), str(s.cast.id)])
    await answer(app, body["id"], gateway)

    row = await stored(app, body["id"])
    assert row.change_set_id is not None
    (item,) = await items_of(db, row.change_set_id)
    assert item.proposed["binding"]["table"] == "heat_v"
    assert item.proposed["binding"]["keyColumns"] == ["heat_no"]
    assert item.flags == ["key_unverified"]
    assert (row.proposed, row.dropped) == (1, 1)


async def test_a_bound_type_only_gets_what_it_lacks_under_its_own_binding(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)  # 炉次, 浇次, 重量, 外部编号 and 对应浇次 are bound
    heat_binding = next(
        b
        for b in await bindings(db, s.ontology)
        if b.kind == "type_binding" and b.subject_id == s.heat.id
    )
    gateway = CatalogGateway(
        [table_match(s.heat, "heat_v")],
        {
            s.heat.id: ColumnsOut(
                properties=[column(s.weight, "weight_t"), column(s.batch_code, "batch")],
                relations=[],
            )
        },
    )
    body = await ask(client, s, typeIds=[str(s.heat.id)])
    await answer(app, body["id"], gateway)

    # No table to match: 炉次 has one. Its columns step offers only the unbound properties.
    assert [purpose for purpose, _ in gateway.texts] == [COLUMNS_PURPOSE]
    shown = gateway.texts[0][1].split("Properties to map:")[1].split("Relations to map:")[0]
    assert str(s.batch_code.id) in shown
    assert str(s.weight.id) not in shown
    row = await stored(app, body["id"])
    assert row.change_set_id is not None
    (item,) = await items_of(db, row.change_set_id)
    assert item.proposed == {
        "subjectRef": str(s.batch_code.id),
        "parentRef": str(heat_binding.id),
        "binding": {"target": "column", "column": "batch"},
    }
    assert (row.proposed, row.dropped) == (1, 1)


async def test_nothing_to_propose_leaves_no_change_set(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    await answer(app, body["id"], CatalogGateway([table_match(s.heat, "no_such_table")], {}))

    row = await stored(app, body["id"])
    assert (row.status, row.change_set_id, row.proposed, row.dropped) == ("succeeded", None, 0, 1)
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0
    (finished,) = await audit_events(db, "binding.suggestion_finished")
    assert finished.detail == {
        "suggestionId": body["id"],
        "changeSetId": None,
        "proposed": 0,
        "dropped": 1,
        "reasons": {"suggestion.not_in_catalog": 1},
    }


async def test_a_scope_over_the_limits_is_refused(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await ready(db, s)
    db.add(
        CatalogTable(
            data_source_id=s.mes.id,
            schema_name="wide",
            table_name="readings",
            kind="table",
            comment=None,
            columns=[
                {
                    "name": f"c{i}",
                    "type": "integer",
                    "family": "integer",
                    "nullable": True,
                    "comment": None,
                    "position": i,
                }
                for i in range(1, 4002)
            ],
            primary_key=None,
            foreign_keys=[],
        )
    )
    await db.commit()
    await sign_in(client, db, Role.EDITOR)

    response = await client.post(
        f"/api/ontologies/{s.ontology.id}/binding-suggestions",
        json={"dataSourceId": str(s.mes.id), "schemas": ["wide"]},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "binding_suggestion.scope_too_large"
    assert await db.scalar(select(func.count()).select_from(BindingSuggestion)) == 0
    assert await db.scalar(select(func.count()).select_from(Job)) == 0


async def test_an_archived_source_or_one_without_a_catalog_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.EDITOR)
    url = f"/api/ontologies/{s.ontology.id}/binding-suggestions"

    for source, code in ((s.mes, "catalog.not_ready"), (s.archived, "datasource.archived")):
        response = await client.post(
            url,
            json={"dataSourceId": str(source.id), "schemas": ["mes"]},
            headers=csrf_headers(client),
        )
        assert response.status_code == 409
        assert response.json()["code"] == code
    response = await client.post(
        url, json={"dataSourceId": str(uuid4()), "schemas": ["mes"]}, headers=csrf_headers(client)
    )
    assert (response.status_code, response.json()["code"]) == (404, "datasource.not_found")


async def test_requests_need_a_session_and_an_editor_and_are_the_users_own(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    create = f"/api/ontologies/{s.ontology.id}/binding-suggestions"
    payload = {"dataSourceId": str(s.mes.id), "schemas": ["mes"]}

    for method, path in (
        ("POST", create),
        ("GET", create),
        ("GET", f"/api/binding-suggestions/{uuid4()}"),
    ):
        response = await client.request(method, path, json=payload if method == "POST" else None)
        assert (response.status_code, response.json()["code"]) == (401, "auth.not_authenticated")

    await sign_in(client, db, Role.VIEWER)
    response = await client.post(create, json=payload, headers=csrf_headers(client))
    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
    for path in (create, f"/api/binding-suggestions/{uuid4()}"):
        response = await client.get(path)
        assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
    assert await db.scalar(select(func.count()).select_from(BindingSuggestion)) == 0

    await sign_in(client, db, Role.EDITOR)
    mine = await ask(client, s)
    listed = await client.get(create)
    assert [entry["id"] for entry in listed.json()] == [mine["id"]]
    await sign_in(client, db, Role.REVIEWER)
    response = await client.get(f"/api/binding-suggestions/{mine['id']}")
    assert (response.status_code, response.json()["code"]) == (404, "binding_suggestion.not_found")
    assert (await client.get(create)).json() == []


async def test_a_model_failure_fails_the_request_and_proposes_nothing(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)

    with pytest.raises(AppError):
        await answer(app, body["id"], FailingGateway(AiUnavailableError("down", retryable=False)))

    row = await stored(app, body["id"])
    assert (row.status, row.step, row.error_code) == ("failed", "match", "ai.unavailable")
    assert row.finished_at is not None
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0
    assert await audit_events(db, "binding.suggestion_finished") == []


# ---------- the steel sample end to end (spec 003, section 15: "AI 建议") ----------

EXPECTED = Path(__file__).parent / "fixtures" / "connectors" / "steel" / "expected-bindings.toml"


async def _steel_catalog(
    app: FastAPI,
    db: AsyncSession,
    client: AsyncClient,
    external_source: ExternalSource,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> DataSource:
    """The steel sample database as a data source, its catalog read by the refresh job."""
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    monkeypatch.setattr(connectors_config, "_configured", settings)
    monkeypatch.setattr(runner, "_handlers", {})
    connectors_jobs.register_handlers(factory, settings)
    source = await add_source(db, external_source)
    response = await client.post(
        f"/api/data-sources/{source.id}/catalog/refresh", headers=csrf_headers(client)
    )
    assert response.status_code == 202, response.text
    await db.commit()
    job = await queue.claim(db, "suggest-test")
    assert job is not None
    await db.commit()
    await runner._execute(
        connectors_jobs.REFRESH_CATALOG,
        JobContext(job.id, job.payload, factory, attempts=job.attempts, worker_id="suggest-test"),
        "suggest-test",
    )
    await db.refresh(source)
    assert source.catalog_status == "ready"
    return source


def _relation_out(entry: dict[str, Any], ids: dict[str, UUID]) -> RelationMatchOut:
    join = entry["join"]
    return RelationMatchOut(
        relation_id=str(ids[entry["relation"]]),
        source_type_id=str(ids[entry["source"]]),
        target_type_id=str(ids[entry["target"]]),
        foreign_key=(
            ForeignKeyOut(side=join["side"], columns=join["columns"], references=join["references"])
            if join["kind"] == "foreign_key"
            else None
        ),
        link_table=(
            LinkTableOut(
                schema_name=join["schema"],
                table=join["table"],
                source_columns=join["sourceColumns"],
                target_columns=join["targetColumns"],
            )
            if join["kind"] == "link_table"
            else None
        ),
        confidence=0.85,
        rationale="外键约束。",
    )


def _join_of(hop: ForeignKeyHop | LinkTableHop) -> dict[str, Any]:
    if isinstance(hop, LinkTableHop):
        return {
            "kind": "link_table",
            "schema": hop.schema,
            "table": hop.table,
            "sourceColumns": list(hop.source_columns),
            "targetColumns": list(hop.target_columns),
        }
    return {
        "kind": "foreign_key",
        "side": hop.side,
        "columns": list(hop.columns),
        "references": list(hop.references),
    }


async def test_the_expected_steel_bindings_reach_the_release_once_reviewed(
    app: FastAPI,
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = tomllib.loads(EXPECTED.read_text("utf-8"))
    await sign_in(client, db, Role.ADMIN)
    imported = await import_and_merge(client, STEEL, filename="steel.ttl")
    ontology_id = UUID(imported["ontology"]["id"])
    source = await _steel_catalog(app, db, client, external_source, settings, monkeypatch)
    rows = await db.scalars(select(Element).where(Element.ontology_id == ontology_id))
    ids = {row.iri: row.id for row in rows if row.iri}
    iris = {element_id: iri for iri, element_id in ids.items()}
    # The model answers what expected-bindings.toml says, each relation from its source type.
    gateway = CatalogGateway(
        [table_match(str(ids[t["type"]]), t["table"], list(t["key"])) for t in expected["types"]],
        {
            ids[t["type"]]: ColumnsOut(
                properties=[column(str(ids[p]), c) for p, c in t["properties"].items()],
                relations=[
                    _relation_out(r, ids) for r in expected["relations"] if r["source"] == t["type"]
                ],
            )
            for t in expected["types"]
        },
    )

    response = await client.post(
        f"/api/ontologies/{ontology_id}/binding-suggestions",
        json={"dataSourceId": str(source.id), "schemas": ["mes"]},
        headers=csrf_headers(client),
    )
    assert response.status_code == 202, response.text
    await answer(app, response.json()["id"], gateway)
    row = await stored(app, response.json()["id"])
    assert (row.status, row.dropped) == ("succeeded", 0)
    assert row.change_set_id is not None
    items = await items_of(db, row.change_set_id)
    link = next(
        i for i in items if i.proposed["binding"].get("join", {}).get("kind") == "link_table"
    )
    evidence = await db.scalars(select(Evidence).where(Evidence.change_item_id == link.id))
    facts = {((e.source or {}).get("table"), (e.source or {}).get("fact")) for e in evidence}
    assert ("slab_rolling", "table") in facts
    assert ("slab_rolling", "foreign_key") in facts

    merged = await accept_and_merge(client, row.change_set_id)
    assert merged["skipped"] == []
    ontology = await db.get(Ontology, ontology_id)
    assert ontology is not None
    assert (await publish(client, ontology)).status_code == 201
    model = await ontology_bindings.bound_model(db, ontology_id)

    assert model is not None
    assert {
        (
            t.iri,
            t.schema,
            t.table,
            t.key_columns,
            frozenset((iris[p.property_id], p.column) for p in t.properties),
        )
        for t in model.types
    } == {
        (t["type"], t["schema"], t["table"], tuple(t["key"]), frozenset(t["properties"].items()))
        for t in expected["types"]
    }
    assert {
        (
            iris[r.relation_id],
            iris[r.source_type_id],
            iris[r.target_type_id],
            canonical(_join_of(r.join)),
        )
        for r in model.relations
    } == {
        (r["relation"], r["source"], r["target"], canonical(r["join"]))
        for r in expected["relations"]
    }


# ---------- replays, retries and what changed while the job ran ----------


async def test_a_replayed_job_does_not_propose_twice(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    await answer(app, body["id"], heat_gateway(s))
    again = heat_gateway(s)

    await answer(app, body["id"], again)

    assert again.texts == []
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 1
    assert len(await audit_events(db, "binding.suggestion_finished")) == 1


async def test_a_retryable_model_failure_queues_the_request_again(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)

    with pytest.raises(RetryableJobError):
        await answer(app, body["id"], FailingGateway(AiUnavailableError("down", retryable=True)))

    row = await stored(app, body["id"])
    assert (row.status, row.error_code, row.finished_at) == ("queued", None, None)
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0


async def test_a_request_interrupted_too_often_fails_without_asking_the_model(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    gateway = heat_gateway(s)

    with pytest.raises(AppError):
        await answer(app, body["id"], gateway, attempts=4)

    row = await stored(app, body["id"])
    assert (row.status, row.error_code) == ("failed", "internal.error")
    assert gateway.texts == []
    assert await db.scalar(select(func.count()).select_from(ChangeSet)) == 0


def _narrow(source: DataSource, schema: str, name: str) -> CatalogTable:
    return CatalogTable(
        data_source_id=source.id,
        schema_name=schema,
        table_name=name,
        kind="table",
        comment=None,
        columns=[
            {
                "name": "id",
                "type": "integer",
                "family": "integer",
                "nullable": False,
                "comment": None,
                "position": 1,
            }
        ],
        primary_key=["id"],
        foreign_keys=[],
    )


async def test_more_than_200_tables_are_refused(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await ready(db, s)
    db.add_all([_narrow(s.mes, "many", f"t{i}") for i in range(201)])
    await db.commit()
    await sign_in(client, db, Role.EDITOR)

    response = await client.post(
        f"/api/ontologies/{s.ontology.id}/binding-suggestions",
        json={"dataSourceId": str(s.mes.id), "schemas": ["many"]},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "binding_suggestion.scope_too_large"


async def test_a_scope_grown_past_the_limits_since_the_request_fails_the_job(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    # A refresh of the catalog found many more tables in the schema.
    db.add_all([_narrow(s.mes, "mes", f"t{i}") for i in range(200)])
    await db.commit()
    gateway = heat_gateway(s)

    with pytest.raises(AppError):
        await answer(app, body["id"], gateway)

    row = await stored(app, body["id"])
    assert (row.status, row.error_code) == ("failed", "binding_suggestion.scope_too_large")
    assert gateway.texts == []


async def test_samples_switched_off_while_the_job_runs_are_not_sent(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await steel(db)
    await ready(db, s, samples=True)
    await sign_in(client, db, Role.EDITOR)

    async def sample_values(
        _: AsyncSession, __: UUID, table: Any, columns: tuple[str, ...]
    ) -> dict[str, tuple[Any, ...]]:
        return dict.fromkeys(columns, ("H24-001",))

    async def switched_off(*_: Any) -> bool:
        return False

    monkeypatch.setattr(binding_suggest.connectors, "sample_values", sample_values)
    monkeypatch.setattr(binding_suggest, "_samples_allowed", switched_off)
    gateway = heat_gateway(s)
    body = await ask(client, s)
    await answer(app, body["id"], gateway)

    assert all("H24-001" not in text for _, text in gateway.texts)
    row = await stored(app, body["id"])
    assert row.samples_sent is False
    assert row.change_set_id is not None
    facts = await db.scalars(
        select(Evidence.source["fact"].astext)
        .join(ChangeItem, ChangeItem.id == Evidence.change_item_id)
        .where(ChangeItem.change_set_id == row.change_set_id)
    )
    assert "sample" not in set(facts)


async def test_a_table_shared_by_a_type_and_its_subtype_is_sampled_once(
    app: FastAPI, client: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = await steel(db)
    await ready(db, s, samples=True)
    await sign_in(client, db, Role.EDITOR)
    reads: list[str] = []

    async def sample_values(
        _: AsyncSession, __: UUID, table: Any, columns: tuple[str, ...]
    ) -> dict[str, tuple[Any, ...]]:
        reads.append(table.name)
        return dict.fromkeys(columns, ())

    monkeypatch.setattr(binding_suggest.connectors, "sample_values", sample_values)
    gateway = CatalogGateway(
        [table_match(s.batch, "heat"), table_match(s.heat, "heat")],
        {
            s.batch.id: ColumnsOut(properties=[column(s.batch_code, "batch")], relations=[]),
            s.heat.id: ColumnsOut(properties=[column(s.weight, "weight_t")], relations=[]),
        },
    )
    body = await ask(client, s, typeIds=[str(s.batch.id), str(s.heat.id)])
    await answer(app, body["id"], gateway)

    assert reads == ["heat"]
    assert len(await audit_events(db, "datasource.sampled")) == 1


# ---------- several candidates for one place ----------


async def test_a_column_that_fails_the_rules_gives_way_to_the_next_candidate(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    gateway = CatalogGateway(
        [table_match(s.heat, "heat")],
        {
            s.heat.id: ColumnsOut(
                properties=[
                    column(s.remark, "note"),  # jsonb: the binding rules refuse it
                    column(s.remark, "remark"),
                    column(s.remark, "batch"),  # not tried: the place is taken
                    column(s.remark, "heat_no"),  # over the limit of candidates
                ],
                relations=[],
            )
        },
    )
    body = await ask(client, s, typeIds=[str(s.heat.id)])
    await answer(app, body["id"], gateway)

    row = await stored(app, body["id"])
    assert row.change_set_id is not None
    remarks = [
        item.proposed["binding"]["column"]
        for item in await items_of(db, row.change_set_id)
        if item.proposed["subjectRef"] == str(s.remark.id)
    ]
    assert remarks == ["remark"]
    (finished,) = await audit_events(db, "binding.suggestion_finished")
    assert finished.detail["reasons"] == {
        "binding.duplicate": 1,
        "binding.type_mismatch": 1,
        "suggestion.repeated": 1,
    }
    assert finished.detail["dropped"] == row.dropped == 3


async def test_a_scope_without_tables_is_refused(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)

    response = await client.post(
        f"/api/ontologies/{s.ontology.id}/binding-suggestions",
        json={"dataSourceId": str(s.mes.id), "schemas": ["nothing_here"]},
        headers=csrf_headers(client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "binding_suggestion.scope_empty"
    assert await db.scalar(select(func.count()).select_from(BindingSuggestion)) == 0
    assert await db.scalar(select(func.count()).select_from(Job)) == 0
    assert await audit_events(db, "binding.suggested") == []


async def test_tables_gone_from_the_catalog_since_the_request_leave_nothing_to_propose(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await ready(db, s)
    await sign_in(client, db, Role.EDITOR)
    body = await ask(client, s)
    await db.execute(delete(CatalogTable).where(CatalogTable.data_source_id == s.mes.id))
    await db.commit()

    await answer(app, body["id"], heat_gateway(s))

    row = await stored(app, body["id"])
    assert (row.status, row.change_set_id, row.proposed) == ("succeeded", None, 0)
