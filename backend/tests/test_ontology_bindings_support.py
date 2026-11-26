"""Helpers for the binding tests (spec 003, section 6). This module has no tests of its own.

The data sources and their catalogs are inserted straight into the connectors tables, as
batch 1 left them: the binding tests do not depend on the connectors implementation.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import User
from ontology_platform.modules.ontology.models import BINDING_KINDS, Element, Ontology
from support import ADMIN_USERNAME, csrf_headers
from test_ontology_support import add_elements, add_ontology, element


@dataclass
class Steel:
    ontology: Ontology
    batch: Element  # 批次, the parent type of 炉次
    heat: Element  # 炉次
    cast: Element  # 浇次
    weight: Element  # decimal, on 炉次
    external_id: Element  # string, no domain
    cast_no: Element  # string, on 浇次
    batch_code: Element  # string, on 批次 (inherited by 炉次)
    remark: Element  # string, no domain, no shape: an import can drop it cleanly
    in_cast: Element  # 炉次 → 浇次
    mes: DataSource
    other: DataSource
    archived: DataSource


def _column(name: str, type_: str, family: str, position: int) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "family": family,
        "nullable": position != 1,
        "comment": None,
        "position": position,
    }


def _table(
    source: DataSource,
    name: str,
    columns: list[tuple[str, str, str]],
    *,
    kind: str = "table",
    primary_key: list[str] | None = None,
    foreign_keys: list[dict[str, Any]] | None = None,
) -> CatalogTable:
    return CatalogTable(
        data_source_id=source.id,
        schema_name="mes",
        table_name=name,
        kind=kind,
        comment=None,
        columns=[
            _column(column, type_, family, position)
            for position, (column, type_, family) in enumerate(columns, start=1)
        ],
        primary_key=primary_key,
        foreign_keys=foreign_keys or [],
    )


def _source(name: str, *, status: str = "active") -> DataSource:
    return DataSource(
        id=uuid4(),
        name=name,
        kind="postgresql",
        host="steel-mes.example",
        port=5432,
        database="steel_mes",
        username="steel_reader",
        status=status,
    )


async def steel(db: AsyncSession) -> Steel:
    """The steel ontology, a MES data source with a cached catalog, a second data source and
    an archived one."""
    ontology = await add_ontology(db)
    batch = element(ontology, "entity_type", "Batch", "批次")
    await add_elements(db, batch)
    heat = element(ontology, "entity_type", "Heat", "炉次", parent_id=batch.id)
    cast = element(ontology, "entity_type", "Cast", "浇次")
    await add_elements(db, heat, cast)
    weight = element(
        ontology, "property", "weight", "重量", domain_id=heat.id, datatype="decimal"
    )
    # Without a domain, as OWL allows for imported elements (the steel sample has externalId);
    # as an import reads them back, so that exporting and importing again changes nothing.
    external_id = element(
        ontology,
        "property",
        "externalId",
        "外部编号",
        datatype="string",
        auto_shape=False,
        multiple=True,
        iri=ontology.base_iri + "externalId",
    )
    cast_no = element(ontology, "property", "castNo", "浇次号", domain_id=cast.id, datatype="string")
    batch_code = element(
        ontology, "property", "batchCode", "批次号", domain_id=batch.id, datatype="string"
    )
    remark = element(
        ontology,
        "property",
        "remark",
        "备注",
        datatype="string",
        auto_shape=False,
        multiple=True,
        iri=ontology.base_iri + "remark",
    )
    in_cast = element(
        ontology, "relation_type", "inCast", "对应浇次", domain_id=heat.id, range_id=cast.id
    )
    await add_elements(db, weight, external_id, cast_no, batch_code, remark, in_cast)

    mes, other, archived = _source("MES"), _source("质量库"), _source("旧库", status="archived")
    db.add_all([mes, other, archived])
    await db.flush()
    db.add_all(
        [
            _table(
                mes,
                "heat",
                [
                    ("heat_no", "character varying(20)", "string"),
                    ("cast_no", "character varying(20)", "string"),
                    ("weight_t", "numeric(8,2)", "decimal"),
                    ("batch", "character varying(20)", "string"),
                    ("note", "jsonb", "other"),
                    ("remark", "text", "string"),
                ],
                primary_key=["heat_no"],
                foreign_keys=[
                    {
                        "name": "heat_cast_fk",
                        "columns": ["cast_no"],
                        "refSchema": "mes",
                        "refTable": "cast",
                        "refColumns": ["cast_no"],
                    }
                ],
            ),
            _table(
                mes,
                "cast",
                [("cast_no", "character varying(20)", "string"), ("seq", "integer", "integer")],
                primary_key=["cast_no"],
            ),
            _table(
                mes, "heat_v", [("heat_no", "character varying(20)", "string")], kind="view"
            ),
            _table(
                mes,
                "heat_cast",
                [
                    ("heat_no", "character varying(20)", "string"),
                    ("cast_no", "character varying(20)", "string"),
                ],
                primary_key=["heat_no", "cast_no"],
            ),
            _table(
                other,
                "cast",
                [("cast_no", "character varying(20)", "string")],
                primary_key=["cast_no"],
            ),
            _table(
                archived,
                "heat",
                [("heat_no", "character varying(20)", "string")],
                primary_key=["heat_no"],
            ),
        ]
    )
    await db.commit()
    return Steel(
        ontology=ontology,
        batch=batch,
        heat=heat,
        cast=cast,
        weight=weight,
        external_id=external_id,
        cast_no=cast_no,
        batch_code=batch_code,
        remark=remark,
        in_cast=in_cast,
        mes=mes,
        other=other,
        archived=archived,
    )


# ---------- edit items, as the API takes them ----------


def table(
    source: DataSource | UUID,
    name: str = "heat",
    keys: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "target": "table",
        "dataSourceId": str(source.id if isinstance(source, DataSource) else source),
        "schema": "mes",
        "table": name,
        "keyColumns": keys if keys is not None else ["heat_no"],
    }


def foreign_key(
    columns: list[str] | None = None,
    references: list[str] | None = None,
    side: str = "source",
) -> dict[str, Any]:
    return {
        "target": "join",
        "join": {
            "kind": "foreign_key",
            "side": side,
            "columns": columns if columns is not None else ["cast_no"],
            "references": references if references is not None else ["cast_no"],
        },
    }


def link_table(
    source_columns: list[str] | None = None, target_columns: list[str] | None = None
) -> dict[str, Any]:
    return {
        "target": "join",
        "join": {
            "kind": "link_table",
            "schema": "mes",
            "table": "heat_cast",
            "sourceColumns": source_columns if source_columns is not None else ["heat_no"],
            "targetColumns": target_columns if target_columns is not None else ["cast_no"],
        },
    }


def ref(value: Element | str) -> str:
    return str(value.id) if isinstance(value, Element) else value


def create(kind: str, temp_ref: str | None = None, **fields: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"op": "create", "kind": kind, "fields": fields}
    if temp_ref is not None:
        item["tempRef"] = temp_ref
    return item


def type_binding(
    subject: Element | str, binding: dict[str, Any], temp_ref: str | None = None
) -> dict[str, Any]:
    return create("type_binding", temp_ref, subjectRef=ref(subject), binding=binding)


def property_binding(subject: Element | str, parent: Element | str, column: str) -> dict[str, Any]:
    return create(
        "property_binding",
        subjectRef=ref(subject),
        parentRef=ref(parent),
        binding={"target": "column", "column": column},
    )


def relation_binding(
    subject: Element | str,
    domain: Element | str,
    range_: Element | str,
    binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return create(
        "relation_binding",
        subjectRef=ref(subject),
        domainRef=ref(domain),
        rangeRef=ref(range_),
        binding=binding if binding is not None else foreign_key(),
    )


def change(op: str, target: Element, **fields: Any) -> dict[str, Any]:
    return {
        "op": op,
        "kind": target.kind,
        "targetElementId": str(target.id),
        "targetRevision": target.revision,
        "fields": fields,
    }


async def save(
    client: AsyncClient, ontology: Ontology, items: list[dict[str, Any]], *, apply: bool = True
) -> Response:
    return await client.post(
        f"/api/ontologies/{ontology.id}/edits",
        json={"items": items, "apply": apply},
        headers=csrf_headers(client),
    )


def the_heat_bindings(s: Steel) -> list[dict[str, Any]]:
    """炉次 and 浇次 to their tables, 重量 and 外部编号 to columns, 对应浇次 to the foreign key."""
    return [
        type_binding(s.heat, table(s.mes), "heat"),
        type_binding(s.cast, table(s.mes, "cast", ["cast_no"]), "cast"),
        property_binding(s.weight, "heat", "weight_t"),
        property_binding(s.external_id, "heat", "heat_no"),
        relation_binding(s.in_cast, "heat", "cast"),
    ]


async def bind(client: AsyncClient, s: Steel) -> None:
    response = await save(client, s.ontology, the_heat_bindings(s))
    assert response.status_code == 200, response.json()
    assert response.json()["merged"] is True


async def bindings(db: AsyncSession, ontology: Ontology, *, active: bool = True) -> list[Element]:
    """The ontology's binding elements, read afresh."""
    rows = await db.scalars(
        select(Element)
        .where(Element.ontology_id == ontology.id, Element.kind.in_(BINDING_KINDS))
        .execution_options(populate_existing=True)
    )
    return [row for row in rows if not active or row.status == "active"]


async def fresh(db: AsyncSession, row: Element) -> Element:
    found = await db.scalar(
        select(Element).where(Element.id == row.id).execution_options(populate_existing=True)
    )
    assert found is not None
    return found


async def admin_id(db: AsyncSession) -> UUID:
    found = await db.scalar(select(User.id).where(User.username == ADMIN_USERNAME))
    assert found is not None
    return found
