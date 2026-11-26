"""Data bindings: the rules, editing, review and merging (spec 003, 6.1 to 6.3)."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors.models import CatalogTable, DataSource
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.schemas import (
    CatalogEvidenceSource,
    ElementFields,
    EvidenceIn,
    ProposedItem,
)
from support import csrf_headers
from test_ontology_bindings_support import (
    Steel,
    admin_id,
    bind,
    bindings,
    change,
    create,
    foreign_key,
    fresh,
    link_table,
    property_binding,
    relation_binding,
    save,
    steel,
    table,
    type_binding,
)
from test_ontology_support import (
    accept_and_merge,
    add_elements,
    add_ontology,
    change_set_items,
    decide_by_seq,
    element,
    merge,
    publish,
    sign_in,
)


async def test_a_merged_and_published_binding_is_in_the_snapshot(
    client: AsyncClient, db: AsyncSession
) -> None:
    steel_ontology = await add_ontology(db)
    heat = element(steel_ontology, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)
    source = DataSource(
        id=uuid4(),
        name="MES",
        kind="postgresql",
        host="steel-mes.example",
        port=5432,
        database="steel_mes",
        username="steel_reader",
    )
    db.add(source)
    await db.flush()
    # Bindings are checked against the cached catalog when they are proposed (spec 003, 6.2).
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
    await sign_in(client, db, Role.ADMIN)

    saved = await client.post(
        f"/api/ontologies/{steel_ontology.id}/edits",
        json={
            "items": [
                {
                    "op": "create",
                    "kind": "type_binding",
                    "tempRef": "heat-table",
                    "fields": {
                        "subjectRef": str(heat.id),
                        "binding": {
                            "target": "table",
                            "dataSourceId": str(source.id),
                            "schema": "mes",
                            "table": "heat",
                            "keyColumns": ["heat_no"],
                        },
                    },
                }
            ],
            "apply": True,
        },
        headers=csrf_headers(client),
    )
    published = await publish(client, steel_ontology)

    assert saved.status_code == 200
    assert saved.json()["merged"] is True
    assert published.status_code == 201
    assert published.json()["bindingCount"] == 1


async def test_a_type_its_properties_and_relations_are_bound_in_one_save(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)

    response = await save(
        client,
        s.ontology,
        [
            type_binding(s.heat, table(s.mes), "heat"),
            type_binding(s.cast, table(s.mes, "cast", ["cast_no"]), "cast"),
            property_binding(s.weight, "heat", "weight_t"),
            property_binding(s.external_id, "heat", "heat_no"),
            # 批次号 is defined on 批次, which 炉次 is a kind of.
            property_binding(s.batch_code, "heat", "batch"),
            relation_binding(s.in_cast, "heat", "cast"),
        ],
    )

    assert response.status_code == 200, response.json()
    assert response.json()["merged"] is True
    rows = await bindings(db, s.ontology)
    by_kind: dict[str, list[Any]] = {}
    for row in rows:
        by_kind.setdefault(row.kind, []).append(row)
    heat_binding = next(row for row in by_kind["type_binding"] if row.subject_id == s.heat.id)
    cast_binding = next(row for row in by_kind["type_binding"] if row.subject_id == s.cast.id)
    assert heat_binding.binding == table(s.mes)
    assert heat_binding.local_name is None
    assert heat_binding.label_zh is None
    assert {(row.subject_id, row.parent_id) for row in by_kind["property_binding"]} == {
        (s.weight.id, heat_binding.id),
        (s.external_id.id, heat_binding.id),
        (s.batch_code.id, heat_binding.id),
    }
    [relation] = by_kind["relation_binding"]
    assert (relation.subject_id, relation.domain_id, relation.range_id) == (
        s.in_cast.id,
        heat_binding.id,
        cast_binding.id,
    )
    assert relation.binding == foreign_key()

    listed = await client.get(f"/api/ontologies/{s.ontology.id}/elements")
    assert all(row["kind"] not in by_kind for row in listed.json())
    properties = await client.get(
        f"/api/ontologies/{s.ontology.id}/elements", params={"kind": "property_binding"}
    )
    assert len(properties.json()) == 3
    assert {row["binding"]["column"] for row in properties.json()} == {
        "weight_t",
        "heat_no",
        "batch",
    }


def _heat(s: Steel, **binding: Any) -> list[dict[str, Any]]:
    return [type_binding(s.heat, {**table(s.mes), **binding}, "heat")]


def _with_cast(s: Steel, cast_source: DataSource | None = None) -> list[dict[str, Any]]:
    return [
        type_binding(s.heat, table(s.mes), "heat"),
        type_binding(s.cast, table(cast_source or s.mes, "cast", ["cast_no"]), "cast"),
    ]


_RULES: dict[str, tuple[Callable[[Steel], list[dict[str, Any]]], int, str]] = {
    "repeated key columns": (
        lambda s: _heat(s, keyColumns=["heat_no", "heat_no"]),
        422,
        "binding.invalid",
    ),
    "unknown data source": (
        lambda s: _heat(s, dataSourceId=str(uuid4())),
        422,
        "binding.invalid",
    ),
    "archived data source": (
        lambda s: [type_binding(s.heat, table(s.archived), "heat")],
        422,
        "binding.invalid",
    ),
    "table not in the catalog": (lambda s: _heat(s, table="melt"), 422, "binding.invalid"),
    "key column not in the table": (
        lambda s: _heat(s, keyColumns=["heat_id"]),
        422,
        "binding.invalid",
    ),
    "key column that cannot be compared": (
        lambda s: _heat(s, keyColumns=["note"]),
        422,
        "binding.invalid",
    ),
    "a column binding for a type": (
        lambda s: [type_binding(s.heat, {"target": "column", "column": "heat_no"})],
        422,
        "binding.invalid",
    ),
    "a type binding of a property": (
        lambda s: [type_binding(s.weight, table(s.mes))],
        422,
        "binding.invalid",
    ),
    "column not in the table": (
        lambda s: [*_heat(s), property_binding(s.weight, "heat", "weight_kg")],
        422,
        "binding.invalid",
    ),
    "text column for a decimal property": (
        lambda s: [*_heat(s), property_binding(s.weight, "heat", "heat_no")],
        422,
        "binding.type_mismatch",
    ),
    "column that binds to nothing": (
        lambda s: [*_heat(s), property_binding(s.external_id, "heat", "note")],
        422,
        "binding.type_mismatch",
    ),
    "property of another type": (
        lambda s: [*_heat(s), property_binding(s.cast_no, "heat", "cast_no")],
        422,
        "binding.invalid",
    ),
    "property under no type binding": (
        lambda s: [property_binding(s.weight, s.heat, "weight_t")],
        422,
        "binding.invalid",
    ),
    "relation the wrong way round": (
        lambda s: [*_with_cast(s), relation_binding(s.in_cast, "cast", "heat")],
        422,
        "binding.invalid",
    ),
    "relation across data sources": (
        lambda s: [*_with_cast(s, s.other), relation_binding(s.in_cast, "heat", "cast")],
        422,
        "binding.cross_source",
    ),
    "foreign key with unequal sides": (
        lambda s: [
            *_with_cast(s),
            relation_binding(s.in_cast, "heat", "cast", foreign_key(["cast_no", "batch"])),
        ],
        422,
        "binding.invalid",
    ),
    "foreign key column not in the table": (
        lambda s: [
            *_with_cast(s),
            relation_binding(s.in_cast, "heat", "cast", foreign_key(["cast_id"])),
        ],
        422,
        "binding.invalid",
    ),
    "foreign key on the other side": (
        # side = target: the columns are the 浇次 table's, which has no heat_no.
        lambda s: [
            *_with_cast(s),
            relation_binding(
                s.in_cast, "heat", "cast", foreign_key(["heat_no"], ["heat_no"], "target")
            ),
        ],
        422,
        "binding.invalid",
    ),
    "link table columns that do not match the keys": (
        lambda s: [
            *_with_cast(s),
            relation_binding(
                s.in_cast, "heat", "cast", link_table(["heat_no", "cast_no"], ["cast_no"])
            ),
        ],
        422,
        "binding.invalid",
    ),
    "binding on an object type": (
        lambda s: [create("entity_type", localName="Slab", labelZh="板坯", binding=table(s.mes))],
        422,
        "changeset.invalid_edit",
    ),
}


@pytest.mark.parametrize("case", list(_RULES))
async def test_bindings_follow_their_rules(
    client: AsyncClient, db: AsyncSession, case: str
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    items, status, code = _RULES[case]

    response = await save(client, s.ontology, items(s))

    assert (response.status_code, response.json()["code"]) == (status, code), response.json()
    assert await bindings(db, s.ontology) == []


async def test_good_relation_bindings_pass(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)

    # side = target: 浇次's cast_no refers to 炉次's cast_no. Left for review, not applied.
    by_target = await save(
        client,
        s.ontology,
        [
            *_with_cast(s),
            relation_binding(
                s.in_cast, "heat", "cast", foreign_key(["cast_no"], ["cast_no"], "target")
            ),
        ],
        apply=False,
    )
    assert by_target.status_code == 200, by_target.json()
    linked = await save(
        client,
        s.ontology,
        [*_with_cast(s), relation_binding(s.in_cast, "heat", "cast", link_table())],
    )

    assert linked.status_code == 200, linked.json()


async def test_one_active_binding_per_bound_thing(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    [heat_binding] = [row for row in await bindings(db, s.ontology) if row.subject_id == s.heat.id]

    again = await save(client, s.ontology, [type_binding(s.heat, table(s.mes, "heat_v"))])
    twice = await save(
        client,
        s.ontology,
        [
            property_binding(s.batch_code, heat_binding, "batch"),
            property_binding(s.batch_code, heat_binding, "remark"),
        ],
    )

    assert (again.status_code, again.json()["code"]) == (409, "binding.duplicate")
    assert (twice.status_code, twice.json()["code"]) == (409, "binding.duplicate")


async def test_only_the_key_columns_of_a_type_binding_change(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    [heat_binding] = [row for row in await bindings(db, s.ontology) if row.subject_id == s.heat.id]

    moved = await save(
        client, s.ontology, [change("update", heat_binding, binding=table(s.mes, "heat_v"))]
    )
    rebound = await save(
        client, s.ontology, [change("update", heat_binding, subjectRef=str(s.cast.id))]
    )
    keys = await save(
        client,
        s.ontology,
        [change("update", heat_binding, binding=table(s.mes, keys=["heat_no", "batch"]))],
    )

    assert (moved.status_code, moved.json()["code"]) == (422, "binding.invalid")
    assert (rebound.status_code, rebound.json()["code"]) == (422, "binding.invalid")
    assert keys.status_code == 200, keys.json()
    updated = await fresh(db, heat_binding)
    assert updated.binding is not None
    assert updated.binding["keyColumns"] == ["heat_no", "batch"]
    assert updated.revision == 2


async def test_a_table_is_replaced_in_one_change_set(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    old = await bindings(db, s.ontology)
    [heat_binding] = [row for row in old if row.subject_id == s.heat.id]
    [cast_binding] = [row for row in old if row.subject_id == s.cast.id]

    # Deleting the old type binding brings the deletes of its column and relation bindings.
    response = await save(
        client,
        s.ontology,
        [
            change("delete", heat_binding),
            type_binding(s.heat, table(s.mes, "heat_v"), "view"),
            property_binding(s.external_id, "view", "heat_no"),
            relation_binding(s.in_cast, "view", cast_binding, link_table()),
        ],
    )

    assert response.status_code == 200, response.json()
    now = await bindings(db, s.ontology)
    [view_binding] = [row for row in now if row.subject_id == s.heat.id]
    assert view_binding.binding == table(s.mes, "heat_v")
    assert {row.id for row in now} & {row.id for row in old} == {cast_binding.id}
    [column] = [row for row in now if row.kind == "property_binding"]
    assert (column.subject_id, column.parent_id) == (s.external_id.id, view_binding.id)
    [relation] = [row for row in now if row.kind == "relation_binding"]
    assert (relation.domain_id, relation.range_id) == (view_binding.id, cast_binding.id)


async def test_a_new_binding_cannot_hang_under_a_binding_the_save_deletes(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    [heat_binding] = [row for row in await bindings(db, s.ontology) if row.subject_id == s.heat.id]

    response = await save(
        client,
        s.ontology,
        [change("delete", heat_binding), property_binding(s.batch_code, heat_binding, "batch")],
    )
    deleted_subject = await save(
        client,
        s.ontology,
        [change("delete", s.batch_code), property_binding(s.batch_code, heat_binding, "batch")],
    )

    assert response.status_code == 422, response.json()
    assert deleted_subject.status_code == 422, deleted_subject.json()
    assert len(await bindings(db, s.ontology)) == 5


async def test_deleting_a_bound_element_takes_its_bindings_along(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)

    weight = await save(client, s.ontology, [change("delete", s.weight)])
    assert weight.status_code == 200, weight.json()
    assert {row.subject_id for row in await bindings(db, s.ontology)} == {
        s.heat.id,
        s.cast.id,
        s.external_id.id,
        s.in_cast.id,
    }

    heat = await save(client, s.ontology, [change("delete", await fresh(db, s.heat))])

    assert heat.status_code == 200, heat.json()
    items = await change_set_items(client, heat.json()["changeSetId"])
    assert {item["kind"] for item in items if item["op"] == "delete"} >= {
        "type_binding",
        "property_binding",
        "relation_binding",
    }
    assert {row.subject_id for row in await bindings(db, s.ontology)} == {s.cast.id}


def _ai_items(s: Steel) -> list[ProposedItem]:
    source = CatalogEvidenceSource.model_validate(
        {"dataSourceId": str(s.mes.id), "schema": "mes", "table": "heat", "fact": "table"}
    )
    catalog = EvidenceIn(kind="catalog", source=source, quote="PRIMARY KEY (heat_no)")
    return [
        ProposedItem(
            op="create",
            kind="type_binding",
            temp_ref="heat",
            proposed=ElementFields.model_validate(
                {"subjectRef": str(s.heat.id), "binding": table(s.mes)}
            ),
            confidence=0.9,
            flags=["key_unverified"],
            evidence=[catalog],
        ),
        ProposedItem(
            op="create",
            kind="property_binding",
            proposed=ElementFields.model_validate(
                {
                    "subjectRef": str(s.weight.id),
                    "parentRef": "heat",
                    "binding": {"target": "column", "column": "weight_t"},
                }
            ),
            confidence=0.8,
        ),
    ]


async def _ai_change_set(db: AsyncSession, s: Steel) -> Any:
    change_set_id = await service.create_change_set(
        db,
        ontology_id=s.ontology.id,
        title="AI 建议绑定：MES",
        source="ai_binding",
        document_id=None,
        created_by=None,
        items=_ai_items(s),
    )
    await db.commit()
    return change_set_id


async def test_a_column_binding_is_skipped_with_its_rejected_table(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    change_set_id = await _ai_change_set(db, s)
    await sign_in(client, db, Role.ADMIN)

    items = await change_set_items(client, change_set_id)
    await decide_by_seq(client, change_set_id, {1: "rejected", 2: "accepted"})
    merged = await merge(client, change_set_id)

    assert items[0]["flags"] == ["key_unverified"]
    assert items[0]["evidence"][0]["kind"] == "catalog"
    assert items[0]["evidence"][0]["source"]["table"] == "heat"
    assert merged.status_code == 200, merged.json()
    assert merged.json()["skipped"] == [
        {"itemId": items[1]["id"], "code": "changeset.dependency_skipped"}
    ]
    assert await bindings(db, s.ontology) == []
    # Neither the rejected item nor the one skipped with it reaches a release.
    published = await publish(client, s.ontology)
    assert published.status_code == 201, published.json()
    assert published.json()["bindingCount"] == 0


async def test_a_reviewer_edit_of_a_binding_is_checked(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    change_set_id = await _ai_change_set(db, s)
    await sign_in(client, db, Role.ADMIN)
    [first, second] = await change_set_items(client, change_set_id)
    url = f"/api/change-sets/{change_set_id}/items"

    missing = await client.patch(
        f"{url}/{first['id']}",
        json={"edited": {"binding": table(s.mes, keys=["heat_id"])}},
        headers=csrf_headers(client),
    )
    mismatch = await client.patch(
        f"{url}/{second['id']}",
        json={"edited": {"binding": {"target": "column", "column": "batch"}}},
        headers=csrf_headers(client),
    )
    # Another property of a new item, with a column of its type.
    retyped = await client.patch(
        f"{url}/{second['id']}",
        json={
            "edited": {
                "subjectRef": str(s.external_id.id),
                "binding": {"target": "column", "column": "heat_no"},
            }
        },
        headers=csrf_headers(client),
    )

    assert missing.status_code == 422, missing.json()
    # A text column for a decimal property.
    assert mismatch.status_code == 422, mismatch.json()
    assert retyped.status_code == 200, retyped.json()
    assert retyped.json()["edited"]["subjectRef"] == str(s.external_id.id)


async def test_a_binding_update_shows_its_values_before(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    [heat_binding] = [row for row in await bindings(db, s.ontology) if row.subject_id == s.heat.id]

    response = await save(
        client,
        s.ontology,
        [change("update", heat_binding, binding=table(s.mes, keys=["heat_no", "batch"]))],
        apply=False,
    )

    assert response.status_code == 200, response.json()
    [item] = await change_set_items(client, response.json()["changeSetId"])
    assert item["before"] == {"subjectRef": str(s.heat.id), "binding": table(s.mes)}


async def test_a_deleted_binding_can_be_restored(client: AsyncClient, db: AsyncSession) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    [weight] = [row for row in await bindings(db, s.ontology) if row.subject_id == s.weight.id]

    deleted = await save(client, s.ontology, [change("delete", weight)])
    restored = await save(client, s.ontology, [change("restore", await fresh(db, weight))])

    assert deleted.status_code == 200, deleted.json()
    assert restored.status_code == 200, restored.json()
    assert (await fresh(db, weight)).status == "active"


async def test_the_assistant_does_not_propose_bindings(db: AsyncSession) -> None:
    s = await steel(db)

    proposal = await ontology_assistant.propose(
        db,
        s.ontology.id,
        message="把炉次绑定到 mes.heat",
        created_by=await admin_id(db),
        items=[_ai_items(s)[0].model_copy(update={"evidence": [], "flags": []})],
    )

    assert proposal == ontology_assistant.Proposal(change_set_id=None, dropped=1)


async def test_the_assistant_deletes_bindings_along_with_their_element(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)

    proposal = await ontology_assistant.propose(
        db,
        s.ontology.id,
        message="删除重量",
        created_by=await admin_id(db),
        items=[
            ProposedItem(
                op="delete",
                kind="property",
                target_element_id=s.weight.id,
                target_revision=s.weight.revision,
                proposed=ElementFields(),
            )
        ],
    )
    await db.commit()

    assert proposal.change_set_id is not None
    items = await change_set_items(client, proposal.change_set_id)
    assert [(item["op"], item["kind"]) for item in items] == [
        ("delete", "property"),
        ("delete", "property_binding"),
    ]


async def test_type_bindings_change_before_what_hangs_under_them(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    await bind(client, s)
    rows = {row.subject_id: row for row in await bindings(db, s.ontology)}
    heat, cast = rows[s.heat.id], rows[s.cast.id]

    # The relation binding comes first and names the type binding by id; it needs the two key
    # columns the item after it gives that type binding.
    response = await save(
        client,
        s.ontology,
        [
            change("delete", rows[s.in_cast.id]),
            relation_binding(
                s.in_cast, heat, cast, link_table(["heat_no", "cast_no"], ["cast_no"])
            ),
            change("update", heat, binding=table(s.mes, keys=["heat_no", "cast_no"])),
        ],
    )

    assert response.status_code == 200, response.json()
    [relation] = [row for row in await bindings(db, s.ontology) if row.kind == "relation_binding"]
    assert relation.binding == link_table(["heat_no", "cast_no"], ["cast_no"])


async def test_a_merge_keeps_one_active_binding_per_type(
    client: AsyncClient, db: AsyncSession
) -> None:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    first = await save(client, s.ontology, [type_binding(s.heat, table(s.mes))], apply=False)
    second = await save(
        client,
        s.ontology,
        [
            type_binding(s.heat, table(s.mes, "heat_v"), "view"),
            property_binding(s.external_id, "view", "heat_no"),
        ],
        apply=False,
    )
    assert first.status_code == 200
    assert second.status_code == 200

    merged_first = await accept_and_merge(client, first.json()["changeSetId"])
    merged_second = await accept_and_merge(client, second.json()["changeSetId"])

    assert merged_first["skipped"] == []
    items = await change_set_items(client, second.json()["changeSetId"])
    assert merged_second["skipped"] == [
        {"itemId": items[0]["id"], "code": "changeset.invalid_item"},
        {"itemId": items[1]["id"], "code": "changeset.dependency_skipped"},
    ]
    [only] = await bindings(db, s.ontology)
    assert only.binding == table(s.mes)
