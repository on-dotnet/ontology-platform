"""Bindings in the ontology module as the M3 skeleton leaves them (spec 003, 6.1 and section 16,
batch 1): binding rows (inserted directly, as batch 4a's merge will write them) stay out of the
semantic views, but the dependency checks see them; binding items wait for batch 4a.
"""

from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import Element, Ontology
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem
from support import csrf_headers
from test_ontology_support import accept_and_merge, add_elements, add_ontology, element, sign_in


def _table(source_id: UUID) -> dict[str, Any]:
    return {
        "target": "table",
        "dataSourceId": str(source_id),
        "schema": "mes",
        "table": "heat",
        "keyColumns": ["heat_no"],
    }


def _type_binding(ontology: Ontology, subject: Element, source_id: UUID) -> Element:
    return element(
        ontology,
        "type_binding",
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        subject_id=subject.id,
        auto_shape=False,
        binding=_table(source_id),
    )


async def _bound_steel(db: AsyncSession) -> tuple[Ontology, Element, Element, UUID]:
    """The object type 炉次 bound to the table mes.heat of a data source."""
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)
    source_id = uuid4()
    binding = _type_binding(steel, heat, source_id)
    await add_elements(db, binding)
    await db.commit()
    return steel, heat, binding, source_id


async def test_bindings_stay_out_of_the_semantic_views(
    client: AsyncClient, db: AsyncSession
) -> None:
    steel = await add_ontology(db)
    heat = element(steel, "entity_type", "Heat", "炉次")
    await add_elements(db, heat)
    await db.commit()
    turtle_before, _ = await ontology_service.export_working_version(db, steel.id)
    context_before = await ontology_assistant.context_for(
        db, steel.id, message="炉次", page="ontology", element_id=None
    )

    await add_elements(db, _type_binding(steel, heat, uuid4()))
    await db.commit()

    turtle_after, _ = await ontology_service.export_working_version(db, steel.id)
    context_after = await ontology_assistant.context_for(
        db, steel.id, message="炉次", page="ontology", element_id=None
    )
    alignment = await ontology_service.list_alignment_elements(db, steel.id)
    graph = await ontology_service.get_graph(db, steel.id)
    listed = await ontology_service.list_elements(db, steel.id, kind=None, q=None)
    bindings = await ontology_service.list_elements(db, steel.id, kind="type_binding", q=None)

    assert turtle_after == turtle_before
    assert context_after == context_before
    assert [e.kind for e in alignment] == ["entity_type"]
    assert [node.id for node in graph.nodes] == [heat.id]
    assert [e.kind for e in listed] == ["entity_type"]
    assert [b.subject_id for b in bindings] == [heat.id]
    assert bindings[0].binding is not None

    # Saving the exported Turtle again finds nothing to change: no delete of the binding.
    await sign_in(client, db, Role.ADMIN)
    saved = await client.post(
        f"/api/ontologies/{steel.id}/turtle",
        json={"turtle": turtle_after},
        headers=csrf_headers(client),
    )
    assert saved.status_code == 200
    assert saved.json()["changeSetId"] is None


async def test_a_bound_type_is_not_deleted_from_under_its_binding(
    client: AsyncClient, db: AsyncSession
) -> None:
    steel, heat, binding, _ = await _bound_steel(db)
    change_set_id = await ontology_service.create_change_set(
        db,
        ontology_id=steel.id,
        title="删除炉次",
        source="manual",
        document_id=None,
        created_by=None,
        items=[
            ProposedItem(
                op="delete", kind="entity_type", target_element_id=heat.id, proposed=ElementFields()
            )
        ],
    )
    await db.commit()
    await sign_in(client, db, Role.ADMIN)

    result = await accept_and_merge(client, change_set_id)
    impact = await client.get(f"/api/ontologies/{steel.id}/elements/{heat.id}/impact")

    assert [skip["code"] for skip in result["skipped"]] == ["changeset.has_dependents"]
    assert impact.status_code == 200
    cascade = {(change["op"], change["element"]["id"]) for change in impact.json()["cascade"]}
    assert ("delete", str(binding.id)) in cascade


async def test_binding_items_wait_for_batch_4a(client: AsyncClient, db: AsyncSession) -> None:
    steel, heat, _, source_id = await _bound_steel(db)
    await sign_in(client, db, Role.ADMIN)
    create = {
        "op": "create",
        "kind": "type_binding",
        "tempRef": "b1",
        "fields": {"subjectRef": str(heat.id), "binding": _table(source_id)},
    }
    # Deleting the bound type takes its binding along in the cascade, which stops there too.
    delete = {
        "op": "delete",
        "kind": "entity_type",
        "targetElementId": str(heat.id),
        "targetRevision": heat.revision,
        "fields": {},
    }

    for item in (create, delete):
        response = await client.post(
            f"/api/ontologies/{steel.id}/edits",
            json={"items": [item], "apply": True},
            headers=csrf_headers(client),
        )
        assert response.status_code == 501, item
        assert response.json()["code"] == "http.not_implemented"


async def test_connectors_learn_which_tables_are_bound(db: AsyncSession) -> None:
    _, heat, _, source_id = await _bound_steel(db)

    usage = await connectors.table_usage(db, source_id)

    assert usage is not None
    assert [(u.schema, u.table, u.type_id, u.type_label) for u in usage] == [
        ("mes", "heat", heat.id, "炉次")
    ]
    assert usage[0].in_working_version
    assert not usage[0].in_active_release
    assert await connectors.table_usage(db, uuid4()) == []


async def test_the_previous_release_can_still_write_evidence_and_releases(
    db: AsyncSession,
) -> None:
    """v0009 only adds columns with server defaults (AGENTS.md: 先加后删)."""
    steel = await add_ontology(db)
    change_set_id = await ontology_service.create_change_set(
        db,
        ontology_id=steel.id,
        title="t",
        source="manual",
        document_id=None,
        created_by=None,
        items=[
            ProposedItem(
                op="create",
                kind="entity_type",
                temp_ref="h",
                proposed=ElementFields(local_name="Heat", label_zh="炉次"),
            )
        ],
    )
    await db.commit()
    item_id = await db.scalar(
        text("SELECT id FROM ontology.change_items WHERE change_set_id = :id"),
        {"id": change_set_id},
    )
    # Written the way the M2 code writes these rows: without the M3 columns.
    await db.execute(
        text(
            "INSERT INTO ontology.evidence (id, change_item_id, document_id, chunk_id, quote)"
            " VALUES (:id, :item, :doc, :chunk, :quote)"
        ),
        {"id": uuid4(), "item": item_id, "doc": uuid4(), "chunk": uuid4(), "quote": "原文"},
    )
    await db.execute(
        text(
            "INSERT INTO ontology.releases (id, ontology_id, version, title, snapshot, turtle,"
            " turtle_sha256, element_count)"
            " VALUES (:id, :ontology, 1, :title, CAST(:snapshot AS jsonb), :turtle, :sha, 0)"
        ),
        {
            "id": uuid4(),
            "ontology": steel.id,
            "title": "v1",
            "snapshot": "[]",
            "turtle": "",
            "sha": "0" * 64,
        },
    )
    await db.commit()

    kinds = list(await db.scalars(text("SELECT kind FROM ontology.evidence")))
    counts = list(await db.scalars(text("SELECT binding_count FROM ontology.releases")))
    assert kinds == ["document"]
    assert counts == [0]
