"""Alignment across pending change sets and the gaps of the name rules (spec 004).

Each test states what the alignment rework has to deliver; section 13 of the spec lists which
change makes each of them pass. They cover issue #40 (documents identified against the same
baseline), issue #36 (one-character names of new types) and related cases.
"""

import hashlib
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    KnownElement,
    build_proposals,
    sentences_of,
)
from ontology_platform.modules.ai.pipeline import make_extractor
from ontology_platform.modules.ai.prompts import (
    EntityTypeOut,
    PropertyOut,
    RelationOut,
    RelationsOut,
    ResolveOut,
    TermsOut,
    TypesOut,
)
from ontology_platform.modules.documents.models import Chunk, Document
from ontology_platform.modules.identity.models import Role
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.models import Ontology
from ontology_platform.modules.ontology.schemas import ElementCopy
from test_ai_extraction import ScriptedGateway, entity, prop, relation
from test_ai_pipeline import held
from test_ontology_support import accept_and_merge, add_elements, add_ontology, element, sign_in

MODELS = ExtractionModels(standard="std", reasoning="deep")
NO_RELATIONS = RelationsOut(relations=[], properties=[])


async def add_document(db: AsyncSession, ontology: Ontology, filename: str, text: str) -> UUID:
    document = Document(
        id=uuid4(),
        ontology_id=ontology.id,
        filename=filename,
        media_type="text/markdown",
        size_bytes=len(text.encode()),
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        storage_key=f"test/{filename}",
        status="extracting",
        progress={"step": "parse", "done": 1, "total": 1},
        uploaded_by=uuid4(),
    )
    db.add(document)
    await db.flush()
    db.add(Chunk(document_id=document.id, seq=0, text=text, char_count=len(text)))
    await db.commit()
    return document.id


def named[T: (RelationOut, PropertyOut)](item: T, local_name: str, sentence: str) -> T:
    return item.model_copy(update={"local_name": local_name, "sentence": sentence})


async def identify(
    app: FastAPI,
    scripts: Sequence[tuple[UUID, list[EntityTypeOut], RelationsOut]],
    resolver: Callable[[str], ResolveOut] | None = None,
) -> list[UUID]:
    """Identify every document before anything is merged: they all see the same baseline.

    This is what uploading several documents at once does; the worker takes them one by one.
    Each sees the change sets of the earlier ones as pending; `resolver` answers the resolve
    calls (by default: every type is a different concept from its candidates).
    """
    outputs: dict[str, list[BaseModel]] = {
        "extract.terms": [TermsOut(terms=[]) for _ in scripts],
        "extract.types": [TypesOut(entity_types=types) for _, types, _ in scripts],
        "extract.relations": [relations for _, _, relations in scripts],
    }
    session_factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    extract = make_extractor(session_factory, ScriptedGateway(outputs, resolver), MODELS)
    change_sets: list[UUID] = []
    for document_id, _, _ in scripts:
        change_set_id = await extract(document_id, held)
        assert change_set_id is not None
        change_sets.append(change_set_id)
    return change_sets


async def merged(client: AsyncClient, change_set_id: UUID) -> list[str]:
    """Accept everything, merge the way the review page does, and return the skip codes."""
    result = await accept_and_merge(client, change_set_id)
    skipped: list[dict[str, Any]] = result["skipped"]
    return [skip["code"] for skip in skipped]


async def working_version(db: AsyncSession, ontology_id: UUID) -> list[ElementCopy]:
    db.expire_all()
    return await ontology_service.list_alignment_elements(db, ontology_id)


def labelled(elements: Sequence[ElementCopy], kind: str, label: str) -> list[ElementCopy]:
    return [e for e in elements if e.kind == kind and e.label_zh == label]


# ---------- issue #40: two documents identified against the same baseline ----------

HEAT_TEXT = "每个炉次都在一座转炉上冶炼。"
TAPPING_TEXT = "转炉出钢时钢水流入钢包。转炉的公称容量为120吨。"


@pytest.mark.parametrize(
    "second_local_name",
    ["Converter", "BofConverter"],
    ids=["same-local-name", "other-local-name"],
)
async def test_documents_naming_one_concept_give_one_type_and_keep_what_hangs_on_it(
    app: FastAPI, client: AsyncClient, db: AsyncSession, second_local_name: str
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    first = await add_document(db, ontology, "转炉规程.md", HEAT_TEXT)
    second = await add_document(db, ontology, "出钢规程.md", TAPPING_TEXT)
    converter = f"new:{second_local_name}"
    first_change_set, second_change_set = await identify(
        app,
        [
            (
                first,
                [
                    entity("new:Converter", "转炉", sentence="0.1"),
                    entity("new:Heat", "炉次", sentence="0.1"),
                ],
                RelationsOut(
                    relations=[
                        named(
                            relation("new:Heat", "new:Converter", "冶炼于", None),
                            "smeltedIn",
                            "0.1",
                        )
                    ],
                    properties=[],
                ),
            ),
            (
                second,
                [
                    entity(converter, "转炉", sentence="0.1"),
                    entity("new:Ladle", "钢包", sentence="0.1"),
                ],
                RelationsOut(
                    relations=[
                        named(
                            relation(converter, "new:Ladle", "出钢至", None),
                            "tapsInto",
                            "0.1",
                        )
                    ],
                    properties=[
                        named(
                            prop(converter, "公称容量"),
                            "nominalCapacity",
                            "0.2",
                        )
                    ],
                ),
            ),
        ],
    )
    await sign_in(client, db, Role.ADMIN)

    assert await merged(client, first_change_set) == []
    second_skips = await merged(client, second_change_set)

    elements = await working_version(db, ontology_id)
    converters = labelled(elements, "entity_type", "转炉")
    # One concept is one type, whatever local name the model gave it in each document.
    assert len(converters) == 1
    # Nothing of the second document is skipped: its relation and property hang on that type.
    assert second_skips == []
    [tapping] = labelled(elements, "relation_type", "出钢至")
    [capacity] = labelled(elements, "property", "公称容量")
    assert (tapping.domain_id, capacity.domain_id) == (converters[0].id, converters[0].id)


# ---------- issue #36: one-character names of new types ----------

CHUNK = ChunkText(id=uuid4(), seq=0, text="钢水由钢包吊运至精炼炉。每个炉次使用一座转炉冶炼。")


def test_new_types_with_the_same_one_character_name_become_one_type() -> None:
    types = [
        entity("new:Steel", "钢"),
        entity("new:SteelMaterial", "钢", synonyms=["钢材"]),
    ]
    proposals = build_proposals([CHUNK], [], types, NO_RELATIONS)

    # As for an existing type named 钢 (#33): the whole name is the same character.
    assert [p.fields["labelZh"] for p in proposals] == ["钢"]


@pytest.mark.parametrize("furnace_first", [False, True], ids=["synonym-first", "label-first"])
def test_a_one_character_name_that_is_another_new_types_synonym_is_a_possible_duplicate(
    furnace_first: bool,
) -> None:
    types = [
        entity("new:Converter", "转炉", synonyms=["炉"]),
        entity("new:Furnace", "炉"),
    ]
    if furnace_first:
        types.reverse()
    proposals = build_proposals([CHUNK], [], types, NO_RELATIONS)

    # 炉 may be 转炉: the two stay apart and a reviewer decides, as with an existing type (#33).
    flagged = [p.fields["labelZh"] for p in proposals if "possible_duplicate" in p.flags]
    assert flagged == [types[1].label_zh]


# ---------- issue #40, further cases: pending change sets that touch the same elements ----------


async def test_pending_change_sets_adding_synonyms_to_one_type_both_take_effect(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    grade_ref = str(grade.id)
    first = await add_document(db, ontology, "术语.md", "钢种又称牌号。")
    second = await add_document(db, ontology, "检验规范.md", "钢种在检验单上写作钢号。")
    first_change_set, second_change_set = await identify(
        app,
        [
            (
                first,
                [
                    entity(
                        grade_ref,
                        "钢种",
                        synonyms=["牌号"],
                        sentence="0.1",
                    )
                ],
                NO_RELATIONS,
            ),
            (
                second,
                [
                    entity(
                        grade_ref,
                        "钢种",
                        synonyms=["钢号"],
                        sentence="0.1",
                    )
                ],
                NO_RELATIONS,
            ),
        ],
    )
    await sign_in(client, db, Role.ADMIN)

    assert await merged(client, first_change_set) == []
    # Adding a synonym does not depend on what the type's other fields were: the first merge
    # moving the revision on must not make the second update stale.
    assert await merged(client, second_change_set) == []
    [stored] = labelled(await working_version(db, ontology_id), "entity_type", "钢种")
    assert {synonym.text for synonym in stored.synonyms} == {"牌号", "钢号"}


async def test_pending_change_sets_proposing_one_relation_give_one_relation(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    heat = element(ontology, "entity_type", "Heat", "炉次")
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, heat, grade)
    heat_ref, grade_ref = str(heat.id), str(grade.id)
    text = "每个炉次只冶炼一个钢种。"
    first = await add_document(db, ontology, "转炉规程.md", text)
    second = await add_document(db, ontology, "质量手册.md", text + "钢种由计划确定。")

    def smelts(local_name: str) -> RelationsOut:
        link = named(relation(heat_ref, grade_ref, "冶炼", None), local_name, "0.1")
        return RelationsOut(relations=[link], properties=[])

    first_change_set, second_change_set = await identify(
        app, [(first, [], smelts("smelts")), (second, [], smelts("produces"))]
    )
    await sign_in(client, db, Role.ADMIN)

    assert await merged(client, first_change_set) == []
    assert await merged(client, second_change_set) == []
    # The model named the same link differently in the two documents.
    assert len(labelled(await working_version(db, ontology_id), "relation_type", "冶炼")) == 1


async def test_pending_change_sets_reusing_a_local_name_for_other_elements_keep_both(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    slab = element(ontology, "entity_type", "Slab", "板坯")
    coil = element(ontology, "entity_type", "Coil", "钢卷")
    await add_elements(db, slab, coil)
    slab_id, coil_id = slab.id, coil.id
    first = await add_document(db, ontology, "连铸规程.md", "每块板坯记录厚度。")
    second = await add_document(db, ontology, "热轧规程.md", "每个钢卷记录厚度。")

    def thickness(domain: UUID) -> RelationsOut:
        measured = named(prop(str(domain), "厚度"), "thickness", "0.1")
        return RelationsOut(relations=[], properties=[measured])

    first_change_set, second_change_set = await identify(
        app,
        [
            (first, [], thickness(slab_id)),
            (second, [], thickness(coil_id)),
        ],
    )
    await sign_in(client, db, Role.ADMIN)

    assert await merged(client, first_change_set) == []
    # 板坯 and 钢卷 each have a thickness; the local name the model chose twice is not a reason
    # to lose the second one.
    assert await merged(client, second_change_set) == []
    properties = labelled(await working_version(db, ontology_id), "property", "厚度")
    assert {p.domain_id for p in properties} == {slab_id, coil_id}


# ---------- deleted elements ----------


async def test_a_type_deleted_earlier_can_be_identified_again(
    app: FastAPI, client: AsyncClient, db: AsyncSession
) -> None:
    ontology = await add_ontology(db)
    ontology_id = ontology.id
    await add_elements(
        db, element(ontology, "entity_type", "Converter", "转炉", status="deprecated")
    )
    document = await add_document(db, ontology, "转炉规程.md", HEAT_TEXT)
    [change_set] = await identify(
        app,
        [
            (
                document,
                [
                    entity("new:Converter", "转炉", sentence="0.1"),
                    entity("new:Heat", "炉次", sentence="0.1"),
                ],
                RelationsOut(
                    relations=[
                        named(
                            relation("new:Heat", "new:Converter", "冶炼于", None),
                            "smeltedIn",
                            "0.1",
                        )
                    ],
                    properties=[],
                ),
            )
        ],
    )
    await sign_in(client, db, Role.ADMIN)

    # A deleted element still holds its local name. The type has to come back all the same,
    # and the relation with it.
    assert await merged(client, change_set) == []
    elements = await working_version(db, ontology_id)
    [converter] = labelled(elements, "entity_type", "转炉")
    [smelted_in] = labelled(elements, "relation_type", "冶炼于")
    assert smelted_in.range_id == converter.id


# ---------- relations: what counts as the same relation, and as direct evidence ----------


def test_a_relation_with_an_existing_label_and_domain_but_another_range_is_proposed() -> None:
    heat = KnownElement(id=uuid4(), kind="entity_type", local_name="Heat", label_zh="炉次")
    ladle = KnownElement(id=uuid4(), kind="entity_type", local_name="Ladle", label_zh="钢包")
    converter = KnownElement(
        id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉"
    )
    uses_ladle = KnownElement(
        id=uuid4(),
        kind="relation_type",
        local_name="usesLadle",
        label_zh="使用",
        domain_id=heat.id,
        range_id=ladle.id,
    )
    relations = RelationsOut(
        relations=[
            named(
                relation(str(heat.id), str(converter.id), "使用", None),
                "usesConverter",
                "0.2",
            )
        ],
        properties=[],
    )
    proposals = build_proposals([CHUNK], [heat, ladle, converter, uses_ladle], [], relations)

    # 炉次 使用 钢包 exists; 炉次 使用 转炉 is another link and must reach the reviewer.
    assert [(p.kind, p.fields["labelZh"], p.fields["rangeRef"]) for p in proposals] == [
        ("relation_type", "使用", str(converter.id))
    ]


def test_relation_evidence_does_not_depend_on_where_the_lines_wrap() -> None:
    sentence = "每个炉次的钢水出钢后装入钢包，随后由行车吊运至精炼炉。"
    # Text extracted from a PDF breaks lines where the page does, here after 随后.
    wrapped = sentence.replace("随后", "随后\n")
    types = [entity("new:Ladle", "钢包"), entity("new:Refiner", "精炼炉")]
    relations = RelationsOut(
        # The model cites the sentence by its number: one sentence however the lines wrap.
        relations=[relation("new:Ladle", "new:Refiner", "运往", "0.1")],
        properties=[],
    )

    def kept(text: str) -> list[str]:
        proposals = build_proposals([ChunkText(id=uuid4(), seq=0, text=text)], [], types, relations)
        return [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"]

    assert kept(sentence) == ["运往"]
    assert kept(wrapped) == ["运往"]
    [one] = sentences_of([ChunkText(id=uuid4(), seq=0, text=wrapped)])
    assert one.text == wrapped
