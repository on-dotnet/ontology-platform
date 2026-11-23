"""Helpers shared by the ontology tests. This module has no tests of its own."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.identity import service as identity
from ontology_platform.modules.identity.models import Role, User
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.models import ChangeOp, Element, Kind, Ontology
from ontology_platform.modules.ontology.schemas import ElementFields, EvidenceIn, ProposedItem
from support import csrf_headers, login

ROLE_PASSWORD = "role-test-password"
DOCUMENT_ID = UUID("00000000-0000-4000-8000-00000000d0c1")
CHUNK_ID = UUID("00000000-0000-4000-8000-0000000c4c01")


async def sign_in(client: AsyncClient, db: AsyncSession, role: Role) -> None:
    """Log the client in as a user with `role` (the seeded admin for Role.ADMIN)."""
    if role is Role.ADMIN:
        response = await login(client)
    else:
        username = f"{role.value}-user"
        if await db.scalar(select(User.id).where(User.username == username)) is None:
            await identity.create_user(db, username=username, password=ROLE_PASSWORD, role=role)
            await db.commit()
        response = await login(client, username, ROLE_PASSWORD)
    assert response.status_code == 200


async def add_ontology(db: AsyncSession, key: str = "steel", name: str = "钢铁冶金") -> Ontology:
    now = datetime.now(UTC)
    ontology = Ontology(
        id=uuid4(),
        key=key,
        name=name,
        base_iri=f"https://example.org/ontology/{key}#",
        created_at=now,
        updated_at=now,
    )
    db.add(ontology)
    await db.commit()
    return ontology


def element(
    ontology: Ontology,
    kind: Kind,
    local_name: str,
    label_zh: str,
    **fields: Any,
) -> Element:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "id": uuid4(),
        "ontology_id": ontology.id,
        "kind": kind,
        "local_name": local_name,
        "label_zh": label_zh,
        "synonyms": [],
        "required": False,
        "multiple": False,
        "status": "active",
        "origin": "manual",
        "revision": 1,
        "created_at": now,
        "updated_at": now,
    }
    values.update(fields)
    return Element(**values)


async def add_elements(db: AsyncSession, *elements: Element) -> None:
    # One flush per row: references between new rows need their targets inserted first.
    for item in elements:
        db.add(item)
        await db.flush()
    await db.commit()


def evidence(quote: str = "原文引语") -> EvidenceIn:
    return EvidenceIn(
        document_id=DOCUMENT_ID,
        chunk_id=CHUNK_ID,
        quote=quote,
        char_start=0,
        char_end=len(quote),
    )


def proposal(
    op: ChangeOp,
    kind: Kind,
    *,
    temp_ref: str | None = None,
    target: UUID | None = None,
    confidence: float | None = 0.9,
    flags: list[str] | None = None,
    **fields: Any,
) -> ProposedItem:
    return ProposedItem(
        op=op,
        kind=kind,
        target_element_id=target,
        temp_ref=temp_ref,
        proposed=ElementFields(**fields),
        confidence=confidence,
        rationale="原文直接给出了定义。",
        flags=flags or [],
        evidence=[evidence()],
    )


async def open_change_set(
    db: AsyncSession,
    ontology: Ontology,
    items: list[ProposedItem],
    *,
    title: str = "识别：工艺规程.docx",
) -> UUID:
    change_set_id = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title=title,
        source="ai_extraction",
        document_id=DOCUMENT_ID,
        created_by=None,
        items=items,
    )
    await db.commit()
    return change_set_id


async def change_set_items(client: AsyncClient, change_set_id: UUID) -> list[dict[str, Any]]:
    response = await client.get(f"/api/change-sets/{change_set_id}")
    assert response.status_code == 200
    items: list[dict[str, Any]] = response.json()["items"]
    return items


async def decide(
    client: AsyncClient,
    change_set_id: UUID,
    item_ids: list[str],
    decision: str,
) -> Response:
    return await client.post(
        f"/api/change-sets/{change_set_id}/decisions",
        json={"itemIds": item_ids, "decision": decision},
        headers=csrf_headers(client),
    )


async def decide_by_seq(
    client: AsyncClient,
    change_set_id: UUID,
    decisions: dict[int, str],
) -> None:
    """Decide items by their position (seq) in the change set."""
    items = {item["seq"]: item["id"] for item in await change_set_items(client, change_set_id)}
    for seq, decision in decisions.items():
        response = await decide(client, change_set_id, [items[seq]], decision)
        assert response.status_code == 200


async def merge(client: AsyncClient, change_set_id: UUID) -> Response:
    return await client.post(
        f"/api/change-sets/{change_set_id}/merge",
        headers=csrf_headers(client),
    )


async def accept_and_merge(client: AsyncClient, change_set_id: UUID) -> dict[str, Any]:
    ids = [item["id"] for item in await change_set_items(client, change_set_id)]
    assert (await decide(client, change_set_id, ids, "accepted")).status_code == 200
    response = await merge(client, change_set_id)
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


async def elements_by_name(db: AsyncSession, ontology: Ontology) -> dict[str, Element]:
    rows = await db.scalars(
        select(Element)
        .where(Element.ontology_id == ontology.id)
        .execution_options(populate_existing=True),
    )
    return {row.local_name: row for row in rows}


async def publish(client: AsyncClient, ontology: Ontology, title: str = "首版") -> Response:
    return await client.post(
        f"/api/ontologies/{ontology.id}/releases",
        json={"title": title},
        headers=csrf_headers(client),
    )
