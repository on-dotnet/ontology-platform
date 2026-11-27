"""Contracts left for the later review learning batches."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai import review_assist
from ontology_platform.modules.ai.candidates import main_name, normalize
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service
from ontology_platform.modules.ontology.review_memory import (
    ReviewMemory,
    _main_name,
    _normalize,
    apply_delta,
    collect,
    pair_key,
    property_key,
    relation_key,
    type_key,
)
from ontology_platform.modules.ontology.schemas import SuppressedItem
from support import csrf_headers
from test_ontology_support import DOCUMENT_ID, add_ontology, open_change_set, proposal, sign_in


async def test_review_memory_writes_need_a_reviewer(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    base = f"/api/ontologies/{ontology.id}/review-memory"
    entry = uuid4()
    writes = [
        ("DELETE", f"{base}/{entry}"),
        ("POST", f"{base}/{entry}/restore"),
        ("POST", f"{base}/clear"),
    ]
    for role in (Role.VIEWER, Role.EDITOR):
        await sign_in(client, db, role)
        for method, url in writes:
            response = await client.request(method, url, headers=csrf_headers(client))
            assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
        # Every signed-in user may read the memory.
        assert (await client.get(base)).status_code != 403
    await sign_in(client, db, Role.REVIEWER)
    for method, url in writes:
        response = await client.request(method, url, headers=csrf_headers(client))
        assert response.status_code != 403


async def test_a_review_assist_needs_an_editor(client: AsyncClient, db: AsyncSession) -> None:
    ontology = await add_ontology(db)
    change_set_id = await open_change_set(
        db, ontology, [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    )
    url = f"/api/change-sets/{change_set_id}/review-assist"
    await sign_in(client, db, Role.VIEWER)
    refused = await client.post(url, json={"locale": "zh-CN"}, headers=csrf_headers(client))
    assert (refused.status_code, refused.json()["code"]) == (403, "auth.forbidden")
    assert (await client.get(url)).status_code != 403
    await sign_in(client, db, Role.EDITOR)
    started = await client.post(url, json={"locale": "zh-CN"}, headers=csrf_headers(client))
    assert started.status_code != 403


async def test_a_change_set_keeps_200_suppressed_proposals_and_counts_the_rest(
    client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    entry = uuid4()
    suppressed = [
        SuppressedItem(
            kind="entity_type",
            label_zh=f"类型{n}",
            label_en=None,
            cause="memory",
            memory_entry_id=entry,
            depends_on=None,
        )
        for n in range(201)
    ]
    items = [proposal("create", "entity_type", local_name="Heat", label_zh="炉次")]
    kept = await service.create_change_set(
        db,
        ontology_id=ontology.id,
        title="识别：工艺规程.docx",
        source="ai_extraction",
        document_id=DOCUMENT_ID,
        created_by=None,
        items=items,
        suppressed=suppressed,
        suppressed_total=230,
    )
    await db.commit()
    plain = await open_change_set(db, ontology, items)
    await sign_in(client, db, Role.VIEWER)

    detail = (await client.get(f"/api/change-sets/{kept}")).json()
    assert len(detail["suppressed"]) == 200
    assert detail["suppressed"][0] == {
        "kind": "entity_type",
        "labelZh": "类型0",
        "labelEn": None,
        "cause": "memory",
        "memoryEntryId": str(entry),
        "dependsOn": None,
    }
    assert detail["suppressedTotal"] == 230
    other = (await client.get(f"/api/change-sets/{plain}")).json()
    assert (other["suppressed"], other["suppressedTotal"]) == ([], 0)


@pytest.mark.parametrize(
    ("zh", "en"),
    [
        (" 炉 次 ", "Heat"),
        ("ＡＢＣ", "abc"),  # noqa: RUF001 (full-width on purpose)
        (None, " Steel Heat "),
        (" \t", " ＦＯＯ "),  # noqa: RUF001 (full-width on purpose)
    ],
)
def test_review_keys_follow_candidate_normalization(zh: str | None, en: str | None) -> None:
    assert _normalize(zh or "") == normalize(zh or "")
    assert _main_name(zh, en) == main_name(zh, en)
    assert type_key(zh, en) == "t:" + main_name(zh, en)
    assert relation_key("炉次", "产出", "钢卷") == "r:炉次|产出|钢卷"
    assert property_key("炉次", "编号") == "p:炉次|编号"
    assert pair_key("钢包车", "钢包") == "k:钢包||钢包车"


@pytest.mark.xfail(strict=True, reason="Batch 2 implements memory collection")
def test_collected_rejections_appear_in_memory() -> None:
    ontology_id = uuid4()
    delta = collect("ai_extraction", [])
    assert apply_delta(
        ReviewMemory(ontology_id, ()), delta, now=datetime.now(UTC), max_entries=500
    ).entries


@pytest.mark.xfail(strict=True, reason="Batch 3 implements extraction memory guards")
def test_extraction_memory_guard_is_registered() -> None:
    from ontology_platform.modules.ai import extraction

    assert "memory" in extraction.build_proposals.__code__.co_varnames


@pytest.mark.xfail(strict=True, reason="Batch 6 implements review assistance")
async def test_review_assist_request_is_available() -> None:
    await review_assist.latest_assist(None, uuid4())  # type: ignore[arg-type]
