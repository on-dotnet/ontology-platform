"""Public query errors and per-type availability against a published catalog."""

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.engine import Engine, ExceptionContext
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.connectors import connection
from ontology_platform.modules.connectors.errors import (
    ConnectorError,
    InvalidValueError,
    QueryTimeoutError,
    SourceBusyError,
    SourceUnavailableError,
)
from ontology_platform.modules.connectors.models import CatalogTable
from ontology_platform.modules.identity.models import Role
from support import csrf_headers
from test_connectors_support import (
    add_source,
    admin_rows,
    cache_table,
    external_statements,
    scratch_fixture,  # noqa: F401  (registers the fixture)
)
from test_ontology_bindings_support import (
    bindings,
    change,
    foreign_key,
    relation_binding,
    save,
    table,
    type_binding,
)
from test_ontology_support import add_elements, element, publish, sign_in
from test_query_support import QueryCatalog, assert_problem, make_catalog, publish_bindings, search


@contextmanager
def _sqlstates_for(table_name: str) -> Iterator[list[str | None]]:
    states: list[str | None] = []

    def record(context: ExceptionContext) -> None:
        if context.statement and table_name in context.statement:
            states.append(getattr(context.original_exception, "sqlstate", None))

    event.listen(Engine, "handle_error", record)
    try:
        yield states
    finally:
        event.remove(Engine, "handle_error", record)


async def _assert_isolated(client: AsyncClient, catalog: QueryCatalog, problem: str) -> None:
    with external_statements() as statements:
        listed = await client.get(f"{catalog.url}/types")
        assert listed.status_code == 200, listed.json()
        assert {t["typeId"]: t["problem"] for t in listed.json()["items"]} == {
            str(catalog.coil.id): problem,
            str(catalog.inspection.id): None,
        }
        denied = await search(client, catalog, catalog.coil)
        assert_problem(denied, 409, f"query.{problem}")
    assert statements == []
    healthy = await search(client, catalog, catalog.inspection, limit=1)
    assert healthy.status_code == 200, healthy.json()
    [row] = healthy.json()["items"]
    assert row["source"]["table"] == "quality_inspection"


@pytest.mark.parametrize("missing", ["table", "coil_no", "status"])
async def test_missing_cached_table_or_bound_column_only_disables_its_type(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, missing: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    cached = await db.get(CatalogTable, (catalog.source.id, "mes", "coil"))
    assert cached is not None
    if missing == "table":
        await db.delete(cached)
    else:
        assert missing in {c["name"] for c in cached.columns}
        cached.columns = [c for c in cached.columns if c["name"] != missing]
    await db.commit()
    await _assert_isolated(client, catalog, "source_mismatch")


@pytest.mark.parametrize("disabled", ["archived", "missing_credential"])
async def test_disabled_source_does_not_hide_types_of_another_source(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, disabled: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    other = await add_source(db, external_source)
    await cache_table(db, other.id, external_source, "mes", "quality_inspection")
    items = [*catalog.coil_bindings(), catalog.inspection_binding(other)]
    original = await publish_bindings(client, catalog, items)
    if disabled == "archived":
        # Archive while unused, then reactivate the snapshot that still refers to this source.
        working = await bindings(db, catalog.ontology)
        coil = next(b for b in working if b.subject_id == catalog.coil.id)
        status = next(b for b in working if b.subject_id == catalog.status.id)
        assert status.parent_id == coil.id
        removed = await save(
            client, catalog.ontology, [change("delete", status), change("delete", coil)]
        )
        assert removed.status_code == 200, removed.json()
        assert removed.json()["merged"] is True
        assert removed.json()["merge"] == {"applied": 2, "skipped": []}
        unbound = await publish(client, catalog.ontology, "解除钢卷绑定")
        assert unbound.status_code == 201, unbound.json()
        assert unbound.json()["bindingCount"] == 1
        archived = await client.post(
            f"/api/data-sources/{catalog.source.id}/archive", headers=csrf_headers(client)
        )
        assert archived.status_code == 200, archived.json()
        assert archived.json()["status"] == "archived"
        activated = await client.post(
            f"/api/releases/{original}/activate", headers=csrf_headers(client)
        )
        assert activated.status_code == 200, activated.json()
        assert activated.json()["id"] == original
        assert activated.json()["isActive"] is True
    else:
        catalog.source.secret = catalog.source.secret_key_id = None
        await db.commit()
    await _assert_isolated(client, catalog, "source_disabled")


async def test_unreadable_saved_credential_is_a_disabled_source(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    catalog.source.secret = b"invalid sealed credential"
    await db.commit()
    response = await search(client, catalog, catalog.coil)
    assert_problem(response, 409, "query.source_disabled")


async def test_unknown_enum_label_is_rejected_by_the_database(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    value = "no-such-coil-status"
    with external_statements() as statements:
        response = await search(
            client,
            catalog,
            catalog.coil,
            filters=[{"propertyId": str(catalog.status.id), "op": "eq", "value": value}],
        )
    assert_problem(response, 422, "query.invalid_filter")
    [(sql, params)] = [(s, p) for s, p in statements if "mes.coil" in s.replace('"', "").lower()]
    assert value not in sql
    assert value in repr(params)
    assert value not in response.text
    assert "invalid input value for enum" not in response.text.lower()


async def test_retired_enum_primary_key_is_not_found_for_detail_and_one_hop(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    enum = f'"{scratch}".inspection_kind'
    inspections = f'"{scratch}".enum_inspection'
    admin_rows(external_source, f"CREATE TYPE {enum} AS ENUM ('initial')")
    admin_rows(
        external_source,
        f"CREATE TABLE {inspections} (inspection_id {enum} PRIMARY KEY, coil_no varchar NOT NULL)",
    )
    admin_rows(
        external_source,
        f"INSERT INTO {inspections} SELECT 'initial', coil_no FROM mes.coil LIMIT 1",  # noqa: S608
    )
    admin_rows(external_source, f'GRANT SELECT ON {inspections} TO "{external_source.reader}"')
    await cache_table(db, catalog.source.id, external_source, scratch, "enum_inspection")
    target = {**table(catalog.source, "enum_inspection", ["inspection_id"]), "schema": scratch}
    await publish_bindings(
        client,
        catalog,
        [
            *catalog.coil_bindings(),
            type_binding(catalog.inspection, target, "inspection"),
            relation_binding(
                catalog.inspected_coil, "inspection", "coil", foreign_key(["coil_no"], ["coil_no"])
            ),
        ],
    )
    page = await search(client, catalog, catalog.inspection)
    assert page.status_code == 200, page.json()
    [row] = page.json()["items"]
    assert row["source"]["key"] == [{"column": "inspection_id", "value": "initial"}]
    obj = f"{catalog.url}/{catalog.inspection.id}/{row['key']}"
    related = f"{obj}/related"
    params = {"relationId": str(catalog.inspected_coil.id), "direction": "out"}
    assert (await client.get(obj)).status_code == 200
    hop = await client.get(related, params=params)
    assert hop.status_code == 200, hop.json()
    assert len(hop.json()["items"]) == 1

    # The URL and stored row remain valid; PostgreSQL now rejects the old label in the key.
    admin_rows(external_source, f"ALTER TYPE {enum} RENAME VALUE 'initial' TO 'renamed'")
    with _sqlstates_for("enum_inspection") as states:
        assert_problem(await client.get(obj), 404, "query.object_not_found")
        assert_problem(await client.get(related, params=params), 404, "query.object_not_found")
    assert states == ["22P02", "22P02"]


async def test_invalid_filters_are_rejected_before_external_sql(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    width = element(
        catalog.ontology,
        "property",
        "widthMm",
        "宽度",
        domain_id=catalog.coil.id,
        datatype="integer",
    )
    await add_elements(db, width)
    await publish_bindings(client, catalog)
    with external_statements() as statements:
        listed = await client.get(f"{catalog.url}/types")
        assert listed.status_code == 200, listed.json()
        coil = next(t for t in listed.json()["items"] if t["typeId"] == str(catalog.coil.id))
        [prop] = coil["properties"]
        assert prop["propertyId"] == str(catalog.status.id)
        assert set(prop["ops"]) == {"eq", "ne", "in", "isNull", "notNull"}
        for property_id, op, value in [
            (catalog.status.id, "contains", "ship"),
            (width.id, "eq", 1200),
            (catalog.status.id, "in", ["produced"] * 101),
            (catalog.status.id, "eq", {"unexpected": "shape"}),
            (catalog.status.id, "unknown", "produced"),
        ]:
            response = await search(
                client,
                catalog,
                catalog.coil,
                filters=[{"propertyId": str(property_id), "op": op, "value": value}],
            )
            assert_problem(response, 422, "query.invalid_filter")
        sorted_by_unbound = await search(
            client, catalog, catalog.coil, sort=[{"propertyId": str(width.id), "direction": "asc"}]
        )
        assert_problem(sorted_by_unbound, 422, "query.invalid_filter")
    assert statements == []


async def test_a_view_failing_at_runtime_reports_mismatch(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    view = f'"{scratch}".coil_view'
    working_query = "SELECT coil_no, status::text AS status FROM mes.coil"
    admin_rows(external_source, f"CREATE VIEW {view} AS {working_query}")
    admin_rows(external_source, f'GRANT SELECT ON {view} TO "{external_source.reader}"')
    await cache_table(db, catalog.source.id, external_source, scratch, "coil_view")
    await publish_bindings(client, catalog, catalog.bindings(scratch, "coil_view"))
    coils = await search(client, catalog, catalog.coil, limit=1)
    inspections = await search(client, catalog, catalog.inspection, limit=1)
    assert coils.status_code == inspections.status_code == 200
    [coil] = coils.json()["items"]
    [inspection] = inspections.json()["items"]
    obj = f"{catalog.url}/{catalog.coil.id}/{coil['key']}"
    related = f"{catalog.url}/{catalog.inspection.id}/{inspection['key']}/related"
    params = {"relationId": str(catalog.inspected_coil.id), "direction": "out"}
    assert (await client.get(obj)).status_code == 200
    hop = await client.get(related, params=params)
    assert hop.status_code == 200, hop.json()
    assert len(hop.json()["items"]) == 1
    admin_rows(external_source, f"CREATE OR REPLACE VIEW {view} AS {working_query} WHERE false")
    assert_problem(await client.get(obj), 404, "query.object_not_found")

    duplicates = f"{working_query} UNION ALL {working_query}"
    admin_rows(external_source, f"CREATE OR REPLACE VIEW {view} AS {duplicates}")
    assert_problem(await client.get(obj), 409, "query.source_mismatch")

    for projection, sqlstate, driver_detail in [
        ("(width_mm / (width_mm - width_mm))::text", "22012", "division by zero"),
        ("status::text::integer::text", "22P02", "invalid input syntax for type integer"),
    ]:
        failing_query = f"SELECT coil_no, {projection} AS status FROM mes.coil"  # noqa: S608
        admin_rows(external_source, f"CREATE OR REPLACE VIEW {view} AS {failing_query}")
        with _sqlstates_for("coil_view") as states:
            for response in [
                await search(client, catalog, catalog.coil),
                await client.get(obj),
                await client.get(related, params=params),
            ]:
                assert_problem(response, 409, "query.source_mismatch")
                assert driver_detail not in response.text.lower()
                assert scratch not in response.text
            filtered = await search(
                client,
                catalog,
                catalog.coil,
                filters=[{"propertyId": str(catalog.status.id), "op": "notNull"}],
            )
            assert_problem(filtered, 422, "query.invalid_filter")
        assert states == [sqlstate] * 4


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (SourceBusyError, 503, "query.busy"),
        (QueryTimeoutError, 504, "query.timeout"),
        (SourceUnavailableError, 502, "query.source_unavailable"),
        (InvalidValueError, 409, "query.source_mismatch"),
    ],
)
async def test_unfiltered_search_maps_connector_failures(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    monkeypatch: pytest.MonkeyPatch,
    error: type[ConnectorError],
    status: int,
    code: str,
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    failure = error()
    failure.args = ("private-driver-detail",)
    select = AsyncMock(side_effect=failure)
    monkeypatch.setattr(connection, "run_select", select)
    response = await search(client, catalog, catalog.coil)
    select.assert_awaited_once()
    assert_problem(response, status, code)
    assert "private-driver-detail" not in response.text


async def test_key_errors_depend_on_the_failed_condition(
    client: AsyncClient,
    db: AsyncSession,
    external_source: ExternalSource,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    page = await search(client, catalog, catalog.inspection, limit=1)
    assert page.status_code == 200, page.json()
    [row] = page.json()["items"]
    obj = f"{catalog.url}/{catalog.inspection.id}/{row['key']}"
    for column, sqlstate, status, code in [
        ("inspection_id", "22P02", 404, "query.object_not_found"),
        ("status", "22P02", 409, "query.source_mismatch"),
        (None, "22P02", 409, "query.source_mismatch"),
        (None, "22012", 409, "query.source_mismatch"),
    ]:
        select = AsyncMock(side_effect=InvalidValueError(column=column, sqlstate=sqlstate))
        monkeypatch.setattr(connection, "run_select", select)
        detail = await client.get(obj)
        related = await client.get(
            f"{obj}/related", params={"relationId": str(catalog.inspected_coil.id)}
        )
        assert select.await_count == 2
        assert_problem(detail, status, code)
        assert_problem(related, status, code)


async def test_malformed_key_and_cursor_and_changed_release(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    await publish_bindings(client, catalog)
    with external_statements() as statements:
        obj = await client.get(f"{catalog.url}/{catalog.coil.id}/!!!")
        assert_problem(obj, 404, "query.object_not_found")
        invalid = await search(client, catalog, catalog.coil, cursor="!!!")
        assert_problem(invalid, 422, "query.invalid_cursor")
    assert statements == []
    first = await search(client, catalog, catalog.coil, limit=1)
    assert first.status_code == 200, first.json()
    cursor = first.json()["nextCursor"]
    assert cursor
    changed_type = await search(client, catalog, catalog.inspection, cursor=cursor)
    assert_problem(changed_type, 422, "query.invalid_cursor")
    released = await publish(client, catalog.ontology, "第二版")
    assert released.status_code == 201, released.json()
    assert released.json()["id"] != first.json()["release"]["id"]
    outdated = await search(client, catalog, catalog.coil, limit=1, cursor=cursor)
    assert_problem(outdated, 409, "query.release_changed")


async def test_a_missing_ontology_is_distinct_from_an_unpublished_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.VIEWER)
    response = await client.get(f"/api/ontologies/{uuid4()}/objects/types")
    assert_problem(response, 404, "ontology.not_found")
