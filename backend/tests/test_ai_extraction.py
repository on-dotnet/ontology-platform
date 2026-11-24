"""Staged extraction with a scripted model: alignment, references, evidence grounding, progress."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai.extraction import (
    TYPES_BATCH_TERMS,
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    Proposal,
    batches,
    build_proposals,
    merge_types,
    normalize,
)
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.prompts import (
    EntityTypeOut,
    PropertyOut,
    Quote,
    RelationOut,
    RelationsOut,
    TermOut,
    TermsOut,
    TypesOut,
)

DOC = uuid4()
CHUNK_A = ChunkText(id=uuid4(), seq=0, text="每个炉次只冶炼一个钢种。钢水由钢包吊运至精炼炉。")
CHUNK_B = ChunkText(
    id=uuid4(), seq=1, text="一个浇次由若干个炉次的钢水连续浇铸而成。出钢温度单位为℃。"
)
EXISTING_GRADE = KnownElement(
    id=uuid4(), kind="entity_type", local_name="SteelGrade", label_zh="钢种", synonyms=("牌号",)
)


class ScriptedGateway:
    """Returns canned outputs per purpose and records what it was asked."""

    def __init__(self, outputs: dict[str, list[BaseModel]]) -> None:
        self.outputs = {purpose: list(items) for purpose, items in outputs.items()}
        self.calls: list[tuple[str, str]] = []
        self.texts: list[tuple[str, str]] = []

    async def structured[T: BaseModel](
        self,
        *,
        purpose: str,
        model: str,
        instructions: str,
        text: str,
        schema: type[T],
        files: Sequence[InputFile] = (),
        document_id: Any = None,
    ) -> T:
        self.calls.append((purpose, model))
        self.texts.append((purpose, text))
        result = self.outputs[purpose].pop(0)
        assert isinstance(result, schema)
        return result

    async def ping(self) -> bool:
        return True


def quote(chunk: int, text: str) -> Quote:
    return Quote(chunk=chunk, text=text)


def entity(ref: str, label: str, name: str, **extra: Any) -> EntityTypeOut:
    values: dict[str, Any] = {
        "ref": ref,
        "label_zh": label,
        "label_en": None,
        "local_name": name,
        "definition_zh": None,
        "synonyms": [],
        "parent": None,
        "confidence": 0.9,
        "rationale": "r",
        "quotes": [],
    }
    values.update(extra)
    return EntityTypeOut(**values)


def relation(domain: str, range_: str, label: str, quotes: list[Quote]) -> RelationOut:
    return RelationOut(
        label_zh=label,
        label_en=None,
        local_name="belongsTo",
        domain=domain,
        range=range_,
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=0.8,
        rationale="r",
        quotes=quotes,
    )


def outputs(types: list[EntityTypeOut], rels: RelationsOut) -> dict[str, list[BaseModel]]:
    term = TermOut(name="炉次", english="Heat", definition=None, category="entity", quotes=[])
    return {
        "extract.terms": [TermsOut(terms=[term])],
        "extract.types": [TypesOut(entity_types=types)],
        "extract.relations": [rels],
    }


async def run(
    gateway: ScriptedGateway, known: Sequence[KnownElement] = ()
) -> tuple[list[Proposal], list[tuple[str, int, int]]]:
    steps: list[tuple[str, int, int]] = []

    async def progress(step: str, done: int, total: int) -> None:
        steps.append((step, done, total))

    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))
    proposals = await extractor.run(
        document_id=DOC, title="t", chunks=[CHUNK_A, CHUNK_B], known=known, progress=progress
    )
    return proposals, steps


def by_label(proposals: list[Proposal], label: str) -> Proposal:
    return next(p for p in proposals if p.fields.get("labelZh") == label)


async def test_stages_use_the_configured_models_and_report_progress() -> None:
    gateway = ScriptedGateway(outputs([], RelationsOut(relations=[], properties=[])))
    _, steps = await run(gateway)

    assert gateway.calls == [
        ("extract.terms", "std"),
        ("extract.types", "deep"),
        ("extract.relations", "std"),
    ]
    assert [s[0] for s in steps] == [
        "terms",
        "terms",
        "types",
        "types",
        "relations",
        "relations",
        "changeset",
        "changeset",
    ]
    assert steps[-1] == ("changeset", 1, 1)


async def test_new_types_get_temp_refs_and_grounded_evidence() -> None:
    types = [entity("new:Heat", "炉次", "Heat", quotes=[quote(0, "每个炉次只冶炼一个钢种")])]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    heat = by_label(proposals, "炉次")
    assert (heat.op, heat.kind, heat.temp_ref) == ("create", "entity_type", "new:Heat")
    assert heat.flags == []
    assert heat.confidence == 0.9
    [evidence] = heat.evidence
    assert evidence.chunk_id == CHUNK_A.id
    assert CHUNK_A.text[evidence.char_start : evidence.char_end] == "每个炉次只冶炼一个钢种"


async def test_quote_not_in_the_text_is_flagged_and_penalised() -> None:
    types = [entity("new:Heat", "炉次", "Heat", quotes=[quote(0, "炉次是冶炼的基本单位")])]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    heat = by_label(proposals, "炉次")
    assert heat.flags == ["evidence_not_found"]
    assert heat.confidence == 0.45
    assert heat.evidence[0].char_start is None


async def test_quote_found_in_another_chunk_than_cited() -> None:
    types = [
        entity(
            "new:CastingSequence",
            "浇次",
            "CastingSequence",
            quotes=[quote(0, "一个浇次由若干个炉次")],
        )
    ]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    assert by_label(proposals, "浇次").evidence[0].chunk_id == CHUNK_B.id


async def test_existing_type_matched_by_synonym_only_gets_new_synonyms() -> None:
    types = [entity("new:Grade", "牌号", "Grade", synonyms=["钢号"], quotes=[quote(0, "一个钢种")])]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[]))), [EXISTING_GRADE]
    )

    [update] = proposals
    assert (update.op, update.target_element_id) == ("update", EXISTING_GRADE.id)
    assert update.fields == {"synonyms": [{"lang": "zh", "text": "钢号"}]}


async def test_existing_type_without_news_produces_nothing() -> None:
    types = [entity(str(EXISTING_GRADE.id), "钢种", "SteelGrade", synonyms=["牌号"])]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[]))), [EXISTING_GRADE]
    )
    assert proposals == []


async def test_relations_resolve_refs_and_drop_unknown_types() -> None:
    types = [
        entity("new:Heat", "炉次", "Heat"),
        entity("new:CastingSequence", "浇次", "CastingSequence"),
    ]
    rels = RelationsOut(
        relations=[
            relation(
                "new:Heat",
                "new:CastingSequence",
                "属于浇次",
                [quote(1, "一个浇次由若干个炉次的钢水")],
            ),
            relation("new:Heat", str(EXISTING_GRADE.id), "冶炼钢种", [quote(0, "只冶炼一个钢种")]),
            relation("new:Heat", "new:Ghost", "幽灵关系", []),
            relation("new:Heat", "new:CastingSequence", "属于浇次", []),  # duplicate
        ],
        properties=[
            PropertyOut(
                label_zh="出钢温度",
                label_en="Tapping temperature",
                local_name="tapping temperature",  # not camelCase: replaced
                domain="new:Heat",
                datatype="decimal",
                unit="℃",
                required=True,
                multiple=False,
                definition_zh=None,
                confidence=0.7,
                rationale="r",
                quotes=[quote(1, "出钢温度单位为℃")],
            )
        ],
    )
    proposals, _ = await run(ScriptedGateway(outputs(types, rels)), [EXISTING_GRADE])

    relations = [p for p in proposals if p.kind == "relation_type"]
    assert [r.fields["labelZh"] for r in relations] == ["属于浇次", "冶炼钢种"]
    assert relations[0].fields["domainRef"] == "new:Heat"
    assert relations[0].fields["rangeRef"] == "new:CastingSequence"
    assert relations[1].fields["rangeRef"] == str(EXISTING_GRADE.id)
    assert relations[0].fields["localName"] == "belongsTo"
    assert relations[1].fields["localName"] == "belongsTo2"  # unique within the ontology
    [prop] = [p for p in proposals if p.kind == "property"]
    assert prop.fields["localName"] == "attribute"
    assert (prop.fields["datatype"], prop.fields["unit"], prop.fields["required"]) == (
        "decimal",
        "℃",
        True,
    )


async def test_parents_resolve_and_duplicate_new_types_merge() -> None:
    types = [
        entity("new:Furnace", "炉子", "Furnace"),
        entity("new:LadleFurnace", "精炼炉", "LadleFurnace", parent="new:Furnace"),
        entity("new:LF", "精炼炉", "LF"),  # same label: merged into the first
        entity("new:Self", "自引用", "Self", parent="new:Self"),
    ]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    labels = [p.fields["labelZh"] for p in proposals]
    assert labels == ["炉子", "精炼炉", "自引用"]
    assert by_label(proposals, "精炼炉").fields["parentRef"] == "new:Furnace"
    assert by_label(proposals, "自引用").fields["parentRef"] is None


def test_normalize_and_batches() -> None:
    assert normalize(" ＬＦ 精炼炉 ") == normalize("lf精炼炉")  # noqa: RUF001 (full-width on purpose)
    chunks = [ChunkText(id=UUID(int=i), seq=i, text="x" * 3000) for i in range(5)]
    assert [len(group) for group in batches(chunks, limit=8000)] == [2, 2, 1]


async def test_a_new_type_can_have_an_existing_parent() -> None:
    child = entity("new:Q235B", "Q235B 钢", "Q235B", parent=str(EXISTING_GRADE.id))
    gateway = ScriptedGateway(outputs([child], RelationsOut(relations=[], properties=[])))
    proposals, _ = await run(gateway, known=[EXISTING_GRADE])

    assert by_label(proposals, "Q235B 钢").fields["parentRef"] == str(EXISTING_GRADE.id)


async def test_updates_of_one_existing_type_are_merged() -> None:
    types = [
        entity(str(EXISTING_GRADE.id), "钢种", "SteelGrade", synonyms=["钢级"]),
        entity("new:Grade", "牌号", "Grade", synonyms=["钢号", "钢级"]),
    ]
    gateway = ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    proposals, _ = await run(gateway, known=[EXISTING_GRADE])

    [update] = [p for p in proposals if p.op == "update"]
    assert update.target_element_id == EXISTING_GRADE.id
    assert update.target_revision == EXISTING_GRADE.revision
    assert [s["text"] for s in update.fields["synonyms"]] == ["钢级", "钢号"]
    assert not [p for p in proposals if p.op == "create"]


async def test_references_to_elements_that_are_not_types_are_dropped() -> None:
    produced_by = KnownElement(
        id=uuid4(),
        kind="relation_type",
        local_name="producedBy",
        label_zh="生产于",
        domain_id=EXISTING_GRADE.id,
        range_id=EXISTING_GRADE.id,
    )
    child = entity("new:Heat", "炉次", "Heat", parent=str(produced_by.id))
    rels = RelationsOut(
        relations=[relation(str(produced_by.id), str(EXISTING_GRADE.id), "包含", [])],
        properties=[],
    )
    gateway = ScriptedGateway(outputs([child], rels))
    proposals, _ = await run(gateway, known=[EXISTING_GRADE, produced_by])

    assert by_label(proposals, "炉次").fields["parentRef"] is None
    assert [p.kind for p in proposals] == ["entity_type"]


def term(name: str, **extra: Any) -> TermOut:
    values: dict[str, Any] = {
        "name": name,
        "english": None,
        "definition": None,
        "category": "entity",
        "quotes": [],
    }
    values.update(extra)
    return TermOut(**values)


def types_texts(gateway: ScriptedGateway) -> list[str]:
    return [text for purpose, text in gateway.texts if purpose == "extract.types"]


async def test_few_terms_are_typed_in_one_call_with_an_unchanged_prompt() -> None:
    gateway = ScriptedGateway(
        {
            "extract.terms": [
                TermsOut(terms=[term("炉次", english="Heat", quotes=[quote(0, "每个炉次")])]),
                TermsOut(terms=[term("浇次", category="other", definition="连续浇铸的炉次")]),
            ],
            "extract.types": [TypesOut(entity_types=[])],
            "extract.relations": [RelationsOut(relations=[], properties=[])] * 2,
        }
    )
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    # Two chunk batches, so terms come from two calls but are typed together.
    long_a = ChunkText(id=CHUNK_A.id, seq=0, text="每个炉次" + "。" * 8100)
    await extractor.run(
        document_id=DOC,
        title="规程",
        chunks=[long_a, CHUNK_B],
        known=[EXISTING_GRADE],
        progress=progress,
    )

    # The prompt documents with at most TYPES_BATCH_TERMS terms were typed with before.
    assert types_texts(gateway) == [
        "Document: 规程\n\n"
        "Existing entity types (id | label | synonyms):\n"
        f"- {EXISTING_GRADE.id} | 钢种 | 牌号\n"
        "\n"
        "Candidate terms (category | name | english | definition | quotes):\n"
        "- entity | 炉次 | Heat |  | [chunk 0] 每个炉次\n"
        "- other | 浇次 |  | 连续浇铸的炉次 | "
    ]


async def test_many_terms_are_typed_in_batches_that_see_earlier_types() -> None:
    names = [f"术语{index}" for index in range(TYPES_BATCH_TERMS + 10)]
    first = [
        entity("new:Heat", "炉次", "Heat", synonyms=["炉"], quotes=[quote(0, "每个炉次")]),
        entity("new:Furnace", "炉子", "Furnace"),
    ]
    second = [
        # The second batch reuses a type of the first one and adds what it knows.
        entity(
            "new:Heat",
            "炉次",
            "Heat",
            synonyms=["熔炼炉次"],
            definition_zh="一次冶炼",
            parent="new:Furnace",
            quotes=[quote(0, "只冶炼一个钢种")],
        ),
        entity("new:Cast", "浇次", "Cast"),
    ]
    gateway = ScriptedGateway(
        {
            "extract.terms": [TermsOut(terms=[term(name) for name in names]), TermsOut(terms=[])],
            "extract.types": [TypesOut(entity_types=first), TypesOut(entity_types=second)],
            "extract.relations": [RelationsOut(relations=[], properties=[])] * 2,
        }
    )
    proposals, steps = await run(gateway)

    first_text, second_text = types_texts(gateway)
    assert f"- entity | {names[TYPES_BATCH_TERMS - 1]} |" in first_text
    assert f"- entity | {names[TYPES_BATCH_TERMS]} |" not in first_text
    assert f"- entity | {names[TYPES_BATCH_TERMS]} |" in second_text
    assert "Entity types proposed from earlier terms of this document" not in first_text
    assert "- new:Heat | 炉次 | 炉" in second_text
    assert [step for step in steps if step[0] == "types"] == [
        ("types", 0, 2),
        ("types", 1, 2),
        ("types", 2, 2),
    ]
    assert [p.fields["labelZh"] for p in proposals] == ["炉次", "炉子", "浇次"]
    heat = by_label(proposals, "炉次")
    assert [s["text"] for s in heat.fields["synonyms"]] == ["炉", "熔炼炉次"]
    assert heat.fields["definitionZh"] == "一次冶炼"
    assert heat.fields["parentRef"] == "new:Furnace"
    assert len(heat.evidence) == 2


def test_a_single_batch_of_types_is_kept_as_the_model_returned_it() -> None:
    batch = [
        entity("new:Heat", "炉次", "Heat"),
        entity("new:Heat", "炉次", "Heat2", synonyms=["炉"]),
        entity("new:LF", "精炼炉", "LF"),
        entity("new:LadleFurnace", "精炼炉", "LadleFurnace"),
    ]
    assert merge_types([], batch) == batch


def test_a_later_batch_does_not_extend_a_ref_an_earlier_batch_gave_to_two_types() -> None:
    found = [entity("new:Ladle", "钢包", "Ladle"), entity("new:Ladle", "行车", "Crane")]
    later = entity("new:Ladle", "钢包", "Ladle", synonyms=["盛钢桶"])
    # Which of the two it extends is unknown: it is added, and its name decides, as for any
    # type sharing a ref.
    types = merge_types(found, [later])
    assert types == [*found, later]
    proposals = build_proposals([LADLE_CHUNK], [], types, RelationsOut(relations=[], properties=[]))
    assert [p.fields["labelZh"] for p in proposals] == ["钢包", "行车"]
    assert [s["text"] for s in by_label(proposals, "钢包").fields["synonyms"]] == ["盛钢桶"]
    assert by_label(proposals, "行车").fields["synonyms"] == []


async def test_new_types_sharing_a_name_become_one_type() -> None:
    types = [
        entity("new:LadleFurnace", "LF精炼炉", "LadleFurnace", synonyms=["精炼炉"]),
        entity("new:Ladle", "钢包", "Ladle"),
        # Another name of the same furnace: merged, its names kept as synonyms.
        entity("new:Refiner", "精炼炉", "Refiner", synonyms=["LF炉"]),
        entity("new:Converter", "转炉", "Converter", label_en="Converter"),
        entity("new:BOF", "顶底复吹转炉", "BOF", label_en="converter"),
    ]
    rels = RelationsOut(
        relations=[
            relation("new:Ladle", "new:Refiner", "运至", [quote(0, "钢水由钢包吊运至精炼炉")])
        ],
        properties=[],
    )
    proposals, _ = await run(ScriptedGateway(outputs(types, rels)))

    created = [p for p in proposals if p.kind == "entity_type"]
    assert [p.fields["labelZh"] for p in created] == ["LF精炼炉", "钢包", "转炉"]
    furnace = by_label(proposals, "LF精炼炉")
    assert [s["text"] for s in furnace.fields["synonyms"]] == ["精炼炉", "LF炉"]
    assert [s["text"] for s in by_label(proposals, "转炉").fields["synonyms"]] == ["顶底复吹转炉"]
    [link] = [p for p in proposals if p.kind == "relation_type"]
    assert link.fields["rangeRef"] == "new:LadleFurnace"


def prop(domain: str, label: str) -> PropertyOut:
    return PropertyOut(
        label_zh=label,
        label_en=None,
        local_name="weight",
        domain=domain,
        datatype="decimal",
        unit="t",
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=0.8,
        rationale="r",
        quotes=[],
    )


LADLE_CHUNK = ChunkText(
    id=uuid4(),
    seq=0,
    text="钢水由钢包吊运至精炼炉。\n行车吊运钢包。\n行车把印有牌号的钢包吊运至精炼炉。\n天车停在精炼炉旁。",
)


@pytest.mark.parametrize(
    ("label", "name", "created"),
    [
        ("行车", "Crane", ["钢包", "行车", "精炼炉"]),  # a second new type
        ("牌号", "Grade", ["钢包", "精炼炉"]),  # an existing type, matched by its synonym
    ],
)
def test_types_sharing_a_ref_but_not_a_name_are_kept_and_the_ref_resolves_to_none(
    label: str, name: str, created: list[str]
) -> None:
    types = [
        entity("new:Ladle", "钢包", "Ladle"),
        entity("new:Ladle", label, name),
        entity("new:Furnace", "精炼炉", "Furnace", parent="new:Ladle"),
    ]
    # The line names both candidates and the furnace: only the shared ref can drop these.
    line = [quote(0, "行车把印有牌号的钢包吊运至精炼炉")]
    rels = RelationsOut(
        relations=[
            relation("new:Ladle", "new:Furnace", "运至", line),
            relation("new:Furnace", "new:Ladle", "接收", line),
        ],
        properties=[prop("new:Ladle", "容量")],
    )
    proposals = build_proposals([LADLE_CHUNK], [EXISTING_GRADE], types, rels)

    # Which of the two the model meant is unknown: whatever references the ref is dropped.
    assert [p.fields.get("labelZh") for p in proposals] == created
    assert by_label(proposals, "精炼炉").fields["parentRef"] is None


def test_types_sharing_a_ref_and_a_name_are_one_type_the_ref_resolves_to() -> None:
    types = [
        entity("new:Ladle", "钢包", "Ladle"),
        entity("new:Ladle", "钢包", "Ladle", synonyms=["盛钢桶"]),
        entity("new:Furnace", "精炼炉", "Furnace", parent="new:Ladle"),
        entity("new:Grade", "钢种", "Grade"),
        entity("new:Grade", "牌号", "Grade"),  # both names of the existing type
    ]
    rels = RelationsOut(
        relations=[
            relation("new:Ladle", "new:Furnace", "运至", [quote(0, "钢水由钢包吊运至精炼炉")]),
        ],
        properties=[prop("new:Ladle", "容量"), prop("new:Grade", "代号")],
    )
    proposals = build_proposals([LADLE_CHUNK], [EXISTING_GRADE], types, rels)

    assert [p.fields["labelZh"] for p in proposals if p.kind == "entity_type"] == ["钢包", "精炼炉"]
    assert [s["text"] for s in by_label(proposals, "钢包").fields["synonyms"]] == ["盛钢桶"]
    assert by_label(proposals, "精炼炉").fields["parentRef"] == "new:Ladle"
    [link] = [p for p in proposals if p.kind == "relation_type"]
    assert (link.fields["domainRef"], link.fields["rangeRef"]) == ("new:Ladle", "new:Furnace")
    assert by_label(proposals, "容量").fields["domainRef"] == "new:Ladle"
    assert by_label(proposals, "代号").fields["domainRef"] == str(EXISTING_GRADE.id)


def test_names_of_a_type_given_a_shared_ref_count_only_for_the_type_it_became() -> None:
    types = [
        entity("new:Crane", "行车", "Crane"),
        entity("new:Ladle", "钢包", "Ladle"),
        # Shares the ref of 钢包, but is named 行车: it is merged into the crane.
        entity("new:Ladle", "行车", "Crane2", synonyms=["天车"]),
        entity("new:Furnace", "精炼炉", "Furnace"),
    ]
    rels = RelationsOut(
        relations=[
            # The line names 钢包, not the crane: no direct evidence for the crane.
            relation("new:Crane", "new:Furnace", "运至", [quote(0, "钢水由钢包吊运至精炼炉")]),
            relation("new:Crane", "new:Crane", "吊运", [quote(0, "行车吊运钢包")]),
            # 天车 came with the type that shares the ref and was merged: it names the crane.
            relation("new:Crane", "new:Furnace", "停靠", [quote(0, "天车停在精炼炉旁")]),
        ],
        properties=[],
    )
    proposals = build_proposals([LADLE_CHUNK], [], types, rels)

    assert [p.fields["labelZh"] for p in proposals if p.kind == "entity_type"] == [
        "行车",
        "钢包",
        "精炼炉",
    ]
    assert [s["text"] for s in by_label(proposals, "行车").fields["synonyms"]] == ["天车"]
    [link] = [p for p in proposals if p.kind == "relation_type"]
    assert (link.fields["labelZh"], link.fields["domainRef"], link.fields["rangeRef"]) == (
        "停靠",
        "new:Crane",
        "new:Furnace",
    )


def test_an_existing_id_given_to_a_type_of_other_names_does_not_align_it() -> None:
    grade = str(EXISTING_GRADE.id)
    types = [
        entity(grade, "行车", "Crane", synonyms=["天车"], quotes=[quote(0, "行车吊运钢包")]),
        entity("new:Ladle", "钢包", "Ladle", parent=grade),
    ]
    rels = RelationsOut(
        relations=[relation(grade, "new:Ladle", "吊运", [quote(0, "行车吊运钢包")])],
        properties=[prop(grade, "起重量")],
    )
    proposals = build_proposals([LADLE_CHUNK], [EXISTING_GRADE], types, rels)

    # Not one name of 钢种: a new type, left to the reviewer; 钢种 gets no synonyms.
    assert [(p.op, p.fields.get("labelZh")) for p in proposals] == [
        ("create", "行车"),
        ("create", "钢包"),
        ("create", "吊运"),
        ("create", "起重量"),
    ]
    crane = by_label(proposals, "行车")
    assert crane.flags == ["possible_duplicate"]
    assert [s["text"] for s in crane.fields["synonyms"]] == ["天车"]
    # The relations stage listed the id with this type's names, so the id stands for it.
    assert by_label(proposals, "吊运").fields["domainRef"] == crane.temp_ref
    assert by_label(proposals, "起重量").fields["domainRef"] == crane.temp_ref
    # The types stage listed the id as 钢种, so a parent given it may mean either.
    assert by_label(proposals, "钢包").fields["parentRef"] is None


def test_an_existing_id_given_to_a_type_of_other_names_can_merge_by_name() -> None:
    grade = str(EXISTING_GRADE.id)
    types = [
        entity("new:Crane", "行车", "Crane", quotes=[quote(0, "行车吊运钢包")]),
        entity(grade, "行车", "Crane2", synonyms=["天车"]),
    ]
    proposals = build_proposals(
        [LADLE_CHUNK],
        [EXISTING_GRADE],
        types,
        RelationsOut(relations=[], properties=[prop(grade, "起重量")]),
    )

    # Merged into the new type of the same name, as any new type would be: no flag.
    assert [(p.op, p.fields.get("labelZh")) for p in proposals] == [
        ("create", "行车"),
        ("create", "起重量"),
    ]
    crane = by_label(proposals, "行车")
    assert crane.flags == []
    assert [s["text"] for s in crane.fields["synonyms"]] == ["天车"]
    assert by_label(proposals, "起重量").fields["domainRef"] == "new:Crane"


def test_a_later_batch_leaves_types_given_an_existing_id_to_be_checked_one_by_one() -> None:
    grade = str(EXISTING_GRADE.id)
    found = [entity(grade, "钢种", "Grade")]
    later = [
        entity(grade, "钢种", "Grade", synonyms=["钢级"]),
        entity(grade, "行车", "Crane", synonyms=["天车"]),
    ]
    types = merge_types(found, later)
    assert types == [*found, *later]

    proposals = build_proposals(
        [LADLE_CHUNK], [EXISTING_GRADE], types, RelationsOut(relations=[], properties=[])
    )
    # Those with a name of 钢种 make one update; 行车 is not folded into it.
    [update] = [p for p in proposals if p.op == "update"]
    assert [s["text"] for s in update.fields["synonyms"]] == ["钢级"]
    assert [p.fields["labelZh"] for p in proposals if p.op == "create"] == ["行车"]


def test_an_existing_id_given_to_another_existing_type_aligns_by_name() -> None:
    converter = KnownElement(id=uuid4(), kind="entity_type", local_name="BOF", label_zh="转炉")
    types = [entity(str(converter.id), "钢种", "Grade", synonyms=["钢级"])]
    proposals = build_proposals(
        [LADLE_CHUNK],
        [EXISTING_GRADE, converter],
        types,
        RelationsOut(relations=[], properties=[prop(str(converter.id), "代号")]),
    )

    [update, attribute] = proposals
    assert (update.op, update.target_element_id) == ("update", EXISTING_GRADE.id)
    assert [s["text"] for s in update.fields["synonyms"]] == ["钢级"]
    assert attribute.fields["domainRef"] == str(EXISTING_GRADE.id)


def test_an_existing_id_given_to_its_type_and_a_type_of_other_names_is_ambiguous() -> None:
    grade = str(EXISTING_GRADE.id)
    types = [
        entity(grade, "钢种", "Grade"),
        entity(grade, "行车", "Crane", quotes=[quote(0, "行车吊运钢包")]),
        entity("new:Ladle", "钢包", "Ladle"),
    ]
    # The line names 牌号, 行车 and 钢包: either reading has direct evidence.
    line = [quote(0, "行车把印有牌号的钢包吊运至精炼炉")]
    rels = RelationsOut(
        relations=[relation(grade, "new:Ladle", "吊运", line)],
        properties=[prop(grade, "起重量")],
    )
    proposals = build_proposals([LADLE_CHUNK], [EXISTING_GRADE], types, rels)

    assert [(p.op, p.fields.get("labelZh")) for p in proposals] == [
        ("create", "行车"),
        ("create", "钢包"),
    ]
    assert by_label(proposals, "行车").flags == ["possible_duplicate"]


async def test_relations_need_a_quote_whose_line_names_both_types() -> None:
    chunk = ChunkText(
        id=uuid4(),
        seq=0,
        text="每个炉次只冶炼一个钢种。\n钢水由钢包吊运至精炼炉。\n炉次按计划组织生产。",
    )
    types = [
        entity("new:Heat", "炉次", "Heat"),
        entity("new:Ladle", "盛钢桶", "Ladle", synonyms=["钢包"]),
        entity("new:Crane", "行车", "Crane"),
    ]
    grade = str(EXISTING_GRADE.id)
    rels = RelationsOut(
        relations=[
            relation("new:Heat", grade, "冶炼", [quote(0, "只冶炼一个钢种")]),
            # The line of the quote does not name the heat: no direct evidence.
            relation("new:Heat", "new:Ladle", "使用", [quote(0, "钢水由钢包吊运至精炼炉")]),
            relation("new:Heat", grade, "计划钢种", []),
            relation("new:Heat", grade, "虚构", [quote(0, "炉次与钢种一一对应")]),
            # 行车 is not named anywhere in the document: no direct evidence either.
            relation("new:Crane", "new:Ladle", "吊运", [quote(0, "由钢包吊运")]),
        ],
        properties=[],
    )
    gateway = ScriptedGateway(outputs(types, rels))
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    proposals = await extractor.run(
        document_id=DOC, title="t", chunks=[chunk], known=[EXISTING_GRADE], progress=progress
    )

    relations = [p for p in proposals if p.kind == "relation_type"]
    assert [r.fields["labelZh"] for r in relations] == ["冶炼"]
    assert relations[0].flags == []
    [relations_text] = [text for purpose, text in gateway.texts if purpose == "extract.relations"]
    assert "- new:Ladle | 盛钢桶 | 钢包 | \n" in relations_text


async def test_only_names_of_two_characters_or_more_and_labels_merge_types() -> None:
    types = [
        entity("new:Converter", "转炉", "Converter", synonyms=["炉"]),
        entity("new:Reheater", "加热炉", "Reheater", synonyms=["炉"]),  # one character: no
        entity("new:Furnace", "炉", "Furnace"),  # one character, even as a label: no
        entity("new:Refiner", "精炼炉", "Refiner", synonyms=["LF炉"]),
        entity("new:LF", "LF精炼炉", "LF", synonyms=["LF炉"]),  # synonym against synonym: no
        entity("new:Return", "回炉处理", "Return", quotes=[quote(0, "每个炉次只冶炼一个钢种")]),
        entity(
            "new:SlabReturn",
            "板坯回炉",
            "SlabReturn",
            synonyms=["回炉处理"],  # names the earlier type's label: the same concept
            quotes=[quote(1, "一个浇次由若干个炉次"), quote(1, "没有这句话")],
        ),
    ]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    assert [p.fields["labelZh"] for p in proposals] == [
        "转炉",
        "加热炉",
        "炉",
        "精炼炉",
        "LF精炼炉",
        "回炉处理",
    ]
    merged = by_label(proposals, "回炉处理")
    assert [s["text"] for s in merged.fields["synonyms"]] == ["板坯回炉"]
    # Located quotes of the merged term are kept as evidence; unlocated ones are not.
    assert [e.chunk_id for e in merged.evidence] == [CHUNK_A.id, CHUNK_B.id]
    assert merged.flags == []
    # Sharing only a synonym is left to the reviewer, marked as a possible duplicate.
    # (Types without quotes also carry evidence_not_found.)
    flagged = [p.fields["labelZh"] for p in proposals if "possible_duplicate" in p.flags]
    assert flagged == ["LF精炼炉"]


async def test_relation_evidence_uses_every_name_and_needs_two_separate_mentions() -> None:
    chunk = ChunkText(
        id=uuid4(),
        seq=0,
        text="铁水由铁水罐运入转炉。\n钢种成分要求见下表。\n相邻炉次的钢种相同。\n铁水由罐运入转炉。",
    )
    converter = KnownElement(
        id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉设备"
    )
    types = [
        # Matches the existing type by a synonym: its label 转炉 is checked too.
        entity("new:BOF", "转炉", "BOF", synonyms=["转炉设备"]),
        entity("new:Pot", "铁水罐", "Pot"),
        # Its short synonym 成分要求 lies inside 钢种成分要求 and is no separate mention either.
        entity("new:Requirement", "钢种成分要求", "Requirement", synonyms=["成分要求"]),
        entity("new:Heat", "炉次", "Heat"),
        entity("new:Tank", "罐", "Tank"),
    ]
    grade = str(EXISTING_GRADE.id)
    rels = RelationsOut(
        relations=[
            relation("new:Pot", "new:BOF", "运入", [quote(0, "铁水由铁水罐运入转炉")]),
            # 钢种 is only found inside 钢种成分要求: one mention, not two.
            relation(grade, "new:Requirement", "要求", [quote(0, "钢种成分要求见下表")]),
            relation("new:Heat", "new:Heat", "相邻", [quote(0, "相邻炉次的钢种相同")]),
            # A one-character name does not count as naming a type.
            relation("new:Tank", "new:BOF", "装运", [quote(0, "铁水由罐运入转炉")]),
        ],
        properties=[],
    )
    gateway = ScriptedGateway(outputs(types, rels))
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    proposals = await extractor.run(
        document_id=DOC,
        title="t",
        chunks=[chunk],
        known=[EXISTING_GRADE, converter],
        progress=progress,
    )

    [link] = [p for p in proposals if p.kind == "relation_type"]
    assert (link.fields["labelZh"], link.fields["rangeRef"]) == ("运入", str(converter.id))


# Lines of samples/steel/docs, verbatim, that state the nine core relations of the expected list.
STEEL_LINES = [
    "- **炉次**：转炉从装料到出钢完成的一次冶炼过程，以炉号唯一标识，炉号由年份、转炉编号和"
    "流水号组成，例如 2611-2-0457。",
    "- **钢种**：按化学成分和性能要求划分的钢的牌号，例如 Q235B。每个炉次只冶炼一个钢种。",
    "- **浇次**：连铸机从开浇到停浇的一次连续浇铸过程。一个浇次由若干个炉次的钢水连续浇铸而成，"
    "炉次在浇次内的顺序称为炉序。",
    "铸坯按轧制计划要求的定尺长度切割成板坯。每块板坯记录板坯号、所属炉次、厚度、宽度、长度"
    "（毫米）和理论重量（吨）。板坯规格一般为厚度 230 mm、宽度 1000～1650 mm、"  # noqa: RUF001 (verbatim)
    "长度 8000～11000 mm。",  # noqa: RUF001 (verbatim)
    "- **轧制事件**：一块板坯在热轧机组上的完整轧制过程，产出一个钢卷。",
    "钢卷必须能够追溯到来源板坯，板坯必须能够追溯到所属炉次和浇次。轧制过程的温度、厚度等"
    "过程数据按钢卷号保存，保存期不少于三年。",
    "每次取样检验形成一份检验结果，记录检验批号、试样编号、检验日期以及各项力学性能的实测值。"
    '检验结果判定为"合格"或"不合格"。',
    "钢卷在精整线上由表面检测仪和人工共同检查表面质量。发现的缺陷记录为缺陷记录，包括缺陷类型、"
    "所在钢卷的位置（距卷头长度，单位米）、严重等级（轻微、一般、严重）。",
    "质量判定须由质检员确认，判定结果关联到钢卷，并记录判定人和判定时间。",
]
# (domain, range, quote) of the nine core relations; the quote is part of one line above.
STEEL_CORE_RELATIONS = [
    ("new:Heat", "new:Grade", "每个炉次只冶炼一个钢种"),
    ("new:Heat", "new:Converter", "转炉从装料到出钢完成的一次冶炼过程"),
    ("new:Heat", "new:Cast", "一个浇次由若干个炉次的钢水连续浇铸而成"),
    ("new:Slab", "new:Heat", "每块板坯记录板坯号、所属炉次"),
    ("new:Rolling", "new:Slab", "一块板坯在热轧机组上的完整轧制过程"),
    ("new:Coil", "new:Slab", "钢卷必须能够追溯到来源板坯"),
    ("new:Result", "new:Lot", "每次取样检验形成一份检验结果，记录检验批号"),
    ("new:Defect", "new:Coil", "发现的缺陷记录为缺陷记录，包括缺陷类型、所在钢卷的位置"),
    ("new:Decision", "new:Coil", "判定结果关联到钢卷"),
]


def _steel_types(defect_label: str, defect_synonyms: list[str]) -> list[EntityTypeOut]:
    """The names the model gave these types in the final evaluation runs of #7."""
    return [
        entity("new:Heat", "炉次", "Heat", label_en="Heat"),
        entity("new:Grade", "钢种", "Grade", label_en="Steel grade"),
        entity("new:Converter", "转炉", "Converter", label_en="Converter"),
        entity("new:Cast", "浇次", "Cast", label_en="Casting sequence"),
        entity("new:Slab", "板坯", "Slab", label_en="Slab"),
        # Its synonym 表面缺陷 must not count as a mention inside 缺陷记录's lines.
        entity("new:SlabDefect", "板坯表面缺陷", "SlabDefect", label_en="Slab surface defect"),
        entity("new:Rolling", "轧制事件", "Rolling", label_en="Rolling event"),
        entity("new:Coil", "钢卷", "Coil", label_en="Steel coil", synonyms=["热轧钢卷"]),
        entity("new:Lot", "检验批", "Lot", label_en="Inspection lot"),
        entity("new:Result", "检验结果", "Result", label_en="Test result"),
        entity("new:Defect", defect_label, "Defect", synonyms=defect_synonyms),
        entity("new:Decision", "质量判定", "Decision", label_en="Quality disposition"),
    ]


@pytest.mark.parametrize(
    ("defect_label", "defect_synonyms"),
    [("缺陷记录", ["钢卷表面缺陷"]), ("表面缺陷", ["缺陷记录"])],  # the two final runs
)
def test_the_core_steel_relations_have_direct_evidence(
    defect_label: str, defect_synonyms: list[str]
) -> None:
    chunks = [ChunkText(id=uuid4(), seq=0, text="\n".join(STEEL_LINES))]
    rels = RelationsOut(
        relations=[
            relation(domain, range_, f"关系{index}", [quote(0, text)])
            for index, (domain, range_, text) in enumerate(STEEL_CORE_RELATIONS)
        ],
        properties=[],
    )
    proposals = build_proposals(chunks, [], _steel_types(defect_label, defect_synonyms), rels)

    kept = [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"]
    assert kept == [f"关系{index}" for index in range(len(STEEL_CORE_RELATIONS))]


def test_a_name_only_inside_a_longer_name_is_no_evidence() -> None:
    chunks = [
        ChunkText(
            id=uuid4(),
            seq=0,
            text="钢种成分要求见下表。\n钢种成分要求与钢种成分要求的检验方法见附录。",
        )
    ]
    types = [
        entity("new:Grade", "钢种", "Grade"),
        entity("new:Requirement", "钢种成分要求", "Requirement", synonyms=["成分要求"]),
    ]
    rels = RelationsOut(
        relations=[
            # Passed before the longest-mention rule: 钢种 and the short synonym 成分要求 sit
            # side by side inside the single mention 钢种成分要求.
            relation("new:Grade", "new:Requirement", "规定", [quote(0, "钢种成分要求见下表")]),
            # Passed before too: 钢种 inside the first 钢种成分要求 paired with the second one.
            relation(
                "new:Grade", "new:Requirement", "检验", [quote(0, "钢种成分要求与钢种成分要求")]
            ),
        ],
        properties=[],
    )
    proposals = build_proposals(chunks, [], types, rels)

    assert [p.kind for p in proposals] == ["entity_type", "entity_type"]


# Alignment with existing types by name (#33): the same names as the other rules.
CONVERTER = KnownElement(
    id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉", synonyms=("炉",)
)
NO_RELATIONS = RelationsOut(relations=[], properties=[])


def test_a_shared_one_character_synonym_does_not_align_a_type() -> None:
    types = [entity("new:ReheatingFurnace", "加热炉", "ReheatingFurnace", synonyms=["炉"])]
    [created] = build_proposals([LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS)

    assert (created.op, created.fields["labelZh"]) == ("create", "加热炉")
    assert "possible_duplicate" not in created.flags


def test_a_mistaken_id_and_a_shared_one_character_synonym_do_not_align_a_type() -> None:
    types = [entity(str(CONVERTER.id), "加热炉", "ReheatingFurnace", synonyms=["炉"])]
    [created] = build_proposals([LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS)

    assert (created.op, created.fields["labelZh"]) == ("create", "加热炉")
    assert "possible_duplicate" in created.flags


def test_an_existing_local_name_does_not_align_a_type() -> None:
    types = [entity("new:Furnace", "加热炉", "ReheatingFurnace", label_en="Converter")]
    [created] = build_proposals([LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS)

    assert (created.op, created.fields["labelZh"]) == ("create", "加热炉")


def test_a_one_character_label_aligns_only_with_the_same_label() -> None:
    steel = KnownElement(id=uuid4(), kind="entity_type", local_name="Steel", label_zh="钢")
    types = [
        entity("new:Steel", "钢", "Steel", synonyms=["钢材"]),
        entity("new:MoltenSteel", "钢水", "MoltenSteel", synonyms=["钢"]),
        entity("new:Furnace", "炉", "Furnace"),
    ]
    proposals = build_proposals([LADLE_CHUNK], [steel, CONVERTER], types, NO_RELATIONS)

    # 钢 is the whole name of both: one type. A one-character synonym aligns nothing, and a
    # one-character synonym of an existing type (炉 of 转炉) may mean it: a reviewer decides.
    assert [(p.op, p.fields.get("labelZh")) for p in proposals] == [
        ("update", None),
        ("create", "钢水"),
        ("create", "炉"),
    ]
    assert proposals[0].target_element_id == steel.id
    assert proposals[0].fields == {"synonyms": [{"lang": "zh", "text": "钢材"}]}
    assert "possible_duplicate" not in proposals[1].flags
    assert "possible_duplicate" in proposals[2].flags


def test_the_label_of_a_type_aligned_by_name_becomes_a_synonym() -> None:
    equipment = KnownElement(
        id=uuid4(), kind="entity_type", local_name="ConverterUnit", label_zh="转炉设备"
    )
    types = [entity("new:Converter", "转炉", "Converter", synonyms=["转炉设备"])]
    [update] = build_proposals([LADLE_CHUNK], [equipment], types, NO_RELATIONS)

    assert (update.op, update.target_element_id) == ("update", equipment.id)
    assert update.fields == {"synonyms": [{"lang": "zh", "text": "转炉"}]}


def test_the_label_of_a_type_aligned_by_its_id_becomes_a_synonym() -> None:
    types = [entity(str(EXISTING_GRADE.id), "钢号", "Grade", synonyms=["钢种"])]
    [update] = build_proposals([LADLE_CHUNK], [EXISTING_GRADE], types, NO_RELATIONS)

    assert (update.op, update.target_element_id) == ("update", EXISTING_GRADE.id)
    assert update.fields == {"synonyms": [{"lang": "zh", "text": "钢号"}]}


STEELMAKING_CONVERTER = KnownElement(
    id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉", synonyms=("炼钢炉",)
)


@pytest.mark.parametrize(
    "ref",
    ["new:ElectricFurnace", str(STEELMAKING_CONVERTER.id)],
    ids=["new-ref", "existing-id"],  # stable ids: the uuid differs per xdist worker
)
def test_a_shared_synonym_alone_does_not_align_a_type(ref: str) -> None:
    types = [entity(ref, "电炉", "ElectricFurnace", synonyms=["炼钢炉"])]
    [created] = build_proposals([LADLE_CHUNK], [STEELMAKING_CONVERTER], types, NO_RELATIONS)

    assert (created.op, created.fields["labelZh"]) == ("create", "电炉")
    # With the converter's id the flag also follows from the mistaken id.
    assert "possible_duplicate" in created.flags


def test_a_synonym_that_is_an_existing_label_aligns_a_type() -> None:
    types = [entity("new:Bof", "氧气转炉", "Bof", synonyms=["转炉"])]
    [update] = build_proposals([LADLE_CHUNK], [STEELMAKING_CONVERTER], types, NO_RELATIONS)

    assert (update.op, update.target_element_id) == ("update", STEELMAKING_CONVERTER.id)
    assert update.fields == {"synonyms": [{"lang": "zh", "text": "氧气转炉"}]}


def test_an_existing_id_given_to_a_type_of_its_one_character_label_is_kept() -> None:
    steel = KnownElement(id=uuid4(), kind="entity_type", local_name="Steel", label_zh="钢")
    types = [
        entity(str(steel.id), "钢", "Steel"),
        entity("new:Billet", "钢坯", "Billet", parent=str(steel.id)),
    ]
    [billet] = build_proposals([LADLE_CHUNK], [steel], types, NO_RELATIONS)

    # Not a mistaken id: the parent given it stands for 钢.
    assert billet.fields["parentRef"] == str(steel.id)
