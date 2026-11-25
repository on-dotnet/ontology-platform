"""Staged extraction with a scripted model: alignment, references, evidence grounding, progress."""

import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import Any
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
    batches,
    build_proposals,
    merge_types,
    normalize,
    resolve_requests,
)
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.prompts import (
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
        if purpose == "extract.resolve" and purpose not in self.outputs:
            answer = self.resolver(text)
            assert isinstance(answer, schema)
            return answer
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


async def test_a_type_named_as_an_existing_synonym_is_judged_and_recorded_as_the_same() -> None:
    # Was `_shares_name` (#33): a label that is an existing type's synonym aligned it. Now the
    # pair is a candidate (0.9) and the model judges; "same" is a recorded, new item that the
    # merge plan puts into the existing type (spec 004, 4.3).
    types = [entity("new:Grade", "牌号", "Grade", synonyms=["钢号"], quotes=[quote(0, "一个钢种")])]
    gateway = ScriptedGateway(
        outputs(types, RelationsOut(relations=[], properties=[])),
        judge({"牌号": ("钢种", "same")}),
    )
    proposals, _ = await run(gateway, [EXISTING_GRADE])

    [created] = proposals
    assert (created.op, created.temp_ref, created.flags) == ("create", "new:Grade", [])
    assert created.match == ProposedMatch("same", element_id=EXISTING_GRADE.id, reason="理由")
    assert created.fields["synonyms"] == [{"lang": "zh", "text": "钢号"}]
    # One call, with the candidate's names.
    [(_, text)] = [entry for entry in gateway.texts if entry[0] == "extract.resolve"]
    assert "T1 | 牌号 | 钢号 |" in text
    assert "C1 | 钢种 | 牌号 |" in text


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
    # `_maybe_update` stays for types of the existing type's main name (G1).
    types = [
        entity(str(EXISTING_GRADE.id), "钢种", "SteelGrade", synonyms=["钢级"]),
        entity("new:Grade", "钢种", "Grade", synonyms=["钢号", "钢级"]),
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


async def test_new_types_judged_the_same_are_recorded_for_the_merge() -> None:
    # Was the merge of new types by shared names (#7): now candidates the model judges. A new
    # type judged the same as an earlier one of this document stays an item with that record
    # (spec 004, 4.3), which the reviewer can overturn; the merge plan puts it into the other.
    types = [
        entity("new:LadleFurnace", "LF精炼炉", "LadleFurnace", synonyms=["精炼炉"]),
        entity("new:Ladle", "钢包", "Ladle"),
        # Another name of the same furnace.
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
        ("钢种", "Grade", ["钢包", "精炼炉"]),  # an existing type, by its main name (G1)
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
        entity("new:Grade", "钢种", "Grade", synonyms=["牌号"]),  # both the existing type (G1)
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


async def test_one_character_matches_are_at_most_possible_duplicates() -> None:
    # Was MIN_NAME and the merge of new types by name (#7, #33): one-character names neither
    # merged nor flagged. Now every pair the shortlist finds is judged; one found only through
    # a one-character name is at most a possible duplicate (G4).
    types = [
        entity("new:Converter", "转炉", "Converter", synonyms=["炉"]),
        entity("new:Reheater", "加热炉", "Reheater", synonyms=["炉"]),  # judged same: G4
        entity("new:Furnace", "炉", "Furnace"),  # judged same: G4
        entity("new:Refiner", "精炼炉", "Refiner", synonyms=["LF炉"]),
        entity("new:LF", "LF精炼炉", "LF", synonyms=["LF炉"]),  # judged unsure
        entity("new:Return", "回炉处理", "Return", quotes=[quote(0, "每个炉次只冶炼一个钢种")]),
        entity(
            "new:SlabReturn",
            "回炉处理",
            "SlabReturn",
            synonyms=["板坯回炉"],  # the main name of the earlier type (G1): joins it
            quotes=[quote(1, "一个浇次由若干个炉次"), quote(1, "没有这句话")],
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
    # Located quotes of the merged term are kept as evidence; unlocated ones are not.
    assert [e.chunk_id for e in merged.evidence] == [CHUNK_A.id, CHUNK_B.id]
    assert merged.flags == []
    # (Types without quotes also carry evidence_not_found.)
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
    types = [entity("new:ReheatingFurnace", "加热炉", "ReheatingFurnace", synonyms=["炉"])]
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
    types = [entity(str(CONVERTER.id), "加热炉", "ReheatingFurnace", synonyms=["炉"])]
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
    types = [entity(str(EXISTING_GRADE.id), "行车", "Crane")]
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
    types = [entity("new:Furnace", "加热炉", "ReheatingFurnace", label_en="Converter")]
    [created] = build_proposals([LADLE_CHUNK], [CONVERTER], types, NO_RELATIONS)

    # Local names take no part in the shortlist: no candidate, nothing to judge.
    assert resolve_requests([CONVERTER], types) == []
    assert (created.op, created.fields["labelZh"], created.match) == ("create", "加热炉", None)


def test_a_one_character_label_aligns_only_with_the_same_label() -> None:
    steel = KnownElement(id=uuid4(), kind="entity_type", local_name="Steel", label_zh="钢")
    types = [
        entity("new:Steel", "钢", "Steel", synonyms=["钢材"]),
        entity("new:MoltenSteel", "钢水", "MoltenSteel", synonyms=["钢"]),
        entity("new:Furnace", "炉", "Furnace"),
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
    types = [entity("new:Converter", "转炉", "Converter", synonyms=["转炉设备"])]
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
    types = [entity(str(EXISTING_GRADE.id), "钢号", "Grade", synonyms=["钢种"])]
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
    types = [entity(ref, "电炉", "ElectricFurnace", synonyms=["炼钢炉"])]
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
    types = [entity("new:Bof", "氧气转炉", "Bof", synonyms=["转炉"])]
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
        entity(str(steel.id), "钢", "Steel"),
        entity("new:Billet", "钢坯", "Billet", parent=str(steel.id)),
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
            relation(domain, range_, f"关系{index}", [quote(0, text)])
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
        entity("new:Heat", "炉次", "Heat"),
        entity("new:Ladle", "钢包", "Ladle"),
        entity("new:Refiner", "精炼炉", "Refiner"),
    ]
    rels = RelationsOut(
        relations=[
            relation("new:Heat", "new:Ladle", "使用", [quote(0, "钢水随后装入钢包")]),
            relation("new:Ladle", "new:Refiner", "运往", [quote(0, "钢水随后装入钢包")]),
            # A quote over two sentences takes both of them.
            relation("new:Heat", "new:Refiner", "经过", [quote(0, "在转炉冶炼。钢水随后")]),
        ],
        properties=[],
    )
    proposals = build_proposals([chunk], [], types, rels)

    assert [p.fields["labelZh"] for p in proposals if p.kind == "relation_type"] == [
        "运往",
        "经过",
    ]


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
        relations=[relation(str(heat.id), str(grade.id), "冶炼", [quote(0, "只冶炼一个钢种")])],
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
            "BOF",
            definition_zh="把铁水炼成钢水的炉子",
            synonyms=["炼钢转炉", "氧气转炉"],
            quotes=[quote(0, "一座转炉")],
        ),
        entity("new:Heat", "炉次", "Heat", quotes=[quote(0, "每个炉次")]),
    ]
    rels = RelationsOut(
        relations=[relation("new:Heat", "new:BOF", "冶炼于", [quote(0, "每个炉次都在一座转炉")])],
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
    types = [entity("new:Converter", "转炉", "Converter", quotes=[quote(0, "一座转炉")])]
    proposals = build_proposals(
        [CONVERTER_CHUNK], [], types, NO_RELATIONS, deleted=[DELETED_CONVERTER]
    )
    assert [(p.op, p.fields) for p in proposals] == [("restore", {})]


def test_two_types_named_as_one_deleted_type_give_one_restore() -> None:
    types = [
        entity("new:Converter", "转炉", "Converter", synonyms=["炼钢炉"]),
        entity("new:BOF", "转炉", "BOF", synonyms=["顶吹转炉"]),
    ]
    proposals = build_proposals(
        [CONVERTER_CHUNK], [], types, NO_RELATIONS, deleted=[DELETED_CONVERTER]
    )
    [restore] = proposals
    assert [s["text"] for s in restore.fields["synonyms"]] == ["炼钢炉", "顶吹转炉"]


def test_an_active_type_of_the_name_wins_over_a_deleted_one() -> None:
    active = KnownElement(id=uuid4(), kind="entity_type", local_name="Converter2", label_zh="转炉")
    types = [entity("new:Converter", "转炉", "Converter", synonyms=["炼钢炉"])]
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
        entity("new:Converter", "电炉", "Converter"),
        entity("new:Heat", "炉次", "Heat"),
    ]
    rels = RelationsOut(
        relations=[
            named_relation(
                relation("new:Heat", "new:Converter", "冶炼于", [quote(0, "每个炉次")]),
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
