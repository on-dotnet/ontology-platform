"""Alignment records of change items: storage, review and merge (spec 004, 5.3, 5.5 and 9)."""

from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai.pipeline import make_extractor
from ontology_platform.modules.ai.prompts import RelationsOut, TermsOut, TypesOut
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import ChangeItem, ChangeSet, Ontology
from ontology_platform.modules.ontology.schemas import ElementFields, ProposedItem
from test_ai_alignment import (
    MODELS,
    add_document,
    identify,
    labelled,
    merged,
    named,
    working_version,
)
from test_ai_extraction import ScriptedGateway, entity, judge, relation
from test_ontology_changesets import patch_item
from test_ontology_support import add_ontology, sign_in

LADLE_TEXT = "钢水由钢包吊运至精炼炉。"
TEEMING_TEXT = "精炼后的钢水装入钢水包浇铸。"


async def detail(client: AsyncClient, change_set_id: UUID) -> dict[str, Any]:
    response = await client.get(f"/api/change-sets/{change_set_id}")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def item_labelled(body: dict[str, Any], label: str) -> dict[str, Any]:
    return next(i for i in body["items"] if (i["edited"] or i["proposed"]).get("labelZh") == label)


async def two_documents(
    app: FastAPI,
    db: AsyncSession,
    verdict: str,
    *,
    refiner_in_second: bool = True,
    key: str = "steel",
) -> tuple[Ontology, UUID, UUID]:
    """钢包 in the first document, 钢水包 in the second, judged `verdict` against it."""
    ontology = await add_ontology(db, key)
    first = await add_document(db, ontology, "吊运规程.md", LADLE_TEXT)
    second = await add_document(db, ontology, "浇铸规程.md", TEEMING_TEXT)
    teeming = [entity("new:TeemingLadle", "钢水包", sentence="0.1")]
    relations = RelationsOut(relations=[], properties=[])
    if refiner_in_second:
        teeming.append(entity("new:Refiner", "精炼炉", sentence="0.1"))
    change_sets = await identify(
        app,
        [
            (first, [entity("new:Ladle", "钢包", sentence="0.1")], relations),
            (second, teeming, relations),
        ],
        judge({"钢水包": ("钢包", verdict)}),
    )
    return ontology, change_sets[0], change_sets[1]


async def test_the_previous_release_still_writes_and_reads_change_items(
    db: AsyncSession,
) -> None:
    # The new columns are nullable and have no defaults the old program would have to send.
    ontology = await add_ontology(db)
    change_set = ChangeSet(
        id=uuid4(), ontology_id=ontology.id, title="旧版", source="manual", status="open"
    )
    db.add(change_set)
    await db.flush()
    item_id = uuid4()
    old_columns = {
        "id": item_id,
        "change_set_id": change_set.id,
        "seq": 1,
        "op": "create",
        "kind": "entity_type",
        "temp_ref": "new:Ladle",
        "proposed": {"localName": "Ladle", "labelZh": "钢包"},
        "decision": "pending",
    }
    await db.execute(insert(ChangeItem).values(**old_columns))
    await db.commit()
    columns = [getattr(ChangeItem, name) for name in old_columns]
    [row] = (await db.execute(select(*columns).where(ChangeItem.id == item_id))).all()
    assert row.seq == 1
    stored = await db.get(ChangeItem, item_id)
    assert stored is not None
    assert (stored.match_kind, stored.match_item_id, stored.match_decision) == (None, None, None)


async def test_a_type_judged_the_same_as_a_pending_one_goes_into_it_after_that_one(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology, first, second = await two_documents(app, db, "same")
    ontology_id = ontology.id
    await sign_in(client, db, Role.ADMIN)

    body = await detail(client, second)
    teeming = item_labelled(body, "钢水包")
    first_ladle = item_labelled(await detail(client, first), "钢包")
    assert teeming["match"] == {
        "kind": "same",
        "elementId": None,
        "itemId": first_ladle["id"],
        "changeSetId": str(first),
        "changeSetTitle": "识别：吊运规程.md",
        "label": "钢包",
        "reason": "理由",
        "decision": None,
        "keptApart": False,
    }
    # The first change set is still pending: created as proposed for now.
    assert teeming["resolution"]["mode"] == "create"

    assert await merged(client, first) == []
    body = await detail(client, second)
    resolution = item_labelled(body, "钢水包")["resolution"]
    assert (resolution["mode"], resolution["elementLabel"]) == ("into", "钢包")
    assert await merged(client, second) == []
    [ladle] = labelled(await working_version(db, ontology_id), "entity_type", "钢包")
    assert {s.text for s in ladle.synonyms} == {"钢水包"}


async def test_the_reviewer_merges_a_possible_duplicate_or_keeps_a_judged_one_apart(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    for verdict, decision, types, key in (
        ("unsure", "same", 2, "steel"),
        ("same", "different", 3, "steel2"),
    ):
        ontology, first, second = await two_documents(app, db, verdict, key=key)
        await sign_in(client, db, Role.ADMIN)
        assert await merged(client, first) == []
        teeming = item_labelled(await detail(client, second), "钢水包")
        assert teeming["match"]["kind"] == ("possible" if verdict == "unsure" else "same")
        response = await patch_item(client, second, teeming["id"], {"matchDecision": decision})
        assert response.status_code == 200
        assert response.json()["match"]["decision"] == decision
        expected = "into" if decision == "same" else "create"
        assert response.json()["resolution"]["mode"] == expected
        assert await merged(client, second) == []
        found = [e for e in await working_version(db, ontology.id) if e.kind == "entity_type"]
        assert len(found) == types


async def test_a_merged_item_that_recorded_this_one_shows_and_takes_effect(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    # The second document is merged first: its 钢水包 is created; the first one's 钢包 then
    # goes into it, as the second item's record says.
    ontology, first, second = await two_documents(app, db, "same", refiner_in_second=False)
    await sign_in(client, db, Role.ADMIN)
    assert await merged(client, second) == []

    ladle = item_labelled(await detail(client, first), "钢包")
    assert ladle["match"]["kind"] == "same"
    assert ladle["match"]["label"] == "钢水包"
    assert ladle["match"]["changeSetId"] == str(second)
    assert ladle["resolution"]["mode"] == "into"
    assert await merged(client, first) == []
    [teeming] = labelled(await working_version(db, ontology.id), "entity_type", "钢水包")
    assert {s.text for s in teeming.synonyms} == {"钢包"}


async def test_an_alignment_decision_needs_a_record(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    _, first, _ = await two_documents(app, db, "same")
    await sign_in(client, db, Role.ADMIN)
    ladle = item_labelled(await detail(client, first), "钢包")
    response = await patch_item(client, first, ladle["id"], {"matchDecision": "same"})
    assert response.status_code == 422
    assert response.json()["code"] == "changeset.no_match"


async def test_a_possible_duplicate_within_one_change_set_can_be_merged_into_the_other(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    text = "钢水由钢包吊运至精炼炉，精炼后装入钢水包浇铸。"
    document = await add_document(db, ontology, "规程.md", text)
    [change_set] = await identify(
        app,
        [
            (
                document,
                [
                    entity("new:Ladle", "钢包", sentence="0.1"),
                    entity("new:Refiner", "精炼炉", sentence="0.1"),
                    entity("new:Teeming", "钢水包", sentence="0.1"),
                ],
                RelationsOut(
                    relations=[
                        named(
                            relation("new:Teeming", "new:Refiner", "运自", None), "comesFrom", "0.1"
                        )
                    ],
                    properties=[],
                ),
            )
        ],
        judge({"钢水包": ("钢包", "unsure")}),
    )
    await sign_in(client, db, Role.ADMIN)
    teeming = item_labelled(await detail(client, change_set), "钢水包")
    assert "possible_duplicate" in teeming["flags"]
    assert teeming["match"]["changeSetId"] == str(change_set)
    response = await patch_item(client, change_set, teeming["id"], {"matchDecision": "same"})
    resolution = response.json()["resolution"]
    assert (resolution["mode"], resolution["elementId"], resolution["elementLabel"]) == (
        "into",
        None,
        "钢包",
    )
    assert await merged(client, change_set) == []
    elements = await working_version(db, ontology_id)
    [ladle] = labelled(elements, "entity_type", "钢包")
    assert {s.text for s in ladle.synonyms} == {"钢水包"}
    [link] = labelled(elements, "relation_type", "运自")
    assert link.domain_id == ladle.id


async def test_a_type_proposed_meanwhile_is_marked_when_the_change_set_is_written(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    # Another document's 钢水包 is written while this one is being identified: it was no
    # candidate of the resolve call, so the write-time recheck marks it (spec 004, 7.3).
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    document = await add_document(db, ontology, "吊运规程.md", LADLE_TEXT)
    outputs: dict[str, list[BaseModel]] = {
        "extract.terms": [TermsOut(terms=[])],
        "extract.types": [TypesOut(entity_types=[entity("new:Ladle", "钢包", sentence="0.1")])],
        "extract.relations": [RelationsOut(relations=[], properties=[])],
    }
    written: list[UUID] = []

    async def lease(session: AsyncSession) -> None:
        if written:
            return
        written.append(
            await ontology_service.create_change_set(
                session,
                ontology_id=ontology_id,
                title="识别：浇铸规程.md",
                source="ai_extraction",
                document_id=None,
                created_by=None,
                items=[
                    ProposedItem(
                        op="create",
                        kind="entity_type",
                        temp_ref="new:Teeming",
                        proposed=ElementFields(local_name="Teeming", label_zh="钢水包"),
                    )
                ],
            )
        )

    extract = make_extractor(app.state.session_factory, ScriptedGateway(outputs), MODELS)
    change_set = await extract(document, lease)
    assert change_set is not None
    await sign_in(client, db, Role.ADMIN)
    ladle = item_labelled(await detail(client, change_set), "钢包")
    other = item_labelled(await detail(client, written[0]), "钢水包")
    assert "possible_duplicate" in ladle["flags"]
    assert (ladle["match"]["kind"], ladle["match"]["itemId"], ladle["match"]["reason"]) == (
        "possible",
        other["id"],
        None,
    )


async def test_a_type_of_a_pending_items_main_name_follows_it_until_renamed(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    # 领用单 of the second document went into 备件领用单; the third document's 领用单 follows
    # it there (a "name" record), unless a reviewer renames it.
    for rename, types in ((False, 1), (True, 2)):
        ontology = await add_ontology(db, "steel" if not rename else "steel2")
        documents = [
            await add_document(db, ontology, f"{name}.md", text)
            for name, text in (("a", "备件领用单。"), ("b", "领用单。"), ("c", "领用单一式两份。"))
        ]
        relations = RelationsOut(relations=[], properties=[])
        issue = entity("new:Issue", "备件领用单", sentence="0.1")
        slip = entity("new:Slip", "领用单", sentence="0.1")
        change_sets = await identify(
            app,
            [
                (documents[0], [issue], relations),
                (documents[1], [slip], relations),
                (documents[2], [slip], relations),
            ],
            judge({"领用单": ("备件领用单", "same")}),
        )
        await sign_in(client, db, Role.ADMIN)
        third = item_labelled(await detail(client, change_sets[2]), "领用单")
        assert (third["match"]["kind"], third["match"]["changeSetId"]) == (
            "name",
            str(change_sets[1]),
        )
        # No "keep apart" for the same main name (spec 004, 5.5).
        refused = await patch_item(
            client, change_sets[2], third["id"], {"matchDecision": "different"}
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "changeset.no_match")
        assert await merged(client, change_sets[0]) == []
        assert await merged(client, change_sets[1]) == []
        if rename:
            response = await patch_item(
                client, change_sets[2], third["id"], {"edited": {"labelZh": "领料单"}}
            )
            assert response.status_code == 200
        assert await merged(client, change_sets[2]) == []
        found = [e for e in await working_version(db, ontology.id) if e.kind == "entity_type"]
        assert len(found) == types
