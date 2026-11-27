"""Staged extraction with a scripted model: alignment, references, evidence grounding, progress."""

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai.extraction import (
    TYPES_BATCH_TERMS,
    ChunkText,
    Decision,
    ExtractionModels,
    Extractor,
    KnownElement,
    PendingType,
    Proposal,
    ProposedMatch,
    RunStats,
    _Builder,
    batches,
    build_proposals,
    merge_types,
    normalize,
    resolve_requests,
    sentence_ref,
    sentences_of,
)
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.prompts import (
    RECORD_RULE,
    RELATIONS_INSTRUCTIONS,
    RESOLVE_INSTRUCTIONS,
    TYPES_INSTRUCTIONS,
    DecisionOut,
    EntityTypeOut,
    PropertyOut,
    Quote,
    RelationOut,
    RelationsOut,
    ResolveOut,
    TermOut,
    TermsOut,
    TypesOut,
)
from ontology_platform.modules.ai.sentences import split_sentences
from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import ParsedPage
from ontology_platform.settings import Settings

DOC = uuid4()
CHUNK_A = ChunkText(id=uuid4(), seq=0, text="每个炉次只冶炼一个钢种。钢水由钢包吊运至精炼炉。")
CHUNK_B = ChunkText(
    id=uuid4(), seq=1, text="一个浇次由若干个炉次的钢水连续浇铸而成。出钢温度单位为℃。"
)
EXISTING_GRADE = KnownElement(
    id=uuid4(), kind="entity_type", local_name="SteelGrade", label_zh="钢种", synonyms=("牌号",)
)


def judge(
    verdicts: Mapping[str, tuple[str | None, str]] | None = None,
    default: str | None = "different",
) -> Callable[[str], ResolveOut]:
    """A scripted resolve call: answers by the labels it finds in the call's input.

    `verdicts` maps the label of a type to judge to (the label of its candidate, the verdict);
    other types get `default` with no candidate, or no answer at all when it is None.
    """

    def answer(text: str) -> ResolveOut:
        rows: list[DecisionOut] = []
        asked: list[tuple[str, str, dict[str, str]]] = []
        for line in text.splitlines():
            found = re.match(r"(\s*)([TC]\d+) \| ([^|]*) \|", line)
            if found is None:
                continue
            alias, label = found[2], found[3].strip()
            if alias.startswith("T"):
                asked.append((alias, label, {}))
            else:
                asked[-1][2][label] = alias
        for alias, label, candidates in asked:
            if verdicts and label in verdicts:
                candidate, verdict = verdicts[label]
                chosen = candidates[candidate] if candidate is not None else None
            elif default is not None:
                chosen, verdict = None, default
            else:
                continue
            rows.append(
                DecisionOut(type=alias, candidate=chosen, verdict=verdict, reason="理由")  # type: ignore[arg-type]
            )
        return ResolveOut(decisions=rows)

    return answer


def decide(
    types: Sequence[EntityTypeOut],
    known: Sequence[KnownElement],
    verdicts: Mapping[str, tuple[str | None, str]] | None = None,
    default: str | None = "different",
    pending: Sequence[PendingType] = (),
) -> dict[int, list[Decision]]:
    """The answers `judge` would give, as `build_proposals` takes them."""
    names = {str(e.id): e.label_zh for e in known} | {str(p.item_id): p.label_zh for p in pending}
    out: dict[int, list[Decision]] = {}
    for request in resolve_requests(known, types, pending=pending):
        label = types[request.index].label_zh
        if verdicts and label in verdicts:
            wanted, verdict = verdicts[label]
            key = next(
                (
                    c.key
                    for c in request.candidates
                    if (types[int(c.key[1])].label_zh if c.key[0] == "run" else names[c.key[1]])
                    == wanted
                ),
                None,
            )
            out[request.index] = [Decision(verdict, key, "理由")]  # type: ignore[arg-type]
        elif default is not None:
            out[request.index] = [Decision(default)]  # type: ignore[arg-type]
    return out


class ScriptedGateway:
    """Returns canned outputs per purpose and records what it was asked.

    A resolve call without canned outputs is answered by `resolver` (by default: every type
    is a different concept from its candidates).
    """

    def __init__(
        self,
        outputs: dict[str, list[BaseModel]],
        resolver: Callable[[str], ResolveOut] | None = None,
    ) -> None:
        self.outputs = {purpose: list(items) for purpose, items in outputs.items()}
        self.resolver = resolver or judge()
        self.calls: list[tuple[str, str]] = []
        self.efforts: list[tuple[str, str | None]] = []
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
        effort: str | None = None,
    ) -> T:
        self.calls.append((purpose, model))
        self.efforts.append((purpose, effort))
        self.texts.append((purpose, text))
        if purpose == "extract.resolve" and purpose not in self.outputs:
            answer = self.resolver(text)
            assert isinstance(answer, schema)
            return answer
        result = self.outputs[purpose].pop(0)
        assert isinstance(result, schema)
        return result

    async def ping(self) -> bool:
        return True


def cite(chunk: ChunkText, fragment: str) -> str:
    """The number a model would cite for the sentence of `chunk` that contains `fragment`."""
    return next(s.ref for s in sentences_of([chunk]) if normalize(fragment) in normalize(s.text))


def entity(ref: str, label: str, **extra: Any) -> EntityTypeOut:
    values: dict[str, Any] = {
        "ref": ref,
        "label_zh": label,
        "label_en": None,
        "definition_zh": None,
        "synonyms": [],
        "parent": None,
        "confidence": 0.9,
        "sentence": None,
    }
    values.update(extra)
    return EntityTypeOut(**values)


def relation(domain: str, range_: str, label: str, sentence: str | None) -> RelationOut:
    return RelationOut(
        label_zh=label,
        local_name="belongsTo",
        domain=domain,
        range=range_,
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=0.8,
        sentence=sentence,
    )


def outputs(types: list[EntityTypeOut], rels: RelationsOut) -> dict[str, list[BaseModel]]:
    term = TermOut(name="炉次", english=None, definition=None, category="entity", quotes=[])
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


async def test_new_types_get_temp_refs_and_the_cited_sentence_as_evidence() -> None:
    types = [entity("new:Heat", "炉次", sentence="0.1")]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    heat = by_label(proposals, "炉次")
    assert (heat.op, heat.kind, heat.temp_ref, heat.rationale) == (
        "create",
        "entity_type",
        "new:Heat",
        None,
    )
    assert heat.fields["localName"] == "Heat"
    assert heat.flags == []
    assert heat.confidence == 0.9
    [evidence] = heat.evidence
    assert evidence.chunk_id == CHUNK_A.id
    assert evidence.quote == "每个炉次只冶炼一个钢种。"
    assert CHUNK_A.text[evidence.char_start : evidence.char_end] == "每个炉次只冶炼一个钢种。"


@pytest.mark.parametrize("cited", ["0.9", "2.1", "第一句", None])
async def test_a_sentence_the_document_does_not_have_is_flagged_and_penalised(
    cited: str | None,
) -> None:
    types = [entity("new:Heat", "炉次", sentence=cited)]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    heat = by_label(proposals, "炉次")
    assert heat.flags == ["evidence_not_found"]
    assert heat.confidence == 0.45
    assert heat.evidence == []


async def test_a_cited_sentence_not_naming_the_type_gives_way_to_the_first_that_does() -> None:
    # 0.2 does not name 浇次; 1.1 is the first sentence that does (spec 004, 7.2).
    types = [entity("new:CastingSequence", "浇次", sentence="0.2")]
    gateway = ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    stats = RunStats()
    proposals = await extractor.run(
        document_id=DOC,
        title="t",
        chunks=[CHUNK_A, CHUNK_B],
        known=[],
        progress=progress,
        stats=stats,
    )
    cast = by_label(proposals, "浇次")
    assert cast.flags == []
    [evidence] = cast.evidence
    assert (evidence.chunk_id, evidence.quote) == (
        CHUNK_B.id,
        "一个浇次由若干个炉次的钢水连续浇铸而成。",
    )
    # The literal check counts what the model cited.
    assert stats.literal == {"entity_type": 1, "entity_type:ok": 0}


async def test_a_type_no_sentence_names_keeps_the_cited_one_and_is_flagged() -> None:
    types = [entity("new:Plan", "生产计划", sentence="0.2")]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    )

    plan = by_label(proposals, "生产计划")
    assert plan.flags == ["evidence_not_found"]
    assert plan.confidence == 0.45
    assert [e.quote for e in plan.evidence] == ["钢水由钢包吊运至精炼炉。"]


async def test_a_type_named_as_an_existing_synonym_is_judged_and_recorded_as_the_same() -> None:
    # Was `_shares_name` (#33): a label that is an existing type's synonym aligned it. Now the
    # pair is a candidate (0.9) and the model judges; "same" is a recorded, new item that the
    # merge plan puts into the existing type (spec 004, 4.3).
    types = [entity("new:Grade", "牌号", synonyms=["钢号"], sentence="0.1")]
    gateway = ScriptedGateway(
        outputs(types, RelationsOut(relations=[], properties=[])),
        judge({"牌号": ("钢种", "same")}),
    )
    proposals, _ = await run(gateway, [EXISTING_GRADE])

    [created] = proposals
    # No sentence of the text names 牌号: its evidence is flagged (spec 004, 7.2).
    assert (created.op, created.temp_ref, created.flags) == (
        "create",
        "new:Grade",
        ["evidence_not_found"],
    )
    assert created.match == ProposedMatch("same", element_id=EXISTING_GRADE.id, reason="理由")
    assert created.fields["synonyms"] == [{"lang": "zh", "text": "钢号"}]
    # One call, with the candidate's names.
    [(_, text)] = [entry for entry in gateway.texts if entry[0] == "extract.resolve"]
    assert "T1 | 牌号 | 钢号 |" in text
    assert "C1 | 钢种 | 牌号 |" in text


async def test_existing_type_without_news_produces_nothing() -> None:
    types = [entity(str(EXISTING_GRADE.id), "钢种", synonyms=["牌号"])]
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[]))), [EXISTING_GRADE]
    )
    assert proposals == []


async def test_relations_resolve_refs_and_drop_unknown_types() -> None:
    types = [
        entity("new:Heat", "炉次"),
        entity("new:CastingSequence", "浇次"),
    ]
    rels = RelationsOut(
        relations=[
            relation(
                "new:Heat",
                "new:CastingSequence",
                "属于浇次",
                "1.1",
            ),
            relation("new:Heat", str(EXISTING_GRADE.id), "冶炼钢种", "0.1"),
            relation("new:Heat", "new:Ghost", "幽灵关系", None),
            relation("new:Heat", "new:CastingSequence", "属于浇次", None),  # duplicate
        ],
        properties=[
            PropertyOut(
                label_zh="出钢温度",
                local_name="tapping temperature",  # not camelCase: replaced
                domain="new:Heat",
                datatype="decimal",
                unit="℃",
                required=True,
                multiple=False,
                definition_zh=None,
                confidence=0.7,
                sentence="1.2",
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
    assert prop.fields["labelEn"] is None  # nothing to split a non-camelCase name into
    assert (prop.fields["datatype"], prop.fields["unit"], prop.fields["required"]) == (
        "decimal",
        "℃",
        True,
    )


async def test_parents_resolve_and_duplicate_new_types_merge() -> None:
    types = [
        entity("new:Furnace", "炉子"),
        entity("new:LadleFurnace", "精炼炉", parent="new:Furnace"),
        entity("new:LF", "精炼炉"),  # same label: merged into the first
        entity("new:Self", "自引用", parent="new:Self"),
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
    child = entity("new:Q235B", "Q235B 钢", parent=str(EXISTING_GRADE.id))
    gateway = ScriptedGateway(outputs([child], RelationsOut(relations=[], properties=[])))
    proposals, _ = await run(gateway, known=[EXISTING_GRADE])

    assert by_label(proposals, "Q235B 钢").fields["parentRef"] == str(EXISTING_GRADE.id)


async def test_updates_of_one_existing_type_are_merged() -> None:
    # `_maybe_update` stays for types of the existing type's main name (G1).
    types = [
        entity(str(EXISTING_GRADE.id), "钢种", synonyms=["钢级"]),
        entity("new:Grade", "钢种", synonyms=["钢号", "钢级"]),
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
    child = entity("new:Heat", "炉次", parent=str(produced_by.id))
    rels = RelationsOut(
        relations=[relation(str(produced_by.id), str(EXISTING_GRADE.id), "包含", None)],
        properties=[],
    )
    gateway = ScriptedGateway(outputs([child], rels))
    proposals, _ = await run(gateway, known=[EXISTING_GRADE, produced_by])

    assert by_label(proposals, "炉次").fields["parentRef"] is None
    assert [p.kind for p in proposals] == ["entity_type"]


def term(
    name: str,
    category: Literal["entity", "attribute", "relation", "value", "other"] = "entity",
    definition: str | None = None,
    quotes: Sequence[Quote] = (),
    english: str | None = None,
) -> TermOut:
    return TermOut(
        name=name, english=english, definition=definition, category=category, quotes=list(quotes)
    )


def types_texts(gateway: ScriptedGateway) -> list[str]:
    return [text for purpose, text in gateway.texts if purpose == "extract.types"]


async def test_few_terms_are_typed_in_one_call_each_with_its_first_sentences() -> None:
    gateway = ScriptedGateway(
        {
            "extract.terms": [
                TermsOut(terms=[term("炉次", quotes=[Quote(chunk=0, text="每个炉次")])]),
                TermsOut(
                    terms=[term("浇次", "other", definition="连续浇铸的炉次"), term("铁水罐")]
                ),
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

    # Existing types go by short ids; a term the text does not contain has no sentence.
    assert types_texts(gateway) == [
        "Document: 规程\n\n"
        "Existing entity types (id | label | synonyms):\n"
        "- E1 | 钢种 | 牌号\n"
        "\n"
        "Candidate terms (category | name | english | definition | sentences):\n"
        # The sentence of its quote; without quotes, the sentences that contain the name.
        "- entity | 炉次 |  |  | [0.1] 每个炉次。\n"
        "- other | 浇次 |  | 连续浇铸的炉次 | [1.1] 一个浇次由若干个炉次的钢水连续浇铸而成。\n"
        "- entity | 铁水罐 |  |  | "
    ]


async def test_term_sentences_follow_the_located_quotes_else_the_name() -> None:
    first = ChunkText(
        id=uuid4(), seq=0, text="钢包在精炼炉等待。\n钢包吊运至连铸机。\n钢包返回转炉。\n钢包清理。"
    )
    second = ChunkText(id=uuid4(), seq=1, text="钢水由钢包盛装。\n行车吊运钢包。")
    ladle_quotes = [
        Quote(chunk=0, text="钢包吊运至连铸机"),
        Quote(chunk=0, text="钢水由钢包盛装"),  # names the wrong chunk: found in the other
        Quote(chunk=0, text="钢包返回转炉"),
        Quote(chunk=0, text="钢包清理"),  # a fourth sentence: at most three are shown
    ]
    gateway = ScriptedGateway(
        {
            "extract.terms": [
                TermsOut(
                    terms=[
                        term("钢包", english="Ladle", quotes=ladle_quotes[:2]),
                        # Its quote is not in the text: the sentences naming it stand in.
                        term("行车", quotes=[Quote(chunk=1, text="行车把钢包吊走")]),
                        # A repeated term adds its quotes to the first one's.
                        term("钢包", quotes=ladle_quotes[2:]),
                    ]
                )
            ],
            "extract.types": [TypesOut(entity_types=[])],
            "extract.relations": [RelationsOut(relations=[], properties=[])],
        }
    )
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    await extractor.run(
        document_id=DOC, title="t", chunks=[first, second], known=[], progress=progress
    )

    [text] = types_texts(gateway)
    assert text.endswith(
        "Candidate terms (category | name | english | definition | sentences):\n"
        "- entity | 钢包 | Ladle |  | "
        "[0.2] 钢包吊运至连铸机。; [1.1] 钢水由钢包盛装。; [0.3] 钢包返回转炉。\n"
        "- entity | 行车 |  |  | [1.2] 行车吊运钢包。"
    )


async def test_many_terms_are_typed_in_batches_that_see_earlier_types() -> None:
    names = [f"术语{index}" for index in range(TYPES_BATCH_TERMS + 10)]
    first = [
        entity("new:Heat", "炉次", synonyms=["炉"], sentence="0.1"),
        entity("new:Furnace", "炉子"),
    ]
    second = [
        # The second batch reuses a type of the first one and adds what it knows.
        entity(
            "new:Heat",
            "炉次",
            synonyms=["熔炼炉次"],
            definition_zh="一次冶炼",
            parent="new:Furnace",
            sentence="1.1",
        ),
        entity("new:Cast", "浇次"),
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
    # One sentence per type: the first batch's stays (spec 004, 7.2).
    assert [e.quote for e in heat.evidence] == ["每个炉次只冶炼一个钢种。"]


def test_a_single_batch_of_types_is_kept_as_the_model_returned_it() -> None:
    batch = [
        entity("new:Heat", "炉次"),
        entity("new:Heat", "炉次", synonyms=["炉"]),
        entity("new:LF", "精炼炉"),
        entity("new:LadleFurnace", "精炼炉"),
    ]
    assert merge_types([], batch) == batch


def test_a_later_batch_does_not_extend_a_ref_an_earlier_batch_gave_to_two_types() -> None:
    found = [entity("new:Ladle", "钢包"), entity("new:Ladle", "行车")]
    later = entity("new:Ladle", "钢包", synonyms=["盛钢桶"])
    # Which of the two it extends is unknown: it is added, and its name decides, as for any
    # type sharing a ref.
    types = merge_types(found, [later])
    assert types == [*found, later]
    proposals = build_proposals([LADLE_CHUNK], [], types, RelationsOut(relations=[], properties=[]))
    assert [p.fields["labelZh"] for p in proposals] == ["钢包", "行车"]
    assert [s["text"] for s in by_label(proposals, "钢包").fields["synonyms"]] == ["盛钢桶"]
    assert by_label(proposals, "行车").fields["synonyms"] == []


async def test_new_types_judged_the_same_are_recorded_for_the_merge() -> None:
    # Was the merge of new types by shared names (#7): now candidates the model judges. A new
    # type judged the same as an earlier one of this document stays an item with that record
    # (spec 004, 4.3), which the reviewer can overturn; the merge plan puts it into the other.
    types = [
        entity("new:LadleFurnace", "LF精炼炉", synonyms=["精炼炉"]),
        entity("new:Ladle", "钢包"),
        # Another name of the same furnace.
        entity("new:Refiner", "精炼炉", synonyms=["LF炉"]),
        entity("new:Converter", "转炉", label_en="Converter"),
        entity("new:BOF", "顶底复吹转炉", label_en="converter"),
    ]
    rels = RelationsOut(
        relations=[relation("new:Ladle", "new:Refiner", "运至", "0.2")],
        properties=[],
    )
    resolver = judge({"精炼炉": ("LF精炼炉", "same"), "顶底复吹转炉": ("转炉", "same")})
    proposals, _ = await run(ScriptedGateway(outputs(types, rels), resolver))

    created = [p for p in proposals if p.kind == "entity_type"]
    assert [p.fields["labelZh"] for p in created] == [
        "LF精炼炉",
        "钢包",
        "精炼炉",
        "转炉",
        "顶底复吹转炉",
    ]
    assert by_label(proposals, "精炼炉").match == ProposedMatch(
        "same", temp_ref="new:LadleFurnace", reason="理由"
    )
    assert by_label(proposals, "顶底复吹转炉").match == ProposedMatch(
        "same", temp_ref="new:Converter", reason="理由"
    )
    # The relation keeps the type it was given; the merge plan puts both into one element.
    [link] = [p for p in proposals if p.kind == "relation_type"]
    assert link.fields["rangeRef"] == "new:Refiner"


def prop(domain: str, label: str) -> PropertyOut:
    return PropertyOut(
        label_zh=label,
        local_name="weight",
        domain=domain,
        datatype="decimal",
        unit="t",
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=0.8,
        sentence=None,
    )


LADLE_CHUNK = ChunkText(
    id=uuid4(),
    seq=0,
    text="钢水由钢包吊运至精炼炉。\n行车吊运钢包。\n行车把印有牌号的钢包吊运至精炼炉。\n天车停在精炼炉旁。",
)


@pytest.mark.parametrize(
    ("label", "created"),
    [
        ("行车", ["钢包", "行车", "精炼炉"]),  # a second new type
        ("钢种", ["钢包", "精炼炉"]),  # an existing type, by its main name (G1)
    ],
)
def test_types_sharing_a_ref_but_not_a_name_are_kept_and_the_ref_resolves_to_none(
    label: str, created: list[str]
) -> None:
    types = [
        entity("new:Ladle", "钢包"),
        entity("new:Ladle", label),
        entity("new:Furnace", "精炼炉", parent="new:Ladle"),
    ]
    # The line names both candidates and the furnace: only the shared ref can drop these.
    line = "0.3"
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
        entity("new:Ladle", "钢包"),
        entity("new:Ladle", "钢包", synonyms=["盛钢桶"]),
        entity("new:Furnace", "精炼炉", parent="new:Ladle"),
        entity("new:Grade", "钢种"),
        entity("new:Grade", "钢种", synonyms=["牌号"]),  # both the existing type (G1)
    ]
    rels = RelationsOut(
        relations=[
            relation("new:Ladle", "new:Furnace", "运至", "0.1"),
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
        entity("new:Crane", "行车"),
        entity("new:Ladle", "钢包"),
        # Shares the ref of 钢包, but is named 行车: it is merged into the crane.
        entity("new:Ladle", "行车", synonyms=["天车"]),
        entity("new:Furnace", "精炼炉"),
    ]
    rels = RelationsOut(
        relations=[
            # The line names 钢包, not the crane: no direct evidence for the crane.
            relation("new:Crane", "new:Furnace", "运至", "0.1"),
            relation("new:Crane", "new:Crane", "吊运", "0.2"),
            # 天车 came with the type that shares the ref and was merged: it names the crane.
            relation("new:Crane", "new:Furnace", "停靠", "0.4"),
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
        entity(grade, "行车", synonyms=["天车"], sentence="0.2"),
        entity("new:Ladle", "钢包", parent=grade),
    ]
    rels = RelationsOut(
        relations=[relation(grade, "new:Ladle", "吊运", "0.2")],
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
        entity("new:Crane", "行车", sentence="0.2"),
        entity(grade, "行车", synonyms=["天车"]),
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
    found = [entity(grade, "钢种")]
    later = [
        entity(grade, "钢种", synonyms=["钢级"]),
        entity(grade, "行车", synonyms=["天车"]),
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
    types = [entity(str(converter.id), "钢种", synonyms=["钢级"])]
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
        entity(grade, "钢种"),
        entity(grade, "行车", sentence="0.2"),
        entity("new:Ladle", "钢包"),
    ]
    # The line names 牌号, 行车 and 钢包: either reading has direct evidence.
    line = "0.3"
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
        entity("new:Heat", "炉次"),
        entity("new:Ladle", "盛钢桶", synonyms=["钢包"]),
        entity("new:Crane", "行车"),
    ]
    grade = str(EXISTING_GRADE.id)
    rels = RelationsOut(
        relations=[
            relation("new:Heat", grade, "冶炼", "0.1"),
            # The line of the quote does not name the heat: no direct evidence.
            relation("new:Heat", "new:Ladle", "使用", "0.2"),
            relation("new:Heat", grade, "计划钢种", None),
            relation("new:Heat", grade, "虚构", "0.9"),
            # 行车 is not named anywhere in the document: no direct evidence either.
            relation("new:Crane", "new:Ladle", "吊运", "0.2"),
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


async def test_one_character_matches_are_at_most_possible_duplicates() -> None:
    # Was MIN_NAME and the merge of new types by name (#7, #33): one-character names neither
    # merged nor flagged. Now every pair the shortlist finds is judged; one found only through
    # a one-character name is at most a possible duplicate (G4).
    types = [
        entity("new:Converter", "转炉", synonyms=["炉"]),
        entity("new:Reheater", "加热炉", synonyms=["炉"]),  # judged same: G4
        entity("new:Furnace", "炉"),  # judged same: G4
        entity("new:Refiner", "精炼炉", synonyms=["LF炉"]),
        entity("new:LF", "LF精炼炉", synonyms=["LF炉"]),  # judged unsure
        entity("new:Return", "回炉处理", sentence="0.1"),
        entity(
            "new:SlabReturn",
            "回炉处理",
            synonyms=["板坯回炉"],  # the main name of the earlier type (G1): joins it
            sentence="1.1",
        ),
    ]
    resolver = judge(
        {
            "加热炉": ("转炉", "same"),
            "炉": ("转炉", "same"),
            "LF精炼炉": ("精炼炉", "unsure"),
        }
    )
    proposals, _ = await run(
        ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])), resolver)
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
    # No sentence names 回炉处理: the cited one stays, flagged, and the joining type adds none.
    assert [e.chunk_id for e in merged.evidence] == [CHUNK_A.id]
    assert merged.flags == ["evidence_not_found"]
    flagged = [p.fields["labelZh"] for p in proposals if "possible_duplicate" in p.flags]
    assert flagged == ["加热炉", "炉", "LF精炼炉"]
    converter = by_label(proposals, "转炉").temp_ref
    assert [by_label(proposals, label).match for label in ("加热炉", "炉")] == [
        ProposedMatch("possible", temp_ref=converter, reason="理由")
    ] * 2


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
        # Judged the same as the existing type: its names and the type's own are checked.
        entity("new:BOF", "转炉", synonyms=["转炉设备"]),
        entity("new:Pot", "铁水罐"),
        # Its short synonym 成分要求 lies inside 钢种成分要求 and is no separate mention either.
        entity("new:Requirement", "钢种成分要求", synonyms=["成分要求"]),
        entity("new:Heat", "炉次"),
        entity("new:Tank", "罐"),
    ]
    grade = str(EXISTING_GRADE.id)
    rels = RelationsOut(
        relations=[
            relation("new:Pot", "new:BOF", "运入", "0.1"),
            # 钢种 is only found inside 钢种成分要求: one mention, not two.
            relation(grade, "new:Requirement", "要求", "0.2"),
            relation("new:Heat", "new:Heat", "相邻", "0.3"),
            # A one-character name does not count as naming a type.
            relation("new:Tank", "new:BOF", "装运", "0.4"),
        ],
        properties=[],
    )
    gateway = ScriptedGateway(outputs(types, rels), judge({"转炉": ("转炉设备", "same")}))
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
    # The merge plan puts new:BOF into the existing type (spec 004, 5.3).
    assert (link.fields["labelZh"], link.fields["rangeRef"]) == ("运入", "new:BOF")


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
        entity("new:Heat", "炉次", label_en="Heat"),
        entity("new:Grade", "钢种", label_en="Steel grade"),
        entity("new:Converter", "转炉", label_en="Converter"),
        entity("new:Cast", "浇次", label_en="Casting sequence"),
        entity("new:Slab", "板坯", label_en="Slab"),
        # Its synonym 表面缺陷 must not count as a mention inside 缺陷记录's lines.
        entity("new:SlabDefect", "板坯表面缺陷", label_en="Slab surface defect"),
        entity("new:Rolling", "轧制事件", label_en="Rolling event"),
        entity("new:Coil", "钢卷", label_en="Steel coil", synonyms=["热轧钢卷"]),
        entity("new:Lot", "检验批", label_en="Inspection lot"),
        entity("new:Result", "检验结果", label_en="Test result"),
        entity("new:Defect", defect_label, synonyms=defect_synonyms),
        entity("new:Decision", "质量判定", label_en="Quality disposition"),
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
            relation(domain, range_, f"关系{index}", cite(chunks[0], text))
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
        entity("new:Grade", "钢种"),
        entity("new:Requirement", "钢种成分要求", synonyms=["成分要求"]),
    ]
    rels = RelationsOut(
        relations=[
            # Passed before the longest-mention rule: 钢种 and the short synonym 成分要求 sit
            # side by side inside the single mention 钢种成分要求.
            relation("new:Grade", "new:Requirement", "规定", "0.1"),
            # Passed before too: 钢种 inside the first 钢种成分要求 paired with the second one.
            relation("new:Grade", "new:Requirement", "检验", "0.2"),
        ],
        properties=[],
    )
    proposals = build_proposals(chunks, [], types, rels)

    assert [p.kind for p in proposals] == ["entity_type", "entity_type"]


# Alignment with existing types (#33 and #31), now candidates, judgements and guardrails
# (spec 004, 4.3 and 4.4).
CONVERTER = KnownElement(
    id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉", synonyms=("炉",)
)
NO_RELATIONS = RelationsOut(relations=[], properties=[])


@pytest.mark.parametrize(
    ("verdict", "flagged"), [("different", False), ("same", True), (None, True)]
)
def test_a_shared_one_character_synonym_is_at_most_a_possible_duplicate(
    verdict: str | None, flagged: bool
) -> None:
    # Was `_shares_synonym` (#33). 炉 is the only name shared: judged different, nothing; judged
    # the same, still only a possible duplicate (G4); not judged at all, one too (G5).
    types = [entity("new:ReheatingFurnace", "加热炉", synonyms=["炉"])]
    verdicts = {"加热炉": ("转炉", verdict)} if verdict else None
    decisions = decide(types, [CONVERTER], verdicts, default=None)
    [created] = build_proposals(
        [LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS, decisions=decisions
    )

    assert (created.op, created.fields["labelZh"]) == ("create", "加热炉")
    assert ("possible_duplicate" in created.flags) is flagged
    assert (created.match is not None) is flagged


def test_a_mistaken_id_and_a_shared_one_character_synonym_do_not_align_a_type() -> None:
    # `mistaken_id` (#31), now G3 and G4: without a judgement (G5) or judged the same, the type
    # is a possible duplicate of the converter.
    types = [entity(str(CONVERTER.id), "加热炉", synonyms=["炉"])]
    for decisions in (None, decide(types, [CONVERTER], {"加热炉": ("转炉", "same")})):
        [created] = build_proposals(
            [LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS, decisions=decisions
        )
        assert (created.op, created.fields["labelZh"]) == ("create", "加热炉")
        assert "possible_duplicate" in created.flags
        assert created.match is not None
        assert created.match.element_id == CONVERTER.id


def test_a_nominated_type_is_at_most_a_possible_duplicate() -> None:
    # G3: the types stage gave 行车 the id of 钢种, whose names it does not share at all.
    types = [entity(str(EXISTING_GRADE.id), "行车")]
    [request] = resolve_requests([EXISTING_GRADE], types)
    assert [(c.key, c.nominated) for c in request.candidates] == [
        (("element", str(EXISTING_GRADE.id)), True)
    ]
    decisions = decide(types, [EXISTING_GRADE], {"行车": ("钢种", "same")})
    [created] = build_proposals(
        [LADLE_CHUNK], [EXISTING_GRADE], types, NO_RELATIONS, decisions=decisions
    )
    assert created.match == ProposedMatch("possible", element_id=EXISTING_GRADE.id, reason="理由")
    assert created.flags == ["possible_duplicate", "evidence_not_found"]


def test_an_existing_local_name_does_not_align_a_type() -> None:
    types = [entity("new:Furnace", "加热炉", label_en="Converter")]
    [created] = build_proposals([LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS)

    # Local names take no part in the shortlist: no candidate, nothing to judge.
    assert resolve_requests([CONVERTER], types) == []
    assert (created.op, created.fields["labelZh"], created.match) == ("create", "加热炉", None)


def test_a_one_character_label_aligns_only_with_the_same_label() -> None:
    steel = KnownElement(id=uuid4(), kind="entity_type", local_name="Steel", label_zh="钢")
    types = [
        entity("new:Steel", "钢", synonyms=["钢材"]),
        entity("new:MoltenSteel", "钢水", synonyms=["钢"]),
        entity("new:Furnace", "炉"),
    ]
    decisions = decide(types, [steel, CONVERTER], {"炉": ("转炉", "unsure")})
    proposals = build_proposals(
        [LADLE_CHUNK], [steel, CONVERTER], types, NO_RELATIONS, decisions=decisions
    )

    # 钢 is the whole main name of both: one type, without asking (G1, any length). The other
    # pairs are judged: 钢水 is a different concept, 炉 may be 转炉.
    assert [(p.op, p.fields.get("labelZh")) for p in proposals] == [
        ("update", None),
        ("create", "钢水"),
        ("create", "炉"),
    ]
    assert proposals[0].target_element_id == steel.id
    assert proposals[0].fields == {"synonyms": [{"lang": "zh", "text": "钢材"}]}
    assert "possible_duplicate" not in proposals[1].flags
    assert "possible_duplicate" in proposals[2].flags


def test_a_type_whose_synonym_is_an_existing_label_is_judged() -> None:
    # Was `_shares_name` (#33): a synonym that is an existing label aligned the type.
    equipment = KnownElement(
        id=uuid4(), kind="entity_type", local_name="ConverterUnit", label_zh="转炉设备"
    )
    types = [entity("new:Converter", "转炉", synonyms=["转炉设备"])]
    for verdict, match in (
        ("same", ProposedMatch("same", element_id=equipment.id, reason="理由")),
        ("different", None),
    ):
        decisions = decide(types, [equipment], {"转炉": ("转炉设备", verdict)})
        [created] = build_proposals(
            [LADLE_CHUNK], [equipment], types, NO_RELATIONS, decisions=decisions
        )
        assert (created.op, created.match) == ("create", match)


def test_an_existing_id_given_to_a_type_of_another_main_name_is_judged() -> None:
    # Was alignment by id plus a shared name (#31, #33). 钢号 has 钢种 as a synonym: a candidate
    # by name, so it is judged as any other (G3 does not cap it).
    types = [entity(str(EXISTING_GRADE.id), "钢号", synonyms=["钢种"])]
    decisions = decide(types, [EXISTING_GRADE], {"钢号": ("钢种", "same")})
    [created] = build_proposals(
        [LADLE_CHUNK], [EXISTING_GRADE], types, NO_RELATIONS, decisions=decisions
    )

    assert (created.op, created.fields["labelZh"]) == ("create", "钢号")
    assert created.match == ProposedMatch("same", element_id=EXISTING_GRADE.id, reason="理由")
    assert "possible_duplicate" not in created.flags


STEELMAKING_CONVERTER = KnownElement(
    id=uuid4(), kind="entity_type", local_name="Converter", label_zh="转炉", synonyms=("炼钢炉",)
)


@pytest.mark.parametrize(
    "ref",
    ["new:ElectricFurnace", str(STEELMAKING_CONVERTER.id)],
    ids=["new-ref", "existing-id"],  # stable ids: the uuid differs per xdist worker
)
def test_a_shared_synonym_alone_leaves_the_judgement_to_the_model(ref: str) -> None:
    # Was `_shares_synonym` (#33): a shared synonym (炼钢炉) flagged the type. Now it is a
    # candidate (0.8): judged different, nothing is flagged; without a judgement, it is (G5).
    types = [entity(ref, "电炉", synonyms=["炼钢炉"])]
    for decisions, flagged in (
        (decide(types, [STEELMAKING_CONVERTER], {"电炉": ("转炉", "different")}), False),
        (None, True),
    ):
        [created] = build_proposals(
            [LADLE_CHUNK], [STEELMAKING_CONVERTER], types, NO_RELATIONS, decisions=decisions
        )
        assert (created.op, created.fields["labelZh"]) == ("create", "电炉")
        assert ("possible_duplicate" in created.flags) is flagged


def test_a_synonym_that_is_an_existing_label_is_judged_the_same() -> None:
    types = [entity("new:Bof", "氧气转炉", synonyms=["转炉"])]
    decisions = decide(types, [STEELMAKING_CONVERTER], {"氧气转炉": ("转炉", "same")})
    [created] = build_proposals(
        [LADLE_CHUNK], [STEELMAKING_CONVERTER], types, NO_RELATIONS, decisions=decisions
    )

    assert created.op == "create"
    assert created.match == ProposedMatch(
        "same", element_id=STEELMAKING_CONVERTER.id, reason="理由"
    )


def test_an_existing_id_given_to_a_type_of_its_one_character_label_is_kept() -> None:
    steel = KnownElement(id=uuid4(), kind="entity_type", local_name="Steel", label_zh="钢")
    types = [
        entity(str(steel.id), "钢"),
        entity("new:Billet", "钢坯", parent=str(steel.id)),
    ]
    [billet] = build_proposals([LADLE_CHUNK], [steel], types, NO_RELATIONS)

    # Not a mistaken id: the parent given it stands for 钢.
    assert billet.fields["parentRef"] == str(steel.id)


# ---------- direct evidence by sentence (spec 004, section 8) ----------


def named_relation(item: RelationOut, local_name: str) -> RelationOut:
    return item.model_copy(update={"local_name": local_name})


def _wrap(line: str, width: int) -> str:
    """Breaks a line where a page of `width` display columns would (full-width counts twice)."""
    rows, row, used = [], "", 0
    for char in line:
        size = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if row and used + size > width:
            rows.append(row)
            row, used = "", 0
        row += char
        used += size
    return "\n".join([*rows, row])


@pytest.mark.parametrize("width", [30, 36, 50])
def test_the_core_steel_relations_survive_hard_wrapped_lines(width: int) -> None:
    text = "\n".join(_wrap(line, width) for line in STEEL_LINES)
    chunks = [ChunkText(id=uuid4(), seq=0, text=text)]
    rels = RelationsOut(
        relations=[
            relation(domain, range_, f"关系{index}", cite(chunks[0], text))
            for index, (domain, range_, text) in enumerate(STEEL_CORE_RELATIONS)
        ],
        properties=[],
    )
    proposals = build_proposals(chunks, [], _steel_types("缺陷记录", ["钢卷表面缺陷"]), rels)

    kept = [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"]
    assert kept == [f"关系{index}" for index in range(len(STEEL_CORE_RELATIONS))]


def test_two_sentences_of_one_line_are_no_direct_evidence() -> None:
    # A Markdown or Word line is a paragraph: its sentences are units of their own.
    chunk = ChunkText(id=uuid4(), seq=0, text="每个炉次在转炉冶炼。钢水随后装入钢包，运往精炼炉。")
    types = [
        entity("new:Heat", "炉次"),
        entity("new:Ladle", "钢包"),
        entity("new:Refiner", "精炼炉"),
    ]
    rels = RelationsOut(
        relations=[
            relation("new:Heat", "new:Ladle", "使用", "0.2"),
            relation("new:Ladle", "new:Refiner", "运往", "0.2"),
        ],
        properties=[],
    )
    proposals = build_proposals([chunk], [], types, rels)

    assert [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"] == ["运往"]


# ---------- relations: the range is part of what makes one existing ----------


def test_a_relation_with_an_existing_label_domain_and_range_is_not_proposed_again() -> None:
    heat = KnownElement(id=uuid4(), kind="entity_type", local_name="Heat", label_zh="炉次")
    grade = KnownElement(id=uuid4(), kind="entity_type", local_name="Grade", label_zh="钢种")
    smelts = KnownElement(
        id=uuid4(),
        kind="relation_type",
        local_name="smelts",
        label_zh="冶炼",
        domain_id=heat.id,
        range_id=grade.id,
    )
    rels = RelationsOut(
        relations=[relation(str(heat.id), str(grade.id), "冶炼", "0.1")],
        properties=[],
    )
    assert build_proposals([CHUNK_A], [heat, grade, smelts], [], rels) == []


# ---------- deleted types (spec 004, section 5.6) ----------

DELETED_CONVERTER = KnownElement(
    id=uuid4(),
    kind="entity_type",
    local_name="Converter",
    label_zh="转炉",
    synonyms=("氧气转炉",),
    revision=3,
)
CONVERTER_CHUNK = ChunkText(id=uuid4(), seq=0, text="每个炉次都在一座转炉上冶炼。")


def test_a_type_named_as_a_deleted_one_restores_it() -> None:
    types = [
        entity(
            "new:BOF",
            "转炉",
            definition_zh="把铁水炼成钢水的炉子",
            synonyms=["炼钢转炉", "氧气转炉"],
            sentence="0.1",
        ),
        entity("new:Heat", "炉次", sentence="0.1"),
    ]
    rels = RelationsOut(
        relations=[relation("new:Heat", "new:BOF", "冶炼于", "0.1")],
        properties=[prop("new:BOF", "公称容量")],
    )
    proposals = build_proposals([CONVERTER_CHUNK], [], types, rels, deleted=[DELETED_CONVERTER])

    [restore] = [p for p in proposals if p.op == "restore"]
    assert (restore.kind, restore.target_element_id, restore.target_revision) == (
        "entity_type",
        DELETED_CONVERTER.id,
        3,
    )
    # Only additions: the new synonym, and the definition the deleted type did not have.
    assert restore.fields == {
        "synonyms": [{"lang": "zh", "text": "炼钢转炉"}],
        "definitionZh": "把铁水炼成钢水的炉子",
    }
    assert [e.chunk_id for e in restore.evidence] == [CONVERTER_CHUNK.id]
    [smelted_in] = [p for p in proposals if p.kind == "relation_type"]
    [capacity] = [p for p in proposals if p.kind == "property"]
    converter = str(DELETED_CONVERTER.id)
    assert (smelted_in.fields["rangeRef"], capacity.fields["domainRef"]) == (converter, converter)
    assert [p.fields["labelZh"] for p in proposals if p.op == "create"] == [
        "炉次",
        "冶炼于",
        "公称容量",
    ]


def test_a_restore_is_proposed_even_with_nothing_to_add() -> None:
    types = [entity("new:Converter", "转炉", sentence="0.1")]
    proposals = build_proposals(
        [CONVERTER_CHUNK], [], types, NO_RELATIONS, deleted=[DELETED_CONVERTER]
    )
    assert [(p.op, p.fields) for p in proposals] == [("restore", {})]


def test_two_types_named_as_one_deleted_type_give_one_restore() -> None:
    types = [
        entity("new:Converter", "转炉", synonyms=["炼钢炉"]),
        entity("new:BOF", "转炉", synonyms=["顶吹转炉"]),
    ]
    proposals = build_proposals(
        [CONVERTER_CHUNK], [], types, NO_RELATIONS, deleted=[DELETED_CONVERTER]
    )
    [restore] = proposals
    assert [s["text"] for s in restore.fields["synonyms"]] == ["炼钢炉", "顶吹转炉"]


def test_an_active_type_of_the_name_wins_over_a_deleted_one() -> None:
    active = KnownElement(id=uuid4(), kind="entity_type", local_name="Converter2", label_zh="转炉")
    types = [entity("new:Converter", "转炉", synonyms=["炼钢炉"])]
    proposals = build_proposals(
        [CONVERTER_CHUNK], [active], types, NO_RELATIONS, deleted=[DELETED_CONVERTER]
    )
    assert [(p.op, p.target_element_id) for p in proposals] == [("update", active.id)]


def test_deleted_elements_hold_their_local_names_and_do_not_align_otherwise() -> None:
    deleted_relation = KnownElement(
        id=uuid4(), kind="relation_type", local_name="smeltedIn", label_zh="冶炼于"
    )
    types = [
        # Another name: a new type, which may not take the deleted type's local name.
        entity("new:Converter", "电炉"),
        entity("new:Heat", "炉次"),
    ]
    rels = RelationsOut(
        relations=[
            named_relation(
                relation("new:Heat", "new:Converter", "冶炼于", "0.1"),
                "smeltedIn",
            )
        ],
        properties=[],
    )
    chunk = ChunkText(id=uuid4(), seq=0, text="每个炉次都在一座电炉上冶炼。")
    proposals = build_proposals(
        [chunk], [], types, rels, deleted=[DELETED_CONVERTER, deleted_relation]
    )
    assert [(p.op, p.fields["localName"]) for p in proposals] == [
        ("create", "Converter2"),
        ("create", "Heat"),
        ("create", "smeltedIn2"),
    ]


async def test_stages_use_the_configured_efforts() -> None:
    # 牌号 is a synonym of the existing 钢种: a candidate, so there is a resolve call too.
    types = [entity("new:Grade", "牌号")]
    gateway = ScriptedGateway(outputs(types, RelationsOut(relations=[], properties=[])))
    extractor = Extractor(
        gateway,
        ExtractionModels(
            standard="std", reasoning="deep", standard_effort="low", reasoning_effort=None
        ),
    )

    async def progress(step: str, done: int, total: int) -> None:
        pass

    await extractor.run(
        document_id=DOC, title="t", chunks=[CHUNK_A], known=[EXISTING_GRADE], progress=progress
    )
    assert gateway.efforts == [
        ("extract.terms", None),  # kept as it was before (spec 004, 7.2)
        ("extract.types", None),
        ("extract.resolve", "low"),
        ("extract.relations", "low"),
    ]


def test_extraction_models_take_the_efforts_from_the_settings() -> None:
    settings = Settings(ai_effort="medium", ai_reasoning_effort="default")
    models = ExtractionModels.of(settings)
    assert (models.standard_effort, models.reasoning_effort) == ("medium", None)


def test_a_type_joining_another_of_its_main_name_adds_its_evidence() -> None:
    types = [
        entity("new:Heat", "炉次", sentence="0.1"),
        entity("new:Melt", "炉次", synonyms=["熔次"], sentence="1.1"),
    ]
    proposals = build_proposals(
        [CHUNK_A, CHUNK_B], [], types, RelationsOut(relations=[], properties=[])
    )

    [heat] = proposals
    assert [s["text"] for s in heat.fields["synonyms"]] == ["熔次"]
    assert [e.chunk_id for e in heat.evidence] == [CHUNK_A.id, CHUNK_B.id]


def test_properties_cite_a_sentence_that_names_them_preferring_one_naming_their_type() -> None:
    chunk = ChunkText(
        id=uuid4(), seq=0, text="钢包记录编号。\n炉次的编号由系统生成。\n炉次在转炉冶炼。"
    )
    types = [entity("new:Heat", "炉次"), entity("new:Ladle", "钢包")]
    numbered = prop("new:Heat", "编号").model_copy(update={"local_name": "heatNo"})
    rels = RelationsOut(
        relations=[],
        properties=[
            # Cites a sentence without the name: the first one naming it and 炉次 is taken.
            numbered.model_copy(update={"sentence": "0.3"}),
            # Named where cited.
            prop("new:Ladle", "编号").model_copy(update={"sentence": "0.1"}),
            # Nobody writes 重量: the cited sentence stays, and the property is flagged.
            prop("new:Ladle", "重量").model_copy(update={"sentence": "0.1"}),
        ],
    )
    literal: Counter[str] = Counter()
    proposals = build_proposals([chunk], [], types, rels, literal=literal)

    props = [p for p in proposals if p.kind == "property"]
    assert [(p.fields["domainRef"], p.evidence[0].quote, p.flags) for p in props] == [
        ("new:Heat", "炉次的编号由系统生成。", []),
        ("new:Ladle", "钢包记录编号。", []),
        ("new:Ladle", "钢包记录编号。", ["evidence_not_found"]),
    ]
    assert props[0].fields["labelEn"] == "heat no"
    assert (literal["property"], literal["property:ok"]) == (3, 1)


def test_relations_take_short_ids_and_only_the_cited_sentence_counts() -> None:
    chunk = ChunkText(id=uuid4(), seq=0, text="钢水由钢包吊运至精炼炉。\n每个炉次只冶炼一个钢种。")
    rels = RelationsOut(
        relations=[
            relation("new:Heat", str(EXISTING_GRADE.id), "冶炼", "0.2"),
            # Names both types, but in another sentence than cited: dropped.
            relation("new:Heat", str(EXISTING_GRADE.id), "生产", "0.1"),
        ],
        properties=[],
    )
    literal: Counter[str] = Counter()
    proposals = build_proposals(
        [chunk],
        [EXISTING_GRADE],
        [entity("new:Heat", "炉次", sentence="0.2")],
        rels,
        literal=literal,
    )
    [smelts] = [p for p in proposals if p.kind == "relation_type"]
    assert (smelts.fields["labelZh"], smelts.fields["labelEn"]) == ("冶炼", "belongs to")
    assert smelts.evidence[0].quote == "每个炉次只冶炼一个钢种。"
    assert (literal["relation_type"], literal["relation_type:ok"]) == (2, 1)


def test_a_relation_can_cite_a_short_run_of_sentences_of_one_chunk() -> None:
    # An introducing sentence and its list items name the two ends only together (#58).
    listed = "炉次的去向有两种：\n- 回炉；\n- 送往钢种调整工位。"
    chunk = ChunkText(id=uuid4(), seq=0, text=listed + "\n炉次按计划组织生产。")
    other = ChunkText(id=uuid4(), seq=1, text="钢种见下表。")
    rels = RelationsOut(
        relations=[
            relation("new:Heat", str(EXISTING_GRADE.id), "调整", "0.1-0.3"),
            # More than three units, across chunks, backwards, or naming one end only: dropped.
            relation("new:Heat", str(EXISTING_GRADE.id), "过长", "[0.1-0.4]"),
            relation("new:Heat", str(EXISTING_GRADE.id), "跨块", "0.3-1.1"),
            relation("new:Heat", str(EXISTING_GRADE.id), "倒序", "0.3-0.1"),
            relation("new:Heat", str(EXISTING_GRADE.id), "一端", "0.1-0.2"),
        ],
        properties=[],
    )
    literal: Counter[str] = Counter()
    proposals = build_proposals(
        [chunk, other],
        [EXISTING_GRADE],
        [entity("new:Heat", "炉次", sentence="0.1")],
        rels,
        literal=literal,
    )
    [kept] = [p for p in proposals if p.kind == "relation_type"]
    assert kept.fields["labelZh"] == "调整"
    [evidence] = kept.evidence
    assert (evidence.char_start, evidence.char_end) == (0, len(listed))
    assert evidence.quote == listed
    assert (literal["relation_type"], literal["relation_type:ok"]) == (5, 1)


def test_a_run_is_one_chunk_forwards_and_at_most_three_units() -> None:
    first = ChunkText(id=uuid4(), seq=0, text="甲。\n乙。\n丙。\n丁。")
    second = ChunkText(id=uuid4(), seq=1, text="戊。\n己。\n庚。\n辛。")
    builder = _Builder([first, second], [])
    run = builder.cite_run("0.2-0.4")
    assert run is not None
    assert (run.chunk_id, run.quote) == (first.id, "乙。\n丙。\n丁。")
    assert builder.cite_run("0.3") == builder.cite("0.3")
    for ref in ("0.4-1.1", "0.3-1.4", "0.3-0.1", "0.1-0.4", "0.3-0.5", "0.1-", None):
        assert builder.cite_run(ref) is None, ref


def test_a_run_does_not_join_names_across_units() -> None:
    # "钢种" would only appear by gluing the end of one unit to the start of the next.
    glued = ChunkText(id=uuid4(), seq=0, text="炉次见下钢\n\n种类一。")
    # The same run with the name inside one unit is direct evidence.
    whole = ChunkText(id=uuid4(), seq=1, text="炉次见下\n\n钢种类一。")
    rels = RelationsOut(
        relations=[
            relation("new:Heat", str(EXISTING_GRADE.id), "拼接", "0.1-0.2"),
            relation("new:Heat", str(EXISTING_GRADE.id), "完整", "1.1-1.2"),
        ],
        properties=[],
    )
    proposals = build_proposals(
        [glued, whole], [EXISTING_GRADE], [entity("new:Heat", "炉次", sentence="0.1")], rels
    )
    assert [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"] == ["完整"]


# A worksheet as the parser gives it (#60): the sheet name is the chunk's heading, the first
# row names the columns, and a data row names neither the table nor its columns.
_SHEET = (
    "| 记录号 | 点检日期 | 点检员 | 关联工单号 |\n"
    "| --- | --- | --- | --- |\n"
    "| DJJL-01 | 2026-11-02 | 马骏 | |\n"
    "| DJJL-02 | 2026-11-02 | 高翔 | |\n"
    "| DJJL-03 | 2026-11-03 | 林晓峰 | WO-0087 |"
)
_SHEET_TYPES = [
    entity("new:Record", "点检记录", sentence="0.1"),
    entity("new:Inspector", "点检员", sentence="0.1"),
    entity("new:Order", "维修工单", synonyms=["工单"], sentence="0.1"),
    entity("new:Equipment", "设备", sentence="0.1"),
]


def _sheet_relations(*cited: tuple[str, str, str, str | None]) -> RelationsOut:
    return RelationsOut(
        relations=[relation(d, r, label, ref) for d, r, label, ref in cited], properties=[]
    )


def test_a_table_row_counts_with_its_table_name_and_header_row() -> None:
    # 点检记录 is named only by the sheet, 工单 only by the header row, the row only by numbers.
    sheet = ChunkText(id=uuid4(), seq=0, text=_SHEET, heading="点检记录")
    literal: Counter[str] = Counter()
    proposals = build_proposals(
        [sheet],
        [],
        _SHEET_TYPES,
        _sheet_relations(
            ("new:Record", "new:Order", "关联工单", "0.5"),
            ("new:Record", "new:Inspector", "执行人", "0.3"),
            # Neither the row, its header nor the table name names 设备: dropped.
            ("new:Record", "new:Equipment", "点检设备", "0.5"),
        ),
        literal=literal,
    )
    kept = [p for p in proposals if p.kind == "relation_type"]
    assert [p.fields["labelZh"] for p in kept] == ["关联工单", "执行人"]
    # The reviewer sees the cited row and, as a second passage, the header row it is read by;
    # the table name is the chunk's heading, shown with every passage.
    header = _SHEET.split("\n")[0]
    assert [e.quote for e in kept[0].evidence] == [_SHEET.split("\n")[4], header]
    assert (kept[0].evidence[1].char_start, kept[0].evidence[1].char_end) == (0, len(header))
    # The literal share keeps measuring the cited text alone; rows kept by their table apart.
    assert literal["relation_type"] == 3
    assert literal["relation_type:ok"] == 0
    assert literal["relation_type:table"] == 2


def test_a_cited_header_row_needs_no_second_passage() -> None:
    sheet = ChunkText(id=uuid4(), seq=0, text=_SHEET, heading="点检记录")
    proposals = build_proposals(
        [sheet], [], _SHEET_TYPES, _sheet_relations(("new:Record", "new:Order", "关联", "0.1-0.3"))
    )
    [kept] = [p for p in proposals if p.kind == "relation_type"]
    assert [e.quote for e in kept.evidence] == ["\n".join(_SHEET.split("\n")[:3])]


def test_the_table_name_counts_for_table_rows_only() -> None:
    # Prose under a heading does not name what the heading names: a section title is no
    # evidence for every sentence in it.
    prose = ChunkText(
        id=uuid4(), seq=0, text="每次点检由点检员执行。\n发现异常时开立工单。", heading="点检记录"
    )
    proposals = build_proposals(
        [prose],
        [],
        _SHEET_TYPES,
        _sheet_relations(
            ("new:Record", "new:Inspector", "执行人", "0.1"),
            ("new:Record", "new:Order", "关联工单", "0.2"),
        ),
    )
    assert [p for p in proposals if p.kind == "relation_type"] == []


def test_the_header_row_is_found_in_the_chunks_before_of_the_same_table() -> None:
    lines = _SHEET.split("\n")
    first = ChunkText(id=uuid4(), seq=0, text="\n".join(lines[:3]), page=4, heading="点检记录")
    rest = "\n".join(lines[3:])
    # The same sheet goes on in the next chunk: same page, same heading.
    same = ChunkText(id=uuid4(), seq=1, text=rest, page=4, heading="点检记录")
    # Another sheet of the same name comes later: not the same table.
    other = ChunkText(id=uuid4(), seq=2, text=rest, page=5, heading="点检记录")
    proposals = build_proposals(
        [first, same, other],
        [],
        _SHEET_TYPES,
        _sheet_relations(
            ("new:Record", "new:Order", "关联工单", "1.2"),
            ("new:Record", "new:Order", "另一张表", "2.2"),
        ),
    )
    [kept] = [p for p in proposals if p.kind == "relation_type"]
    assert kept.fields["labelZh"] == "关联工单"
    assert [(e.chunk_id, e.quote) for e in kept.evidence] == [
        (same.id, lines[4]),
        (first.id, lines[0]),
    ]


def test_table_context_keeps_the_longest_and_separate_mentions() -> None:
    # 备件 inside the table name 备件领用 is no mention of its own; the 备件编码 column is.
    issue = ChunkText(
        id=uuid4(),
        seq=0,
        text="| 领用单号 | 数量 |\n| --- | --- |\n| LY-01 | 2 |",
        heading="备件领用",
    )
    coded = ChunkText(
        id=uuid4(),
        seq=1,
        text="| 领用单号 | 备件编码 |\n| --- | --- |\n| LY-01 | SP-01 |",
        heading="备件领用",
    )
    types = [
        entity("new:Slip", "备件领用单", synonyms=["备件领用"], sentence="0.1"),
        entity("new:Part", "备件", sentence="0.1"),
    ]
    proposals = build_proposals(
        [issue, coded],
        [],
        types,
        _sheet_relations(
            ("new:Slip", "new:Part", "领用备件", "0.3"), ("new:Slip", "new:Part", "领用", "1.3")
        ),
    )
    assert [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"] == ["领用"]


def test_a_table_row_cut_at_a_sentence_end_is_still_a_row_of_its_table() -> None:
    # A cell ending a sentence cuts its row into units; the piece after the cut and the rows
    # below it are still rows of the table.
    text = (
        "| 记录号 | 关联工单号 | 备注 |\n"
        "| --- | --- | --- |\n"
        "| DJJL-01 | WO-0086 | 漏油。已更换密封 |\n"
        "| DJJL-02 | WO-0087 | |"
    )
    units = [text[start:end] for start, end in split_sentences(text)]
    assert units[2:4] == ["| DJJL-01 | WO-0086 | 漏油。", "已更换密封 |"]
    sheet = ChunkText(id=uuid4(), seq=0, text=text, heading="点检记录")
    proposals = build_proposals(
        [sheet],
        [],
        _SHEET_TYPES,
        _sheet_relations(
            ("new:Record", "new:Order", "整改工单", "0.4"),
            ("new:Record", "new:Order", "关联工单", "0.5"),
        ),
    )
    kept = [p for p in proposals if p.kind == "relation_type"]
    assert [p.fields["labelZh"] for p in kept] == ["整改工单", "关联工单"]
    header = text.split("\n")[0]
    assert [e.quote for e in kept[0].evidence] == ["已更换密封 |", header]
    assert [e.quote for e in kept[1].evidence] == [text.split("\n")[3], header]


def test_the_header_row_is_found_across_the_chunker_line_break() -> None:
    # The chunker ends a chunk after a line break; a blank line there ends the table.
    page = ParsedPage(number=None, heading="点检记录", text=_SHEET)
    first, *rest = chunk_pages([page], max_chars=len("\n".join(_SHEET.split("\n")[:3])) + 2)
    assert first.text.endswith("|\n")
    chunks = [
        ChunkText(id=uuid4(), seq=seq, text=part.text, heading=part.heading)
        for seq, part in enumerate([first, *rest])
    ]
    apart = ChunkText(id=uuid4(), seq=0, text=first.text + "\n", heading="点检记录")
    after = ChunkText(id=uuid4(), seq=1, text=chunks[1].text, heading="点检记录")
    proposals = build_proposals(
        chunks, [], _SHEET_TYPES, _sheet_relations(("new:Record", "new:Order", "关联", "1.1"))
    )
    [kept] = [p for p in proposals if p.kind == "relation_type"]
    assert [e.quote for e in kept.evidence] == [_SHEET.split("\n")[3], _SHEET.split("\n")[0]]
    dropped = build_proposals(
        [apart, after],
        [],
        _SHEET_TYPES,
        _sheet_relations(("new:Record", "new:Order", "关联", "1.1")),
    )
    assert [p for p in dropped if p.kind == "relation_type"] == []


def test_the_header_row_is_not_looked_for_past_prose_in_the_chunk_before() -> None:
    lines = _SHEET.split("\n")
    # The chunk before ends with a paragraph: the rows that follow are of another table.
    first = ChunkText(
        id=uuid4(),
        seq=0,
        text="\n".join([*lines[:3], "", "以上为十一月记录。"]),
        heading="点检记录",
    )
    rest = ChunkText(id=uuid4(), seq=1, text="\n".join(lines[3:]), heading="点检记录")
    proposals = build_proposals(
        [first, rest],
        [],
        _SHEET_TYPES,
        _sheet_relations(("new:Record", "new:Order", "关联工单", "1.1")),
    )
    assert [p for p in proposals if p.kind == "relation_type"] == []


def test_rows_with_no_header_row_are_not_read_by_the_table_name() -> None:
    rows = ChunkText(id=uuid4(), seq=0, text="| DJJL-01 | 工单 WO-0086 |", heading="点检记录")
    proposals = build_proposals(
        [rows], [], _SHEET_TYPES, _sheet_relations(("new:Record", "new:Order", "关联", "0.1"))
    )
    assert [p for p in proposals if p.kind == "relation_type"] == []


def test_the_table_name_does_not_count_for_prose_cited_with_a_row() -> None:
    text = "发现异常时开立工单。\n| 记录号 | 点检日期 |\n| --- | --- |\n| DJJL-01 | 2026-11-02 |"
    chunk = ChunkText(id=uuid4(), seq=0, text=text, heading="点检记录")
    proposals = build_proposals(
        [chunk],
        [],
        _SHEET_TYPES,
        _sheet_relations(("new:Record", "new:Order", "关联工单", "0.1-0.3")),
    )
    assert [p for p in proposals if p.kind == "relation_type"] == []


def test_a_type_related_to_itself_needs_a_mention_in_the_cited_row() -> None:
    # 设备 is named by the table name and twice by the header row, never by the row itself.
    sheet = ChunkText(
        id=uuid4(),
        seq=0,
        text="| 设备编码 | 上级设备编码 |\n| --- | --- |\n| E-01 | E-00 |",
        heading="设备台账",
    )
    proposals = build_proposals(
        [sheet],
        [],
        [entity("new:Equipment", "设备", sentence="0.1")],
        _sheet_relations(("new:Equipment", "new:Equipment", "上级设备", "0.3")),
    )
    assert [p for p in proposals if p.kind == "relation_type"] == []


def test_a_cited_header_row_is_the_header_of_its_own_table() -> None:
    # Two tables with no blank line between: the cited header row is not read by the first's.
    text = (
        "| 序号 | 数量 |\n| --- | --- |\n| 1 | 2 |\n"
        "| 记录号 | 关联工单号 |\n| --- | --- |\n| DJJL-01 | WO-0086 |"
    )
    chunk = ChunkText(id=uuid4(), seq=0, text=text, heading="点检记录")
    proposals = build_proposals(
        [chunk], [], _SHEET_TYPES, _sheet_relations(("new:Record", "new:Order", "关联", "0.4"))
    )
    [kept] = [p for p in proposals if p.kind == "relation_type"]
    assert [e.quote for e in kept.evidence] == [text.split("\n")[3]]


def test_types_and_properties_still_cite_one_sentence() -> None:
    chunk = ChunkText(id=uuid4(), seq=0, text="炉次按计划组织生产。\n每个炉次记录出钢重量。")
    weight = prop("new:Heat", "出钢重量").model_copy(update={"sentence": "0.1-0.2"})
    proposals = build_proposals(
        [chunk],
        [],
        [entity("new:Heat", "炉次", sentence="0.1-0.2")],
        RelationsOut(relations=[], properties=[weight]),
    )
    # A run is not a sentence number: no evidence, flagged.
    assert all(p.flags == ["evidence_not_found"] for p in proposals)
    assert all(p.evidence == [] for p in proposals)


def test_the_relations_prompt_allows_a_short_run_of_sentences() -> None:
    assert "3.12-3.14" in RELATIONS_INSTRUCTIONS
    assert "3.12-3.14" in (RelationOut.model_fields["sentence"].description or "")
    assert "3.12-3.14" not in TYPES_INSTRUCTIONS
    assert "3.12-3.14" not in (PropertyOut.model_fields["sentence"].description or "")
    # The shared citing rule must not tell the relations stage to cite one sentence only.
    assert "Cite the one sentence" not in RELATIONS_INSTRUCTIONS


def test_types_and_resolve_judge_a_thing_and_its_record_alike() -> None:
    # #57: the types stage merged a thing and its record, resolve called them different.
    assert RECORD_RULE in TYPES_INSTRUCTIONS
    assert RECORD_RULE in RESOLVE_INSTRUCTIONS
    assert "a thing and the record of it (" not in RESOLVE_INSTRUCTIONS
    assert "identified and kept track of" in RECORD_RULE
    # An event and its numbered record stay one concept (the number identifies the event).
    assert "even when the record has a number" in RECORD_RULE


def test_the_types_prompt_names_what_is_not_a_type() -> None:
    # The three granularity rules of #58, and identity not only by a number.
    rules = " ".join(TYPES_INSTRUCTIONS.split())
    for phrase in (
        "by an action noun",
        "Registers, ledgers, directories, lists",
        "which documents are kept, by whom and for how long",
        "stays a type even without a number of its own",
        "Requests, applications, permits and notifications",
        "Lines or items of a plan",
        "a role that an existing kind of thing plays",
        "differ only by period or frequency",
        "not the only one",
    ):
        assert phrase in rules
    # Kinds told apart by a category stay types (a subclass of equipment, say).
    assert "differ only by period, frequency or category" not in rules


def test_the_types_prompt_keeps_lines_and_results_that_are_tracked_one_by_one() -> None:
    # #93: the prompt gave "an order line" as a line that is never a type, while an order line
    # with its own number that later records cite line by line is one (steel-industry answers).
    rules = " ".join(TYPES_INSTRUCTIONS.split())
    assert "an order line" not in rules
    assert "has a line number of its own and that other records refer to line by line" in rules
    # Item-by-item test results are records, not the outcome values listed above them.
    assert "are records, not values" in rules
    # Paper that only goes with a thing or a handover is not a type of its own.
    assert "Slips, copies, receipts, tags, labels and attachments" in rules
    assert "Being mentioned, kept, handed over or referred to is not enough" in rules


def test_the_prompts_give_examples_in_generic_words_only() -> None:
    cjk = re.compile(r"[一-鿿]")
    for prompt in (TYPES_INSTRUCTIONS, RESOLVE_INSTRUCTIONS, RELATIONS_INSTRUCTIONS):
        assert not cjk.search(prompt)


async def test_short_ids_in_the_output_stand_for_the_existing_types() -> None:
    types = [
        entity("E1", "钢种", synonyms=["钢级"], sentence="0.1"),
        entity("new:Heat", "炉次", parent="e1", sentence="0.1"),
    ]
    rels = RelationsOut(
        relations=[relation("new:Heat", "E1", "冶炼", "0.1")],
        properties=[prop("E1", "牌号长度").model_copy(update={"sentence": "0.1"})],
    )
    gateway = ScriptedGateway(outputs(types, rels))
    proposals, _ = await run(gateway, [EXISTING_GRADE])

    grade = str(EXISTING_GRADE.id)
    assert [(p.op, p.kind, p.target_element_id) for p in proposals][:2] == [
        ("update", "entity_type", EXISTING_GRADE.id),
        ("create", "entity_type", None),
    ]
    assert by_label(proposals, "炉次").fields["parentRef"] == grade
    assert by_label(proposals, "冶炼").fields["rangeRef"] == grade
    assert by_label(proposals, "牌号长度").fields["domainRef"] == grade
    relations_text = next(text for purpose, text in gateway.texts if purpose == "extract.relations")
    assert "- E1 | 钢种 | 钢级 |" in relations_text
    assert "[0.1] 每个炉次只冶炼一个钢种。\n[0.2] 钢水由钢包吊运至精炼炉。" in relations_text
    assert grade not in relations_text


def test_sentence_numbers_are_read_with_or_without_brackets() -> None:
    assert [sentence_ref(v) for v in ("3.12", "[3.12]", " 0.1 ", "3", "3.x", "", None)] == [
        "3.12",
        "3.12",
        "0.1",
        None,
        None,
        None,
        None,
    ]


async def test_a_short_id_the_call_did_not_show_points_nowhere() -> None:
    # The calls show eight existing types, E1 to E8; the model gave a new type the short id
    # E9. It stays a new type, and what refers to E9 refers to it, not to an existing type.
    known = [
        KnownElement(id=uuid4(), kind="entity_type", local_name=f"T{n}", label_zh=f"设备{n}")
        for n in range(1, 10)
    ]
    types = [
        entity("E9", "炉次", label_en="Heat", sentence="0.1"),
        entity("new:Cast", "浇次", parent="E9", sentence="1.1"),
    ]
    rels = RelationsOut(
        relations=[],
        properties=[prop("E9", "炉号").model_copy(update={"sentence": "0.1"})],
    )
    gateway = ScriptedGateway(
        {
            "extract.terms": [TermsOut(terms=[])],
            "extract.types": [TypesOut(entity_types=types)],
            "extract.relations": [rels],
        }
    )
    proposals, _ = await run(gateway, known[:8])

    heat = by_label(proposals, "炉次")
    assert (heat.op, heat.fields["localName"]) == ("create", "Heat")
    assert by_label(proposals, "浇次").fields["parentRef"] == "new:Heat"
    [number] = [p for p in proposals if p.kind == "property"]
    assert number.fields["domainRef"] == heat.temp_ref == "new:Heat"


async def test_a_term_is_shown_with_at_most_three_sentences() -> None:
    chunk = ChunkText(id=uuid4(), seq=0, text="钢包一。钢包二。钢包三。钢包四。")
    gateway = ScriptedGateway(
        {
            "extract.terms": [TermsOut(terms=[term("钢包")])],
            "extract.types": [TypesOut(entity_types=[])],
            "extract.relations": [RelationsOut(relations=[], properties=[])],
        }
    )
    extractor = Extractor(gateway, ExtractionModels(standard="std", reasoning="deep"))

    async def progress(step: str, done: int, total: int) -> None:
        pass

    await extractor.run(document_id=DOC, title="t", chunks=[chunk], known=[], progress=progress)
    [text] = types_texts(gateway)
    assert text.endswith("- entity | 钢包 |  |  | [0.1] 钢包一。; [0.2] 钢包二。; [0.3] 钢包三。")
