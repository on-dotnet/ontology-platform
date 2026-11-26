"""Bindings in the ontology module as the M3 skeleton leaves them (spec 003, 6.1 and section 16,
batch 1): binding rows (inserted directly, as batch 4a's merge will write them) stay out of the
semantic views, but the dependency checks see them.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.audit.models import AuditEvent
from ontology_platform.modules.connectors import service as connectors
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.ontology import assistant as ontology_assistant
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import ChangeSet, Element, Ontology, Release
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem
from support import ADMIN_USERNAME, csrf_headers
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


async def test_table_usage_reads_the_release_in_effect(db: AsyncSession) -> None:
    steel, heat, binding, source_id = await _bound_steel(db)
    # Written the way publish_release writes snapshots; its checks only pass bindings with 4a.
    release_id = uuid4()
    db.add(
        Release(
            id=release_id,
            ontology_id=steel.id,
            version=1,
            title="v1",
            snapshot=[
                ontology_service.element_out(e, steel.base_iri).model_dump(
                    mode="json", by_alias=True
                )
                for e in (heat, binding)
            ],
            turtle="",
            turtle_sha256="0" * 64,
            element_count=1,
            binding_count=1,
            created_at=datetime.now(UTC),
        )
    )
    await db.flush()
    await db.execute(
        update(Ontology).where(Ontology.id == steel.id).values(active_release_id=release_id)
    )
    # The working version moves on: only the release still has the binding, and the label too.
    await db.execute(delete(Element).where(Element.id == binding.id))
    await db.execute(update(Element).where(Element.id == heat.id).values(label_zh="炉次（改）"))
    await db.commit()

    usage = await connectors.table_usage(db, source_id)

    assert usage is not None
    assert [(u.schema, u.table, u.type_id, u.type_label) for u in usage] == [
        ("mes", "heat", heat.id, "炉次")
    ]
    assert usage[0].in_active_release
    assert not usage[0].in_working_version

    # A release that is not in effect does not count.
    await db.execute(update(Ontology).where(Ontology.id == steel.id).values(active_release_id=None))
    await db.commit()
    assert await connectors.table_usage(db, source_id) == []


async def _admin_id(db: AsyncSession) -> UUID:
    admin_id = await db.scalar(select(User.id).where(User.username == ADMIN_USERNAME))
    assert admin_id is not None
    return admin_id


async def test_mcp_proposals_are_the_token_owners_and_counted(db: AsyncSession) -> None:
    steel = await add_ontology(db)
    admin_id = await _admin_id(db)
    token_id = uuid4()
    before = datetime.now(UTC) - timedelta(seconds=1)
    item = ProposedItem(
        op="create",
        kind="entity_type",
        temp_ref="h",
        proposed=ElementFields(local_name="Heat", label_zh="炉次"),
    )

    proposal = await ontology_assistant.propose(
        db,
        steel.id,
        message="加一个炉次",
        created_by=admin_id,
        items=[item],
        source="mcp",
        title="MCP 提议的炉次",
        token_id=token_id,
    )
    # Proposals that are not MCP ones count for neither limit.
    await ontology_service.create_change_set(
        db,
        ontology_id=steel.id,
        title="手工",
        source="manual",
        document_id=None,
        created_by=admin_id,
        items=[item],
    )
    await db.commit()

    assert proposal.change_set_id is not None
    change_set = await db.get(ChangeSet, proposal.change_set_id)
    assert change_set is not None
    assert (change_set.source, change_set.title, change_set.token_id) == (
        "mcp",
        "MCP 提议的炉次",
        token_id,
    )
    created = await db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "changeset.created",
            AuditEvent.target_id == str(change_set.id),
        )
    )
    assert created is not None
    assert created.actor_id == admin_id
    assert created.detail == {"source": "mcp", "items": 1, "tokenId": str(token_id)}

    after = datetime.now(UTC) + timedelta(seconds=1)
    assert await ontology_service.count_mcp_change_sets(db, token_id, since=before) == 1
    assert await ontology_service.count_mcp_change_sets(db, token_id, since=after) == 0
    assert await ontology_service.count_mcp_change_sets(db, uuid4(), since=before) == 0
    assert await ontology_service.count_open_mcp_change_sets(db, admin_id) == 1
    assert await ontology_service.count_open_mcp_change_sets(db, uuid4()) == 0

    change_set.status = "rejected"
    await db.commit()
    assert await ontology_service.count_open_mcp_change_sets(db, admin_id) == 0
    # The rate limit still counts what was proposed, whatever became of it.
    assert await ontology_service.count_mcp_change_sets(db, token_id, since=before) == 1


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
