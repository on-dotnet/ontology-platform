"""Staged extraction with a scripted model: alignment, references, evidence grounding, progress."""

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel

from ontology_platform.modules.ai.extraction import (
    TYPES_BATCH_TERMS,
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    Proposal,
    batches,
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
