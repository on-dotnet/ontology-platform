"""Entity resolution: the resolve call, its guardrails and the prompt sizes (spec 004, 4 and 6)."""

from uuid import uuid4

from pydantic import BaseModel

from ontology_platform.modules.ai.candidates import Names
from ontology_platform.modules.ai.extraction import (
    RELATIONS_CATALOG_MAX,
    RESOLVE_BATCH,
    TYPES_CONTEXT_MAX,
    ChunkText,
    Decision,
    ExtractionModels,
    Extractor,
    KnownElement,
    PendingType,
    Proposal,
    ProposedMatch,
    build_proposals,
    catalog_for,
    mark_late_candidates,
    relations_catalog,
    resolve_requests,
    types_context,
)
from ontology_platform.modules.ai.prompts import (
    DecisionOut,
    EntityTypeOut,
    PropertyOut,
    RelationsOut,
    ResolveOut,
    TermOut,
    TermsOut,
    TypesOut,
)
from test_ai_extraction import ScriptedGateway, decide, entity, judge, relation

CHUNK = ChunkText(id=uuid4(), seq=0, text="钢水由钢包吊运至精炼炉。每个炉次使用一座转炉冶炼。")
NO_RELATIONS = RelationsOut(relations=[], properties=[])
CONVERTER = KnownElement(id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉")
FURNACE = KnownElement(
    id=uuid4(), kind="entity_type", local_name="Furnace", label_zh="氧气转炉炉体"
)


async def nothing(step: str, done: int, total: int) -> None:
    pass


async def extract(
    gateway: ScriptedGateway,
    known: list[KnownElement],
    pending: list[PendingType] | None = None,
    chunks: list[ChunkText] | None = None,
) -> tuple[list[Proposal], Extractor]:
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))
    proposals = await extractor.run(
        document_id=uuid4(),
        title="t",
        chunks=chunks or [CHUNK],
        known=known,
        progress=nothing,
        pending=pending or [],
    )
    return proposals, extractor


def outputs(
    types: list[EntityTypeOut], relations: RelationsOut = NO_RELATIONS
) -> dict[str, list[BaseModel]]:
    term = TermOut(name="转炉", english=None, definition=None, category="entity", quotes=[])
    return {
        "extract.terms": [TermsOut(terms=[term])],
        "extract.types": [TypesOut(entity_types=types)],
        "extract.relations": [relations],
    }


async def test_no_call_without_candidates_and_one_call_with_the_standard_model() -> None:
    gateway = ScriptedGateway(outputs([entity("new:Ladle", "钢包")]))
    await extract(gateway, [CONVERTER])
    assert [purpose for purpose, _ in gateway.calls] == [
        "extract.terms",
        "extract.types",
        "extract.relations",
    ]

    gateway = ScriptedGateway(outputs([entity("new:Bof", "氧气转炉")]))
    await extract(gateway, [CONVERTER])
    assert ("extract.resolve", "std") in gateway.calls
    # Resolve runs between the types and the relations stage.
    assert [purpose for purpose, _ in gateway.calls].index("extract.resolve") == 2


async def test_types_of_more_than_one_batch_are_judged_in_several_calls() -> None:
    known = [
        KnownElement(id=uuid4(), kind="entity_type", local_name=f"T{n}", label_zh=f"设备{n:03d}")
        for n in range(RESOLVE_BATCH + 5)
    ]
    types = [entity(f"new:N{n}", f"设备{n:03d}型") for n in range(RESOLVE_BATCH + 5)]
    gateway = ScriptedGateway(outputs(types))
    _, extractor = await extract(gateway, known)
    calls = [text for purpose, text in gateway.texts if purpose == "extract.resolve"]
    assert len(calls) == 2
    assert calls[0].count("\nT") == RESOLVE_BATCH
    assert len(extractor.last.requests) == RESOLVE_BATCH + 5
    assert all(len(r.candidates) <= 3 for r in extractor.last.requests)


async def test_answers_about_what_was_not_asked_are_ignored() -> None:
    # G2: a type or candidate that was not sent counts for nothing; the type is a possible
    # duplicate for want of a usable answer (G5).
    def resolver(text: str) -> ResolveOut:

        return ResolveOut(
            decisions=[
                DecisionOut(type="T1", candidate="C9", verdict="same", reason="x"),
                DecisionOut(type="T7", candidate="C1", verdict="different", reason="x"),
            ]
        )

    gateway = ScriptedGateway(outputs([entity("new:Bof", "氧气转炉")]), resolver)
    [created], _ = await extract(gateway, [CONVERTER])
    assert created.flags[0] == "possible_duplicate"
    assert created.match == ProposedMatch("possible", element_id=CONVERTER.id)


def test_two_candidates_judged_the_same_make_an_unsure_one_of_the_best() -> None:
    # G6: one new type goes into at most one target.
    types = [entity("new:Bof", "氧气转炉", synonyms=["转炉炉体"])]
    [request] = resolve_requests([CONVERTER, FURNACE], types)
    decisions = {
        0: [Decision("same", candidate.key, "r") for candidate in request.candidates],
    }
    [created] = build_proposals(
        [CHUNK], [CONVERTER, FURNACE], types, NO_RELATIONS, decisions=decisions
    )
    best = max(request.candidates, key=lambda candidate: candidate.score.value)
    assert created.match is not None
    assert created.match.kind == "possible"
    assert str(created.match.element_id) == best.key[1]


def test_a_type_is_not_the_same_as_its_parent_or_child() -> None:
    # G7: judged the same as its own parent, it is at most a possible duplicate.
    types = [entity("new:Bof", "氧气转炉", parent=str(CONVERTER.id))]
    decisions = decide(types, [CONVERTER], {"氧气转炉": ("转炉", "same")})
    [created] = build_proposals([CHUNK], [CONVERTER], types, NO_RELATIONS, decisions=decisions)
    assert created.match == ProposedMatch("possible", element_id=CONVERTER.id, reason="理由")
    assert created.fields["parentRef"] == str(CONVERTER.id)

    child = [
        entity("new:Furnace", "炉体"),
        entity("new:BofFurnace", "转炉炉体", parent="new:Furnace"),
    ]
    decisions = decide(child, [], {"转炉炉体": ("炉体", "same")})
    created_types = build_proposals([CHUNK], [], child, NO_RELATIONS, decisions=decisions)
    assert [p.fields["labelZh"] for p in created_types] == ["炉体", "转炉炉体"]
    assert created_types[1].match is not None
    assert created_types[1].match.kind == "possible"


def pending_type(label: str, synonyms: tuple[str, ...] = ()) -> PendingType:
    return PendingType(
        item_id=uuid4(),
        change_set_id=uuid4(),
        change_set_title="识别：出钢规程.md",
        label_zh=label,
        synonyms=synonyms,
    )


async def test_pending_items_are_candidates_and_those_of_the_same_main_name_are_not_judged() -> (
    None
):
    ladle = pending_type("钢水包", ("大包",))
    converter = pending_type("转炉")
    types = [entity("new:Ladle", "钢包"), entity("new:Converter", "转炉")]
    gateway = ScriptedGateway(outputs(types), judge({"钢包": ("钢水包", "same")}))
    proposals, extractor = await extract(gateway, [], [ladle, converter])

    # 转炉 has the main name of a pending item (G1): not judged, created with a record of it, so
    # that the merge follows that item.
    assert [r.index for r in extractor.last.requests] == [0]
    [(_, text)] = [entry for entry in gateway.texts if entry[0] == "extract.resolve"]
    assert "C1 | 钢水包 | 大包 |" in text
    assert [(p.fields["labelZh"], p.match) for p in proposals] == [
        ("钢包", ProposedMatch("same", item_id=ladle.item_id, reason="理由")),
        ("转炉", ProposedMatch("name", item_id=converter.item_id)),
    ]


def test_with_many_existing_types_each_call_shows_at_most_its_limit() -> None:
    known = [
        KnownElement(id=uuid4(), kind="entity_type", local_name=f"T{n}", label_zh=f"类型{n:04d}")
        for n in range(1000)
    ]

    context = types_context(known, ["类型0007", "钢包"])
    assert len(context) <= TYPES_CONTEXT_MAX
    assert context[0].label_zh == "类型0007"
    types = [entity("new:Ladle", "钢包"), entity(str(known[3].id), "类型0003")]
    chunk = ChunkText(id=uuid4(), seq=0, text="钢包运往类型0500。")
    lines = catalog_for(relations_catalog(types, known)[0], [chunk])
    assert len(lines) <= RELATIONS_CATALOG_MAX
    # Named in the batch first, then the document's own types; other existing types are out.
    assert [line[0].split(" | ")[1] for line in lines] == ["钢包", "类型0500", "类型0003"]
    requests = resolve_requests(known, [entity("new:X", "类型0001型")])
    assert all(len(request.candidates) <= 3 for request in requests)


async def test_the_trimmed_types_are_counted() -> None:
    known = [
        KnownElement(id=uuid4(), kind="entity_type", local_name=f"T{n}", label_zh=f"类型{n:04d}")
        for n in range(TYPES_CONTEXT_MAX + 10)
    ]
    gateway = ScriptedGateway(outputs([]))
    _, extractor = await extract(gateway, known)
    assert extractor.last.trimmed["extract.types"] > 0
    [(_, text)] = [entry for entry in gateway.texts if entry[0] == "extract.types"]
    assert text.count("\n- ") <= TYPES_CONTEXT_MAX + 1  # the term line is the one more


def test_candidates_that_appeared_meanwhile_are_marked_without_a_model() -> None:
    types = [
        entity("new:Ladle", "钢包"),
        entity("new:Converter", "转炉"),
        entity("new:Billet", "钢坯"),
    ]
    proposals = build_proposals([CHUNK], [], types, NO_RELATIONS, decisions=decide(types, []))
    late_element = uuid4()
    late = [
        (
            ProposedMatch("possible", element_id=late_element),
            Names.of("钢水包", None, ()),
            "钢水包",
            None,
        ),
        # The same main name: left to the merge (G1).
        (ProposedMatch("possible", item_id=uuid4()), Names.of("转炉", None, ()), "转炉", None),
    ]
    mark_late_candidates(proposals, late)
    assert [(p.fields["labelZh"], p.match) for p in proposals] == [
        ("钢包", ProposedMatch("possible", element_id=late_element)),
        ("转炉", None),
        ("钢坯", None),
    ]
    assert ["possible_duplicate" in p.flags for p in proposals] == [True, False, False]


def test_relations_hang_on_a_type_judged_the_same_as_an_existing_one() -> None:
    # The relation refers to the new item; the merge plan resolves it into the existing type.
    types = [entity("new:Bof", "氧气转炉", synonyms=["转炉"])]
    heat = KnownElement(id=uuid4(), kind="entity_type", local_name="Heat", label_zh="炉次")
    rels = RelationsOut(
        relations=[relation(str(heat.id), "new:Bof", "使用", "0.2")],
        properties=[
            PropertyOut(
                label_zh="容量",
                local_name="capacity",
                domain="new:Bof",
                datatype="decimal",
                unit="t",
                required=False,
                multiple=False,
                definition_zh=None,
                confidence=0.8,
                sentence=None,
            )
        ],
    )
    decisions = decide(types, [CONVERTER, heat], {"氧气转炉": ("转炉", "same")})
    proposals = build_proposals([CHUNK], [CONVERTER, heat], types, rels, decisions=decisions)
    assert [(p.kind, p.fields.get("domainRef"), p.fields.get("rangeRef")) for p in proposals] == [
        ("entity_type", None, None),
        ("relation_type", str(heat.id), "new:Bof"),
        ("property", "new:Bof", None),
    ]
    assert isinstance(proposals[0].match, ProposedMatch)
    assert proposals[0].match.element_id == CONVERTER.id


def test_a_type_is_not_the_same_as_a_parent_given_by_a_ref_that_landed_elsewhere() -> None:
    # G7 once the refs are resolved: new:Converter is the existing 转炉 (G1).
    types = [
        entity("new:Converter", "转炉"),
        entity("new:Bof", "氧气转炉", parent="new:Converter"),
    ]
    decisions = decide(types, [CONVERTER], {"氧气转炉": ("转炉", "same")})
    [created] = build_proposals([CHUNK], [CONVERTER], types, NO_RELATIONS, decisions=decisions)
    assert created.match == ProposedMatch("possible", element_id=CONVERTER.id, reason="理由")


def test_a_verdict_of_different_about_one_candidate_leaves_the_others_unjudged() -> None:
    # G5: only the candidate named is different; the one left without an answer is unsure.
    types = [entity("new:Bof", "氧气转炉", synonyms=["转炉炉体"])]
    [request] = resolve_requests([CONVERTER, FURNACE], types)
    named = next(c.key for c in request.candidates if c.key[1] == str(FURNACE.id))
    decisions = {0: [Decision("different", named)]}
    [created] = build_proposals(
        [CHUNK], [CONVERTER, FURNACE], types, NO_RELATIONS, decisions=decisions
    )
    assert created.match == ProposedMatch("possible", element_id=CONVERTER.id)
