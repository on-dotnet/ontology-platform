"""Published bindings govern which external data an object query can read."""

import re
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from external_source import ExternalSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.metrics import service as metrics_service
from support import csrf_headers
from test_connectors_support import (
    admin_rows,
    cache_table,
    external_statements,
    scratch_fixture,  # noqa: F401  (registers the fixture)
)
from test_ontology_bindings_support import property_binding, save, table, type_binding
from test_ontology_editing import create
from test_ontology_editing import save as save_edit
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    change_set_items,
    element,
    elements_by_name,
    publish,
    sign_in,
)
from test_query_support import QueryCatalog, assert_problem, make_catalog, publish_bindings, search


async def test_datetime_property_on_date_column_filters_search_and_metric(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    target = f'"{scratch}".dated_coil'
    admin_rows(external_source, f"CREATE TABLE {target} (coil_no text PRIMARY KEY, made date)")
    admin_rows(external_source, f'GRANT SELECT ON {target} TO "{external_source.reader}"')
    for key, day in (("A", "2026-01-01"), ("B", "2026-01-02")):
        admin_rows(external_source, f"INSERT INTO {target} VALUES (%s, %s)", key, day)  # noqa: S608
    await cache_table(db, catalog.source.id, external_source, scratch, "dated_coil")
    made = element(
        catalog.ontology,
        "property",
        "madeAt",
        "日期时间",
        domain_id=catalog.coil.id,
        datatype="dateTime",
    )
    await add_elements(db, made)
    saved = await save_edit(
        client,
        catalog.ontology,
        create(
            "metric",
            "firstDayCount",
            "首日数量",
            subjectRef=str(catalog.coil.id),
            metric={
                "aggregate": "count",
                "filters": [
                    {"propertyRef": str(made.id), "op": "eq", "value": "2026-01-01T00:00:00"}
                ],
            },
        ),
        create(
            "metric",
            "firstDayUtcCount",
            "首日 UTC 数量",
            subjectRef=str(catalog.coil.id),
            metric={
                "aggregate": "count",
                "filters": [
                    {"propertyRef": str(made.id), "op": "eq", "value": "2026-01-01T02:00:00+02:00"}
                ],
            },
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["merged"]
    bound_table = table(catalog.source, "dated_coil", ["coil_no"])
    bound_table["schema"] = scratch
    await publish_bindings(
        client,
        catalog,
        [type_binding(catalog.coil, bound_table, "coil"), property_binding(made, "coil", "made")],
    )
    for raw in ("2026-01-01T00:00:00", "2026-01-01T00:00:00Z", "2026-01-01"):
        page = await search(
            client,
            catalog,
            catalog.coil,
            filters=[{"propertyId": str(made.id), "op": "eq", "value": raw}],
        )
        assert page.status_code == 200, page.text
        assert [row["source"]["key"][0]["value"] for row in page.json()["items"]] == ["A"]
    # The time of day counts: a date is that day's midnight, not the whole day.
    for op, raw, expected in (
        ("ge", "2026-01-01T10:00:00", ["B"]),
        ("eq", "2026-01-01T10:00:00", []),
        ("lt", "2026-01-01T10:00:00+02:00", ["A"]),
    ):
        page = await search(
            client,
            catalog,
            catalog.coil,
            filters=[{"propertyId": str(made.id), "op": op, "value": raw}],
        )
        assert page.status_code == 200, page.text
        keys = [row["source"]["key"][0]["value"] for row in page.json()["items"]]
        assert keys == expected, (op, raw)
    metrics = await elements_by_name(db, catalog.ontology)
    for name in ("firstDayCount", "firstDayUtcCount"):
        result = await metrics_service.evaluate(db, catalog.ontology.id, metrics[name].id)
        assert (result.population, result.value) == (1, "1")


async def test_nothing_is_queried_before_a_release(client: AsyncClient, db: AsyncSession) -> None:
    steel = await add_ontology(db)
    await add_elements(db, element(steel, "entity_type", "Heat", "炉次"))
    await db.commit()
    await sign_in(client, db, Role.VIEWER)

    with external_statements() as statements:
        response = await client.get(f"/api/ontologies/{steel.id}/objects/types")

    assert_problem(response, 409, "query.no_release")
    assert statements == []


async def _assert_coil_unbound(client: AsyncClient, catalog: QueryCatalog) -> None:
    with external_statements() as statements:
        response = await search(client, catalog, catalog.coil)
    assert_problem(response, 409, "query.type_not_bound")
    assert statements == []


async def test_bindings_only_expose_columns_of_the_active_release(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource
) -> None:
    catalog = await make_catalog(client, db, external_source)
    old = await publish(client, catalog.ontology)
    assert old.status_code == 201, old.json()
    items = catalog.coil_bindings()
    await sign_in(client, db, Role.EDITOR)
    pending = await save(client, catalog.ontology, items, apply=False)
    assert pending.status_code == 200, pending.json()
    assert pending.json()["merged"] is False
    change_set_id = UUID(pending.json()["changeSetId"])
    decisions = await change_set_items(client, change_set_id)
    assert [item["decision"] for item in decisions] == ["pending"] * len(items)
    await _assert_coil_unbound(client, catalog)

    await sign_in(client, db, Role.REVIEWER)
    merged = await accept_and_merge(client, change_set_id)
    assert merged == {"applied": len(items), "skipped": []}
    await _assert_coil_unbound(client, catalog)
    await sign_in(client, db, Role.ADMIN)
    active = await publish(client, catalog.ontology, "发布钢卷绑定")
    assert active.status_code == 201, active.json()
    release = {k: active.json()[k] for k in ("id", "version")}

    await sign_in(client, db, Role.VIEWER)
    [(number, status)] = admin_rows(
        external_source, "SELECT coil_no, status::text FROM mes.coil ORDER BY coil_no LIMIT 1"
    )
    with external_statements() as statements:
        page = await search(client, catalog, catalog.coil, limit=1)
        assert page.status_code == 200, page.json()
        [row] = page.json()["items"]
        detail = await client.get(f"{catalog.url}/{catalog.coil.id}/{row['key']}")
    assert page.json()["release"] == release
    assert detail.status_code == 200, detail.json()
    assert detail.json() == {**row, "release": release, "relations": []}
    assert row["values"] == {str(catalog.status.id): status}
    assert row["source"] == {
        "dataSourceId": str(catalog.source.id),
        "dataSourceName": catalog.source.name,
        "schema": "mes",
        "table": "coil",
        "key": [{"column": "coil_no", "value": number}],
    }
    normalized = [sql.lower().replace('"', "") for sql, _ in statements]
    reads = [sql for sql in normalized if "mes.coil" in sql]
    assert len(reads) == 2
    for sql in reads:
        assert "coil_no" in sql
        assert "status" in sql
        assert "*" not in sql
        assert not re.search(r"\b(rolling_id|org_id|site_id|thickness_mm|width_mm|weight_t)\b", sql)

    await sign_in(client, db, Role.ADMIN)
    activated = await client.post(
        f"/api/releases/{old.json()['id']}/activate", headers=csrf_headers(client)
    )
    assert activated.status_code == 200, activated.json()
    await sign_in(client, db, Role.VIEWER)
    await _assert_coil_unbound(client, catalog)


async def test_text_filters_compare_literal_values_and_preserve_the_source(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source, writer=True)
    target = f'"{scratch}".literal_coil'
    admin_rows(external_source, f"CREATE TABLE {target} (coil_no int PRIMARY KEY, status text)")
    admin_rows(external_source, f'GRANT USAGE ON SCHEMA "{scratch}" TO "{external_source.writer}"')
    admin_rows(external_source, f'GRANT ALL ON {target} TO "{external_source.writer}"')
    literal = "coil'; -- %_"
    values = [literal, literal + "tail", "head" + literal, "coil'; -- abc_", "coil'; -- %x"]
    insert = f"INSERT INTO {target} VALUES (%s, %s)"  # noqa: S608
    for key, value in enumerate(values, start=1):
        admin_rows(external_source, insert, key, value)
    await cache_table(db, catalog.source.id, external_source, scratch, "literal_coil")
    await publish_bindings(client, catalog, catalog.coil_bindings(scratch, "literal_coil"))
    snapshot = f"SELECT coil_no, status FROM {target} ORDER BY coil_no"  # noqa: S608
    before = admin_rows(external_source, snapshot)

    for op, keys in [("eq", ["1"]), ("startsWith", ["1", "2"]), ("contains", ["1", "2", "3"])]:
        with external_statements() as statements:
            response = await search(
                client,
                catalog,
                catalog.coil,
                filters=[{"propertyId": str(catalog.status.id), "op": op, "value": literal}],
            )
        assert response.status_code == 200, response.json()
        assert [row["source"]["key"][0]["value"] for row in response.json()["items"]] == keys
        [read] = [sql for sql, _ in statements if "literal_coil" in sql]
        assert read.lstrip().lower().startswith("select")
        assert literal not in read
    assert admin_rows(external_source, snapshot) == before


async def test_filter_operators_match_external_primary_keys(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    target = f'"{scratch}".filter_coil'
    admin_rows(
        external_source,
        f"CREATE TABLE {target} (coil_no integer PRIMARY KEY, status mes.coil_status)",
    )
    admin_rows(external_source, f'GRANT SELECT ON {target} TO "{external_source.reader}"')
    admin_rows(
        external_source,
        f"INSERT INTO {target} VALUES "  # noqa: S608
        "(1, 'shipped'), (2, NULL), (3, 'produced'), "
        "(4, 'inspected'), (5, NULL), (6, 'shipped')",
    )
    await cache_table(db, catalog.source.id, external_source, scratch, "filter_coil")
    number = element(
        catalog.ontology,
        "property",
        "number",
        "卷号",
        domain_id=catalog.coil.id,
        datatype="integer",
    )
    await add_elements(db, number)
    bindings = catalog.coil_bindings(scratch, "filter_coil")
    bindings.append(property_binding(number, "coil", "coil_no"))
    await publish_bindings(client, catalog, bindings)

    status = catalog.status
    for prop, condition, predicate in (
        (number, {"op": "lt", "value": 3}, "coil_no < 3"),
        (number, {"op": "in", "value": [2, 6]}, "coil_no IN (2, 6)"),
        (
            status,
            {"op": "in", "value": ["produced", "shipped"]},
            "status IN ('produced', 'shipped')",
        ),
        (status, {"op": "isNull"}, "status IS NULL"),
        (status, {"op": "notNull"}, "status IS NOT NULL"),
        (status, {"op": "ne", "value": "shipped"}, "status <> 'shipped'"),
    ):
        sql = f"SELECT coil_no FROM {target} WHERE {predicate}"  # noqa: S608
        expected = {str(key) for (key,) in admin_rows(external_source, sql)}
        assert 0 < len(expected) < 6, predicate
        response = await search(
            client,
            catalog,
            catalog.coil,
            filters=[{"propertyId": str(prop.id), **condition}],
            limit=6,
        )
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["nextCursor"] is None, predicate
        keys = [row["source"]["key"][0]["value"] for row in page["items"]]
        assert len(keys) == len(expected), predicate
        assert set(keys) == expected, predicate


async def test_exact_scalar_values_and_filters_on_the_external_table(
    client: AsyncClient, db: AsyncSession, external_source: ExternalSource, scratch: str
) -> None:
    catalog = await make_catalog(client, db, external_source)
    target = f'"{scratch}".measurements'
    admin_rows(
        external_source,
        f"CREATE TABLE {target} (coil_no bigint PRIMARY KEY, status text, "
        "mass numeric, accepted boolean, made date, measured timestamp)",
    )
    admin_rows(external_source, f'GRANT SELECT ON {target} TO "{external_source.reader}"')
    precise = "12345678901234567890.1234500"
    insert = f"INSERT INTO {target} VALUES (%s, %s, %s, %s, %s, %s)"  # noqa: S608
    admin_rows(external_source, insert, 12, None, "1.5", False, "2024-01-01", None)
    admin_rows(
        external_source,
        insert,
        2**53 + 1,
        "炉" * 2001,
        precise,
        True,
        "2024-02-29",
        "2024-02-29 17:45:12.123456",
    )
    await cache_table(db, catalog.source.id, external_source, scratch, "measurements")
    items = catalog.coil_bindings(scratch, "measurements")
    ids = {}
    for name, datatype in [
        ("number", "integer"),
        ("mass", "decimal"),
        ("accepted", "boolean"),
        ("made", "date"),
        ("measured", "dateTime"),
    ]:
        prop = element(
            catalog.ontology, "property", name, name, domain_id=catalog.coil.id, datatype=datatype
        )
        await add_elements(db, prop)
        ids[name] = str(prop.id)
        items.append(property_binding(prop, "coil", "coil_no" if name == "number" else name))
    await publish_bindings(client, catalog, items)
    listed = await client.get(f"{catalog.url}/types")
    assert listed.status_code == 200, listed.text
    [info] = listed.json()["items"]
    operations = {p["propertyId"]: set(p["ops"]) for p in info["properties"]}
    assert operations[ids["accepted"]] == {"eq", "ne", "isNull", "notNull"}
    ordered = {"eq", "ne", "lt", "le", "gt", "ge", "in", "isNull", "notNull"}
    for name in ("number", "mass", "made", "measured"):
        assert operations[ids[name]] == ordered
    assert operations[str(catalog.status.id)] == ordered | {"contains", "startsWith"}
    page = await search(
        client,
        catalog,
        catalog.coil,
        filters=[
            {"propertyId": ids["number"], "op": "gt", "value": 12},
            {"propertyId": ids["mass"], "op": "eq", "value": precise},
            {"propertyId": ids["accepted"], "op": "ne", "value": False},
            {"propertyId": ids["made"], "op": "ge", "value": "2024-02-29"},
            {"propertyId": ids["measured"], "op": "le", "value": "2024-02-29T17:45:12.123456"},
        ],
    )
    assert page.status_code == 200, page.text
    [row] = page.json()["items"]
    assert row["values"] == {
        str(catalog.status.id): "炉" * 2000,
        ids["number"]: "9007199254740993",
        ids["mass"]: precise,
        ids["accepted"]: True,
        ids["made"]: "2024-02-29",
        ids["measured"]: "2024-02-29T17:45:12.123456",
    }
    assert row["values"][ids["accepted"]] is True
    assert row["truncated"] == [str(catalog.status.id)]
    detail = await client.get(f"{catalog.url}/{catalog.coil.id}/{row['key']}")
    assert detail.status_code == 200, detail.text
    assert detail.json() == {**row, "relations": [], "release": page.json()["release"]}
