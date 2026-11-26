"""Data bindings in releases, comparisons, impact, imports and the read interfaces for other
modules (spec 003, 6.4 to 6.6, and the snapshot side of section 15)."""

import re
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from rdflib import Graph, URIRef
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import bindings as ontology_bindings
from ontology_platform.modules.ontology import expert, importing, service
from ontology_platform.modules.ontology.models import Element, Release
from support import csrf_headers
from test_ontology_bindings_support import (
    Steel,
    admin_id,
    bind,
    bindings,
    change,
    foreign_key,
    fresh,
    property_binding,
    save,
    steel,
    table,
    the_heat_bindings,
)
from test_ontology_support import accept_and_merge, change_set_items, publish, sign_in


async def _snapshot(db: AsyncSession, release_id: str) -> list[dict[str, Any]]:
    rows = await db.scalar(select(Release.snapshot).where(Release.id == UUID(release_id)))
    assert rows is not None
    return rows


def _without_version(turtle: str) -> str:
    """The release's Turtle without the lines that name its version and date."""
    return "\n".join(
        line
        for line in turtle.splitlines()
        if not re.search(r"versionInfo|versionIRI|dcterms:created|dcterms:modified", line)
    )


async def _bound_and_published(client: AsyncClient, db: AsyncSession) -> tuple[Steel, Any]:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    published = await publish(client, s.ontology)
    assert published.status_code == 201, published.json().get("problems")
    return s, published.json()


async def test_a_release_holds_its_bindings_but_not_in_its_turtle(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    export_before = await client.get(f"/api/ontologies/{s.ontology.id}/export")
    first = (await publish(client, s.ontology)).json()

    await bind(client, s)
    export_after = await client.get(f"/api/ontologies/{s.ontology.id}/export")
    second = (await publish(client, s.ontology, "绑定")).json()

    assert export_after.content == export_before.content
    assert (first["elementCount"], first["bindingCount"]) == (9, 0)
    assert (second["elementCount"], second["bindingCount"]) == (9, 5)
    turtles = [
        (await client.get(f"/api/releases/{release['id']}/export")).text
        for release in (first, second)
    ]
    assert _without_version(turtles[1]) == _without_version(turtles[0])
    assert "heat_no" not in turtles[1]
    snapshot = await _snapshot(db, second["id"])
    kinds = [row["kind"] for row in snapshot]
    assert kinds.count("type_binding") == 2
    assert kinds.count("property_binding") == 2
    assert kinds.count("relation_binding") == 1
    heat_binding = next(row for row in snapshot if row["subjectId"] == str(s.heat.id))
    assert heat_binding["binding"] == table(s.mes)
    assert heat_binding["localName"] is None and heat_binding["iri"] is None


async def test_bindings_reach_a_release_only_once_merged_and_published(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    first = (await publish(client, s.ontology)).json()

    pending = await save(client, s.ontology, the_heat_bindings(s), apply=False)
    assert pending.status_code == 200, pending.json()
    while_open = (await publish(client, s.ontology, "未审核")).json()
    assert while_open["bindingCount"] == 0
    model = await ontology_bindings.bound_model(db, s.ontology.id)
    assert model is not None and model.types == ()

    await accept_and_merge(client, pending.json()["changeSetId"])
    merged_only = await ontology_bindings.bound_model(db, s.ontology.id)
    assert merged_only is not None and merged_only.types == ()

    published = (await publish(client, s.ontology, "绑定")).json()
    model = await ontology_bindings.bound_model(db, s.ontology.id)
    assert published["bindingCount"] == 5
    assert model is not None and model.version == published["version"]
    assert {bound.type_id for bound in model.types} == {s.heat.id, s.cast.id}

    activated = await client.post(
        f"/api/releases/{first['id']}/activate", headers=csrf_headers(client)
    )
    assert activated.status_code == 200, activated.json()
    rolled_back = await ontology_bindings.bound_model(db, s.ontology.id)
    assert rolled_back is not None and rolled_back.version == first["version"]
    assert rolled_back.types == () and rolled_back.relations == ()


async def test_without_a_release_there_is_no_bound_model(db: AsyncSession) -> None:
    s = await steel(db)

    assert await ontology_bindings.bound_model(db, s.ontology.id) is None
    assert await ontology_bindings.released_ontology(db, s.ontology.id) is None


async def test_the_bound_model_describes_the_release_in_effect(
    client: AsyncClient, db: AsyncSession
) -> None:
    s, release = await _bound_and_published(client, db)
    # Later edits of the working version do not reach the model.
    weight = next(row for row in await bindings(db, s.ontology) if row.subject_id == s.weight.id)
    assert (await save(client, s.ontology, [change("delete", weight)])).status_code == 200

    model = await ontology_bindings.bound_model(db, s.ontology.id)

    assert model is not None
    assert (model.ontology_id, str(model.release_id), model.version) == (
        s.ontology.id,
        release["id"],
        release["version"],
    )
    heat = model.type(s.heat.id)
    assert heat is not None
    assert (heat.label, heat.local_name, heat.data_source_id) == ("炉次", "Heat", s.mes.id)
    assert (heat.schema, heat.table, heat.key_columns) == ("mes", "heat", ("heat_no",))
    assert [(p.property_id, p.label, p.datatype, p.column) for p in heat.properties] == [
        (s.external_id.id, "外部编号", "string", "heat_no"),
        (s.weight.id, "重量", "decimal", "weight_t"),
    ]
    [relation] = model.relations
    assert (relation.relation_id, relation.label) == (s.in_cast.id, "对应浇次")
    assert (relation.source_type_id, relation.target_type_id) == (s.heat.id, s.cast.id)
    assert relation.join == ontology_bindings.ForeignKeyHop(
        side="source", columns=("cast_no",), references=("cast_no",)
    )
    assert model.type(s.batch.id) is None


async def test_the_released_ontology_is_the_semantic_part_of_the_release(
    client: AsyncClient, db: AsyncSession
) -> None:
    s, release = await _bound_and_published(client, db)

    by_id = await ontology_bindings.released_ontology(db, s.ontology.id)
    by_key = await ontology_bindings.released_ontology(db, s.ontology.key)

    assert by_id is not None and by_id == by_key
    assert (by_id.key, by_id.name, by_id.version) == ("steel", "钢铁冶金", release["version"])
    assert len(by_id.elements) == 9
    assert all(element.binding is None for element in by_id.elements)
    assert by_id.bound_type_ids == frozenset({s.heat.id, s.cast.id})
    assert await ontology_bindings.released_ontology(db, "nothing") is None


async def test_publishing_checks_the_bindings(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    # 重量 moves to 浇次 behind the binding's back: 炉次's table no longer fits it.
    await db.execute(
        update(Element).where(Element.id == s.weight.id).values(domain_id=s.cast.id)
    )
    await db.commit()
    weight = next(row for row in await bindings(db, s.ontology) if row.subject_id == s.weight.id)

    response = await publish(client, s.ontology)

    assert response.status_code == 422
    assert response.json()["problems"] == [
        {
            "code": "release.invalid_binding",
            "elementId": str(weight.id),
            "message": response.json()["problems"][0]["message"],
        }
    ]


async def test_comparing_rates_binding_changes(client: AsyncClient, db: AsyncSession) -> None:
    s, release = await _bound_and_published(client, db)
    rows = await bindings(db, s.ontology)
    heat = next(row for row in rows if row.subject_id == s.heat.id)
    weight = next(row for row in rows if row.subject_id == s.weight.id)
    response = await save(
        client,
        s.ontology,
        [
            change("update", heat, binding=table(s.mes, keys=["heat_no", "batch"])),
            change("delete", weight),
            property_binding(s.batch_code, heat, "batch"),
        ],
    )
    assert response.status_code == 200, response.json()

    compared = await client.get(
        f"/api/ontologies/{s.ontology.id}/compare", params={"from": release["id"]}
    )

    assert compared.status_code == 200, compared.json()
    changes = {
        (change["kind"], change["change"]): change for change in compared.json()["changes"]
    }
    assert set(changes) == {
        ("type_binding", "changed"),
        ("property_binding", "removed"),
        ("property_binding", "added"),
    }
    changed = changes[("type_binding", "changed")]
    assert (changed["level"], changed["label"], changed["iri"]) == (
        "review",
        "炉次 → mes.heat",
        None,
    )
    assert [field["field"] for field in changed["fields"]] == ["binding"]
    assert changes[("property_binding", "removed")]["level"] == "breaking"
    assert changes[("property_binding", "removed")]["label"] == "重量 → mes.heat.weight_t"
    assert changes[("property_binding", "added")]["level"] == "compatible"
    assert compared.json()["counts"] == {"breaking": 1, "review": 1, "compatible": 1}


async def test_impact_lists_the_bindings(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    rows = {row.subject_id: row for row in await bindings(db, s.ontology)}

    heat = await client.get(f"/api/ontologies/{s.ontology.id}/elements/{s.heat.id}/impact")
    weight = await client.get(f"/api/ontologies/{s.ontology.id}/elements/{s.weight.id}/impact")

    assert heat.status_code == 200, heat.json()
    assert heat.json()["bindings"] == [
        {
            "id": str(rows[s.heat.id].id),
            "kind": "type_binding",
            "label": "炉次 → mes.heat",
            "iri": None,
        }
    ]
    cascade = {(c["op"], c["element"]["kind"], c["element"]["id"]) for c in heat.json()["cascade"]}
    assert {
        ("delete", "type_binding", str(rows[s.heat.id].id)),
        ("delete", "property_binding", str(rows[s.weight.id].id)),
        ("delete", "property_binding", str(rows[s.external_id.id].id)),
        ("delete", "relation_binding", str(rows[s.in_cast.id].id)),
    } <= cascade
    assert [ref["kind"] for ref in weight.json()["bindings"]] == ["property_binding"]


async def test_imports_and_turtle_edits_leave_bindings_alone(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    turtle = (await client.get(f"/api/ontologies/{s.ontology.id}/export")).text
    actor = await admin_id(db)

    same = await importing.import_into(
        db, s.ontology.id, data=turtle.encode(), filename="steel.ttl", actor=actor, ip=None
    )
    edited = await expert.save_turtle(db, s.ontology.id, turtle, actor=actor, ip=None)

    assert same.change_set_id is None
    assert edited.change_set_id is None
    assert len(await bindings(db, s.ontology)) == 5


async def test_an_import_that_drops_a_bound_element_drops_its_binding(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    response = await save(
        client,
        s.ontology,
        [
            *the_heat_bindings(s),
            property_binding(s.remark, "heat", "remark"),
        ],
    )
    assert response.status_code == 200, response.json()
    remark_binding = next(
        row for row in await bindings(db, s.ontology) if row.subject_id == s.remark.id
    )
    graph = Graph().parse(
        data=(await client.get(f"/api/ontologies/{s.ontology.id}/export")).text, format="turtle"
    )
    remark = URIRef(s.ontology.base_iri + "remark")
    for triple in list(graph.triples((remark, None, None))):
        graph.remove(triple)

    imported = await importing.import_into(
        db,
        s.ontology.id,
        data=graph.serialize(format="turtle").encode(),
        filename="steel.ttl",
        actor=await admin_id(db),
        ip=None,
    )

    assert imported.change_set_id is not None
    items = await change_set_items(client, imported.change_set_id)
    assert sorted((item["op"], item["kind"], item["targetElementId"]) for item in items) == [
        ("delete", "property", str(s.remark.id)),
        ("delete", "property_binding", str(remark_binding.id)),
    ]
    merged = await accept_and_merge(client, imported.change_set_id)
    assert merged["skipped"] == []
    assert (await fresh(db, remark_binding)).status == "deprecated"
    assert (await fresh(db, s.remark)).status == "deprecated"


async def test_the_binding_kinds_are_listed_only_when_asked_for(db: AsyncSession) -> None:
    s = await steel(db)

    listed = await service.list_elements(db, s.ontology.id, kind=None, q=None)

    assert {element.kind for element in listed} == {"entity_type", "property", "relation_type"}


async def test_the_binding_view_of_a_type_checks_the_catalog(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    rows = {row.subject_id: row for row in await bindings(db, s.ontology)}
    # The column of 外部编号 is renamed in the data source since the catalog was read.
    await db.execute(
        update(Element)
        .where(Element.id == rows[s.external_id.id].id)
        .values(binding={"target": "column", "column": "heat_id"})
    )
    await db.commit()
    pending = await save(
        client, s.ontology, [property_binding(s.batch_code, rows[s.heat.id], "batch")], apply=False
    )
    assert pending.status_code == 200, pending.json()

    [heat] = await ontology_bindings.binding_views(db, s.ontology.id, s.heat.id)
    every = await ontology_bindings.binding_views(db, s.ontology.id, None)
    batch = await ontology_bindings.binding_views(db, s.ontology.id, s.batch.id)

    assert [view.type_id for view in every] == [s.cast.id, s.heat.id]  # 浇次, 炉次
    assert heat.table is not None
    assert (heat.table.data_source.name, heat.table.table, heat.table.check) == (
        "MES",
        "heat",
        "ok",
    )
    assert heat.table.key_columns == ["heat_no"]
    by_property = {p.property_id: p for p in heat.properties}
    assert set(by_property) == {s.weight.id, s.external_id.id, s.batch_code.id, s.remark.id}
    weight = by_property[s.weight.id]
    assert weight.inherited is False and weight.column is not None
    assert (weight.column.column, weight.column.column_type, weight.column.check) == (
        "weight_t",
        "numeric(8,2)",
        "ok",
    )
    renamed = by_property[s.external_id.id].column
    assert renamed is not None and renamed.check == "missing_column"
    assert by_property[s.batch_code.id].inherited is True
    assert by_property[s.batch_code.id].column is None
    [relation] = heat.relations
    assert (relation.relation_id, relation.direction, relation.other_type_id) == (
        s.in_cast.id,
        "out",
        s.cast.id,
    )
    assert relation.join is not None and relation.join.check == "ok"
    assert heat.open_change_set_ids == [UUID(pending.json()["changeSetId"])]
    [cast_view] = [view for view in every if view.type_id == s.cast.id]
    assert [r.direction for r in cast_view.relations] == ["in"]
    assert cast_view.open_change_set_ids == []
    assert batch[0].table is None


async def test_the_binding_view_is_read_by_any_signed_in_user(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    url = f"/api/ontologies/{s.ontology.id}/bindings"
    created = await client.post(
        "/api/auth/tokens",
        json={"name": "agent", "scopes": ["ontology:read", "objects:read"]},
        headers=csrf_headers(client),
    )
    assert created.status_code == 201, created.json()
    client.cookies.clear()

    anonymous = await client.get(url)
    by_token = await client.get(url, headers={"Authorization": f"Bearer {created.json()['token']}"})
    await sign_in(client, db, Role.VIEWER)
    every = await client.get(url)
    one = await client.get(url, params={"typeId": str(s.batch.id)})
    not_a_type = await client.get(url, params={"typeId": str(s.weight.id)})

    assert (anonymous.status_code, anonymous.json()["code"]) == (401, "auth.not_authenticated")
    assert (by_token.status_code, by_token.json()["code"]) == (403, "auth.token_not_allowed")
    assert every.status_code == 200, every.json()
    assert [view["typeId"] for view in every.json()] == [str(s.cast.id), str(s.heat.id)]
    heat = every.json()[1]
    assert heat["table"]["dataSource"] == {"id": str(s.mes.id), "name": "MES", "status": "active"}
    assert (heat["table"]["schema"], heat["table"]["check"]) == ("mes", "ok")
    assert heat["relations"][0]["join"]["join"] == foreign_key()["join"]
    assert one.status_code == 200
    assert one.json()[0]["table"] is None
    assert (not_a_type.status_code, not_a_type.json()["code"]) == (404, "element.not_found")
