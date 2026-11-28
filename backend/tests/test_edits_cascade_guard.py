"""Manual saves whose callers have already listed every affected element."""

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology
from support import csrf_headers
from test_ontology_bindings_support import (
    bindings,
    change,
    property_binding,
    save,
    steel,
    table,
    type_binding,
)
from test_ontology_support import add_elements, add_ontology, change_set_items, element, sign_in


async def save_listed(
    client: AsyncClient, ontology: Ontology, *items: dict[str, Any], apply: bool = False
) -> Response:
    return await client.post(
        f"/api/ontologies/{ontology.id}/edits",
        json={"items": items, "allowCascade": False, "apply": apply},
        headers=csrf_headers(client),
    )


@pytest.fixture
async def table_and_column(
    client: AsyncClient, db: AsyncSession
) -> tuple[Ontology, Element, Element]:
    s = await steel(db)
    await sign_in(client, db, Role.ADMIN)
    bound = await save(client, s.ontology, [type_binding(s.heat, table(s.mes))])
    assert bound.status_code == 200, bound.text
    [bound_table] = await bindings(db, s.ontology)

    # The editor has read the table revision when a separate save adds the column.
    added = await save(client, s.ontology, [property_binding(s.weight, bound_table, "weight_t")])
    assert added.status_code == 200, added.text
    [column] = [row for row in await bindings(db, s.ontology) if row.kind == "property_binding"]
    return s.ontology, bound_table, column


@pytest.mark.parametrize("apply", [False, True], ids=["review", "apply"])
async def test_unlisted_binding_rolls_back_the_save(
    client: AsyncClient,
    db: AsyncSession,
    table_and_column: tuple[Ontology, Element, Element],
    apply: bool,
) -> None:
    ontology, bound_table, column = table_and_column
    change_sets = select(func.count(ChangeSet.id)).where(ChangeSet.ontology_id == ontology.id)
    events = select(func.count(AuditEvent.id))
    previous_sets = await db.scalar(change_sets)
    previous_events = await db.scalar(events)

    response = await save_listed(client, ontology, change("delete", bound_table), apply=apply)

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "changeset.cascade_changed"
    assert "1 additional" in response.json()["detail"]
    assert await db.scalar(change_sets) == previous_sets
    assert await db.scalar(events) == previous_events
    assert {row.id for row in await bindings(db, ontology)} == {bound_table.id, column.id}


async def test_listed_bindings_are_the_only_change_set_items(
    client: AsyncClient, table_and_column: tuple[Ontology, Element, Element]
) -> None:
    ontology, bound_table, column = table_and_column
    response = await save_listed(
        client, ontology, change("delete", column), change("delete", bound_table)
    )

    assert response.status_code == 200, response.text
    items = await change_set_items(client, response.json()["changeSetId"])
    assert [(item["op"], item["kind"], item["targetElementId"]) for item in items] == [
        ("delete", "property_binding", str(column.id)),
        ("delete", "type_binding", str(bound_table.id)),
    ]


async def test_subtype_cascade_requires_listing_the_child(
    client: AsyncClient, db: AsyncSession
) -> None:
    await sign_in(client, db, Role.ADMIN)
    ontology = await add_ontology(db)
    parent = element(ontology, "entity_type", "Batch", "批次")
    child = element(ontology, "entity_type", "Heat", "炉次", parent_id=parent.id)
    await add_elements(db, parent, child)

    missing = await save_listed(client, ontology, change("delete", parent))
    assert missing.status_code == 409, missing.text
    assert missing.json()["code"] == "changeset.cascade_changed"

    # Clearing the parent ref can share the child's explicitly requested update.
    listed = await save_listed(
        client,
        ontology,
        change("delete", parent),
        change("update", child, labelZh="新炉次"),
        apply=True,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["merge"] == {"applied": 2, "skipped": []}
    await db.refresh(child)
    assert (child.parent_id, child.label_zh) == (None, "新炉次")
