"""Deterministic review-memory behavior in extraction."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ontology_platform.modules.ai.candidates import Names
from ontology_platform.modules.ai.extraction import (
    ChunkText,
    ExtractionModels,
    Extractor,
    KnownElement,
    MemoryOutcome,
    Proposal,
    ProposedMatch,
    build_proposals,
    mark_late_candidates,
    relations_catalog,
    resolve_requests,
)
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.memory_prompts import (
    MEMORY_RELATIONS_RULES,
    MEMORY_TYPES_RULES,
    relation_rows,
    type_rows,
    with_rows,
)
from ontology_platform.modules.ai.pipeline import make_extractor
from ontology_platform.modules.ai.prompts import (
    RELATIONS_INSTRUCTIONS,
    TYPES_INSTRUCTIONS,
    EntityTypeOut,
    PropertyOut,
    RelationOut,
    RelationsOut,
    TermOut,
    TermsOut,
    TypesOut,
)
from ontology_platform.modules.ontology import service as ontology_service
from ontology_platform.modules.ontology.review_memory import (
    MemoryEntry,
    MemoryKind,
    ReviewMemory,
    property_key,
    relation_key,
    type_key,
)
from test_ai_extraction import ScriptedGateway, decide
from test_ai_pipeline import add_document, factory, held, outputs
from test_ontology_support import add_elements, add_ontology, element


def test_rejected_new_type_is_suppressed() -> None:
    entry = MemoryEntry(
        id=uuid4(),
        kind="rejected",
        element_kind="entity_type",
        key=type_key("Rejected", None),
        label="Rejected",
        reason="incorrect",
        label_en=None,
        domain=None,
        range=None,
        to_label_zh=None,
        to_label_en=None,
        element_id=None,
        other_label=None,
        created_at=datetime.now(UTC),
        last_hit_at=None,
    )
    item = EntityTypeOut(
        ref="new:Rejected",
        label_zh="Rejected",
        label_en=None,
        definition_zh=None,
        synonyms=[],
        parent=None,
        confidence=1,
        sentence=None,
    )
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [],
        [item],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (entry,)),
        outcome=outcome,
    )
    assert proposals == []
    assert outcome.suppressed_total == 1
    assert outcome.suppressed[0].memory_entry_id == entry.id
    assert entry.id in outcome.memory_hits


def entry(kind: MemoryKind, key: str, label: str, element_id: UUID | None = None) -> MemoryEntry:
    return MemoryEntry(
        id=uuid4(),
        kind=kind,
        element_kind="entity_type",
        key=key,
        label=label,
        reason="incorrect" if kind == "rejected" else None,
        label_en=None,
        domain=None,
        range=None,
        to_label_zh="New name" if kind == "renamed" else None,
        to_label_en=None,
        element_id=element_id,
        other_label=None,
        created_at=datetime.now(UTC),
        last_hit_at=None,
    )


def entity(
    name: str, parent: str | None = None, synonyms: list[str] | None = None
) -> EntityTypeOut:
    return EntityTypeOut(
        ref=f"new:{name}",
        label_zh=name,
        label_en=None,
        definition_zh=None,
        synonyms=synonyms or [],
        parent=parent,
        confidence=1,
        sentence=None,
    )


def test_m1_child_and_existing_update() -> None:
    rejected = entry("rejected", type_key("Gone", None), "Gone")
    existing = KnownElement(uuid4(), "entity_type", "Current", "Current")
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [existing],
        [entity("Gone"), entity("Child", "new:Gone"), entity("Current", synonyms=["Gone"])],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (rejected,)),
        outcome=outcome,
    )
    assert {(p.op, p.kind) for p in proposals} == {
        ("create", "entity_type"),
        ("update", "entity_type"),
    }
    child = next(p for p in proposals if p.op == "create")
    assert child.fields["parentRef"] is None
    assert outcome.suppressed_total == 1
    assert outcome.memory_hits == {rejected.id}


def test_m1_synonym_does_not_suppress() -> None:
    rejected = entry("rejected", type_key("Gone", None), "Gone")
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [],
        [entity("Fresh", synonyms=["Gone"])],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (rejected,)),
        outcome=outcome,
    )
    assert len(proposals) == 1
    assert outcome.suppressed_total == 0


def test_m2_current_element_and_deleted_element() -> None:
    existing = KnownElement(uuid4(), "entity_type", "NewName", "New name")
    renamed = entry("renamed", type_key("Old name", None), "Old name", existing.id)
    memory = ReviewMemory(uuid4(), (renamed,))
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [existing],
        [entity("Old name")],
        RelationsOut(relations=[], properties=[]),
        memory=memory,
        outcome=outcome,
    )
    assert proposals == []
    assert outcome.memory_hits == {renamed.id}
    deleted = build_proposals(
        [],
        [],
        [entity("Old name")],
        RelationsOut(relations=[], properties=[]),
        deleted=[existing],
        memory=memory,
    )
    assert [(p.op, p.kind) for p in deleted] == [("create", "entity_type")]


def test_m2_does_not_add_old_name_from_model_synonyms() -> None:
    existing = KnownElement(uuid4(), "entity_type", "LadleCarrier", "钢包运输车")
    renamed = entry("renamed", type_key("钢包车", None), "钢包车", existing.id)
    proposals = build_proposals(
        [],
        [existing],
        [entity("钢包运输车", synonyms=["钢包车"])],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (renamed,)),
    )
    assert all(
        "钢包车" not in [s["text"] for s in proposal.fields.get("synonyms", [])]
        for proposal in proposals
    )


def test_m3_resolve_and_late_candidates() -> None:
    known = KnownElement(uuid4(), "entity_type", "Cart", "Cart")
    apart = entry("kept_apart", "k:car||cart", "Car")
    memory = ReviewMemory(uuid4(), (apart,))
    outcome = MemoryOutcome()
    assert resolve_requests([known], [entity("Car")], memory=memory, outcome=outcome) == []
    proposal = Proposal(
        op="create",
        kind="entity_type",
        fields={
            "labelZh": "Car",
            "labelEn": None,
            "synonyms": [],
        },
    )
    late = [
        (ProposedMatch("possible", element_id=known.id), Names.of("Cart", None, ()), "Cart", None)
    ]
    mark_late_candidates([proposal], late, memory=memory, outcome=outcome)
    assert proposal.match is None
    assert "possible_duplicate" not in proposal.flags
    assert outcome.memory_hits == {apart.id}


def test_m3_build_proposals_does_not_mark_kept_apart_candidate() -> None:
    known = KnownElement(uuid4(), "entity_type", "Cart", "Cart")
    apart = entry("kept_apart", "k:car||cart", "Car")
    proposals = build_proposals(
        [],
        [known],
        [entity("Car")],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (apart,)),
    )
    assert len(proposals) == 1
    assert proposals[0].match is None
    assert "possible_duplicate" not in proposals[0].flags


def test_prompt_selection_and_empty_input() -> None:
    rejected = entry("rejected", type_key("Boiler", None), "Boiler")
    memory = ReviewMemory(uuid4(), (rejected,))
    assert type_rows(memory, ["Unrelated"]) == []
    assert with_rows("old", "text", [], MEMORY_TYPES_RULES) == ("old", "text")
    rows = type_rows(memory, ["Boiler"])
    assert rows == ["- rejected type: Boiler (reason: incorrect)"]
    instructions, text = with_rows("old", "text", rows, MEMORY_TYPES_RULES)
    assert instructions.endswith(MEMORY_TYPES_RULES)
    assert rows[0] in text


def test_prompt_rows_are_recent_first_and_limited() -> None:
    old = replace(
        entry("rejected", type_key("Boiler", None), "Boiler"),
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    newer = replace(
        entry("renamed", type_key("Boilers", None), "Boilers"),
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    memory = ReviewMemory(uuid4(), (old, newer))
    assert type_rows(memory, ["Boiler"], limit=1) == ["- renamed type: Boilers -> New name"]


def test_last_hit_at_takes_priority_over_created_at() -> None:
    now = datetime.now(UTC)
    hit = replace(
        entry("rejected", type_key("Boiler", None), "Boiler"),
        created_at=now - timedelta(days=3),
        last_hit_at=now,
    )
    created = replace(
        entry("renamed", type_key("Boilers", None), "Boilers"), created_at=now - timedelta(days=1)
    )
    assert type_rows(ReviewMemory(uuid4(), (created, hit)), ["Boiler"], limit=1) == [
        "- rejected type: Boiler (reason: incorrect)"
    ]


def test_deleted_renamed_entry_is_not_sent_to_type_stage() -> None:
    deleted_id = uuid4()
    renamed = entry("renamed", type_key("Old name", None), "Old name", deleted_id)
    assert (
        type_rows(
            ReviewMemory(uuid4(), (renamed,)),
            ["Old name"],
            known=[KnownElement(uuid4(), "entity_type", "Current", "Current")],
        )
        == []
    )


def test_relation_rows_use_main_names_and_skip_unrelated_properties() -> None:
    # A property entry has no range; an English-only type must not select it through an
    # empty Chinese label.
    rejected = replace(
        entry("rejected", "p:other|code", "code"),
        element_kind="property",
        domain="Other",
    )
    memory = ReviewMemory(uuid4(), (rejected,))
    english_only = EntityTypeOut(
        ref="new:Scrap",
        label_zh=" ",
        label_en="Scrap",
        definition_zh=None,
        synonyms=[],
        parent=None,
        confidence=1,
        sentence=None,
    )
    lines, _ = relations_catalog([english_only, entity("Boiler")], [])
    assert [line[3] for line in lines] == ["scrap", "boiler"]
    assert relation_rows(memory, [line[3] for line in lines]) == []
    assert relation_rows(memory, [""]) == []
    assert relation_rows(memory, ["other"]) == [
        "- rejected property: Other | code (reason: incorrect)"
    ]


def test_chinese_memory_labels_remain_in_data_only() -> None:
    rejected = entry("rejected", type_key("炉渣颜色", None), "炉渣颜色")
    instructions, text = with_rows(
        TYPES_INSTRUCTIONS,
        "source",
        type_rows(ReviewMemory(uuid4(), (rejected,)), ["炉渣颜色"]),
        MEMORY_TYPES_RULES,
    )
    assert "炉渣颜色" in text
    assert "炉渣颜色" not in instructions
    assert all(not ("\u4e00" <= char <= "\u9fff") for char in instructions)


def test_m1_suppresses_dependent_relation_and_property() -> None:
    rejected = entry("rejected", type_key("Gone", None), "Gone")
    relation = RelationOut(
        label_zh="link",
        local_name="link",
        domain="new:Gone",
        range="new:Child",
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=1,
        sentence="0.1",
    )
    prop = PropertyOut(
        label_zh="code",
        local_name="code",
        domain="new:Gone",
        datatype="string",
        unit=None,
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=1,
        sentence="0.2",
    )
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [ChunkText(uuid4(), 0, "Gone link Child. Gone code.")],
        [],
        [entity("Gone"), entity("Child")],
        RelationsOut(
            relations=[
                relation,
                relation.model_copy(),
                relation.model_copy(update={"sentence": None}),
            ],
            properties=[
                prop,
                prop.model_copy(),
                # A property without evidence would still be proposed (flagged), so it counts.
                prop.model_copy(update={"label_zh": "weight", "sentence": None}),
            ],
        ),
        memory=ReviewMemory(uuid4(), (rejected,)),
        outcome=outcome,
    )
    assert [(p.kind, p.fields["labelZh"]) for p in proposals] == [("entity_type", "Child")]
    assert [(s.cause, s.label_zh) for s in outcome.suppressed] == [
        ("memory", "Gone"),
        ("depends_on_suppressed", "link"),
        ("depends_on_suppressed", "code"),
        ("depends_on_suppressed", "weight"),
    ]
    assert outcome.suppressed_total == 4
    assert [(s.memory_entry_id, s.depends_on) for s in outcome.suppressed[1:]] == [
        (rejected.id, "Gone"),
        (rejected.id, "Gone"),
        (rejected.id, "Gone"),
    ]


@pytest.mark.parametrize("verdicts", [None, {"Other": ("Gone", "same")}])
def test_m1_nothing_is_judged_against_a_suppressed_type(
    verdicts: dict[str, tuple[str | None, str]] | None,
) -> None:
    # "Other" shares a synonym with the rejected "Gone" of the same run. Unanswered (G5) or
    # judged the same, it would point at a type that is not in the change set.
    rejected = entry("rejected", type_key("Gone", None), "Gone")
    memory = ReviewMemory(uuid4(), (rejected,))
    types = [entity("Gone"), entity("Other", synonyms=["Gone"])]
    assert resolve_requests([], types, memory=memory) == []
    decisions = decide(types, [], verdicts, default=None)
    assert decisions or verdicts is None
    outcome = MemoryOutcome()
    [created] = build_proposals(
        [],
        [],
        types,
        RelationsOut(relations=[], properties=[]),
        decisions=decisions,
        memory=memory,
        outcome=outcome,
    )
    assert (created.fields["labelZh"], created.match) == ("Other", None)
    assert "possible_duplicate" not in created.flags
    assert outcome.suppressed_total == 1


def test_m1_an_english_only_twin_of_a_suppressed_type_goes_with_it() -> None:
    rejected = entry("rejected", type_key("废钢", None), "废钢")
    twin = EntityTypeOut(
        ref="new:Scrap",
        label_zh=" ",
        label_en="Scrap",
        definition_zh=None,
        synonyms=[],
        parent=None,
        confidence=1,
        sentence=None,
    )
    first = entity("废钢").model_copy(update={"label_en": "Scrap"})
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [],
        [first, twin],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), (rejected,)),
        outcome=outcome,
    )
    assert proposals == []
    assert [(s.cause, s.depends_on) for s in outcome.suppressed] == [
        ("memory", None),
        ("depends_on_suppressed", "废钢"),
    ]
    assert outcome.suppressed[1].memory_entry_id == rejected.id


def test_m1_suppresses_rejected_relation_and_property_keys() -> None:
    rejected_relation = replace(
        entry("rejected", relation_key("boiler", "links", "tank"), "links"),
        element_kind="relation_type",
    )
    rejected_property = replace(
        entry("rejected", property_key("boiler", "code"), "code"),
        element_kind="property",
    )
    relation = RelationOut(
        label_zh="links",
        local_name="links",
        domain="new:Boiler",
        range="new:Tank",
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=1,
        sentence="0.1",
    )
    prop = PropertyOut(
        label_zh="code",
        local_name="code",
        domain="new:Boiler",
        datatype="string",
        unit=None,
        required=False,
        multiple=False,
        definition_zh=None,
        confidence=1,
        sentence="0.2",
    )
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [ChunkText(uuid4(), 0, "Boiler links Tank. Boiler code.")],
        [],
        [entity("Boiler"), entity("Tank")],
        RelationsOut(relations=[relation], properties=[prop]),
        memory=ReviewMemory(uuid4(), (rejected_relation, rejected_property)),
        outcome=outcome,
    )
    assert [p.kind for p in proposals] == ["entity_type", "entity_type"]
    assert [s.cause for s in outcome.suppressed] == ["memory", "memory"]
    assert outcome.memory_hits == {rejected_relation.id, rejected_property.id}


def test_suppressed_list_is_capped_but_total_is_not() -> None:
    names = [f"Rejected{i}" for i in range(201)]
    entries = tuple(entry("rejected", type_key(name, None), name) for name in names)
    outcome = MemoryOutcome()
    proposals = build_proposals(
        [],
        [],
        [entity(name) for name in names],
        RelationsOut(relations=[], properties=[]),
        memory=ReviewMemory(uuid4(), entries),
        outcome=outcome,
    )
    assert proposals == []
    assert len(outcome.suppressed) == 200
    assert outcome.suppressed_total == 201
    assert outcome.memory_hits == {e.id for e in entries}


class CapturingGateway(ScriptedGateway):
    def __init__(self) -> None:
        super().__init__(
            {
                "extract.terms": [
                    TermsOut(
                        terms=[
                            TermOut(
                                name="Boiler",
                                english=None,
                                definition=None,
                                category="entity",
                                quotes=[],
                            )
                        ]
                    )
                ],
                "extract.types": [TypesOut(entity_types=[entity("Boiler")])],
                "extract.relations": [RelationsOut(relations=[], properties=[])],
            }
        )
        self.inputs: list[tuple[str, str, str]] = []

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
        self.inputs.append((purpose, instructions, text))
        return await super().structured(
            purpose=purpose,
            model=model,
            instructions=instructions,
            text=text,
            schema=schema,
            files=files,
            document_id=document_id,
            effort=effort,
        )


async def test_empty_and_unrelated_memory_leave_every_model_input_identical() -> None:
    captured: list[list[tuple[str, str, str]]] = []

    async def progress(_step: str, _done: int, _total: int) -> None:
        pass

    unrelated = entry("rejected", type_key("Unrelated", None), "Unrelated")
    for memory in (None, ReviewMemory(uuid4(), ()), ReviewMemory(uuid4(), (unrelated,))):
        gateway = CapturingGateway()
        extractor = Extractor(gateway, ExtractionModels("std", "deep"))
        await extractor.run(
            document_id=uuid4(),
            title="doc",
            chunks=[ChunkText(uuid4(), 0, "Boiler")],
            known=[],
            progress=progress,
            memory=memory,
        )
        captured.append(gateway.inputs)
    assert captured[0] == captured[1] == captured[2]
    for calls in captured:
        assert next(i for p, i, _ in calls if p == "extract.types") == TYPES_INSTRUCTIONS
        assert next(i for p, i, _ in calls if p == "extract.relations") == RELATIONS_INSTRUCTIONS
        assert all("Reviewer decisions" not in t for _, _, t in calls)


async def test_relevant_memory_appends_rules_and_data() -> None:
    rejected_type = entry("rejected", type_key("Boiler", None), "Boiler")
    rejected_relation = replace(
        entry("rejected", "r:boiler|link|boiler", "link"),
        element_kind="relation_type",
        domain="Boiler",
        range="Boiler",
    )
    memory = ReviewMemory(uuid4(), (rejected_type, rejected_relation))
    gateway = CapturingGateway()

    async def progress(_step: str, _done: int, _total: int) -> None:
        pass

    await Extractor(gateway, ExtractionModels("std", "deep")).run(
        document_id=uuid4(),
        title="doc",
        chunks=[ChunkText(uuid4(), 0, "Boiler")],
        known=[],
        progress=progress,
        memory=memory,
    )
    calls = {purpose: (instructions, text) for purpose, instructions, text in gateway.inputs}
    assert calls["extract.types"][0].endswith(MEMORY_TYPES_RULES)
    assert "- rejected type: Boiler" in calls["extract.types"][1]
    assert calls["extract.relations"][0].endswith(MEMORY_RELATIONS_RULES)
    assert "- rejected relation:" in calls["extract.relations"][1]
    assert relation_rows(memory, ["Boiler"], limit=1) == [
        "- rejected relation: Boiler | link | Boiler (reason: incorrect)"
    ]


async def test_the_extractor_caps_memory_rows_at_its_setting() -> None:
    # The worker passes `review_memory_prompt_max`; the default is the module's PROMPT_MAX.
    existing = KnownElement(uuid4(), "entity_type", "Boilers", "Boilers")
    memory = ReviewMemory(
        uuid4(),
        (
            entry("rejected", type_key("Boiler", None), "Boiler"),
            entry("renamed", type_key("Boilers", None), "Boilers", existing.id),
        ),
    )

    async def progress(_step: str, _done: int, _total: int) -> None:
        pass

    rows: list[int] = []
    for limit in (1, 2):
        gateway = CapturingGateway()
        await Extractor(gateway, ExtractionModels("std", "deep"), memory_prompt_max=limit).run(
            document_id=uuid4(),
            title="doc",
            chunks=[ChunkText(uuid4(), 0, "Boiler")],
            known=[existing],
            progress=progress,
            memory=memory,
        )
        text = next(t for purpose, _, t in gateway.inputs if purpose == "extract.types")
        rows.append(sum(line.startswith("- re") for line in text.splitlines()))
    assert rows == [1, 2]


@pytest.mark.parametrize("early", [False, True])
async def test_pipeline_persists_suppression_and_records_hits(
    app: FastAPI,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    early: bool,
) -> None:
    ontology = await add_ontology(db)
    grade = element(ontology, "entity_type", "SteelGrade", "钢种")
    await add_elements(db, grade)
    document, _ = await add_document(db, ontology)
    rejected = entry("rejected", type_key("炉次", None), "炉次")
    memory = ReviewMemory(ontology.id, (rejected,))
    hits: list[tuple[UUID, ...]] = []
    events: list[str] = []
    original_lock = ontology_service.lock_ontology

    async def lock_ontology(session: AsyncSession, target_id: UUID) -> None:
        await original_lock(session, target_id)
        events.append("lock")

    async def get_memory(_db: AsyncSession, _ontology_id: object) -> ReviewMemory:
        return memory

    async def record_hits(
        _db: AsyncSession,
        _ontology_id: object,
        entry_ids: Sequence[UUID],
    ) -> None:
        events.append("hits")
        hits.append(tuple(entry_ids))

    monkeypatch.setattr(ontology_service, "lock_ontology", lock_ontology)
    monkeypatch.setattr(ontology_service, "review_memory_for", get_memory)
    monkeypatch.setattr(ontology_service, "record_memory_hits", record_hits)
    canned = outputs(grade)
    if early:
        cast(TypesOut, canned["extract.types"][0]).entity_types.pop()
    gateway = ScriptedGateway(canned)
    extractor = make_extractor(factory(app), gateway, ExtractionModels("std", "deep"))
    change_set_id = await extractor(document.id, held)
    assert hits == [(rejected.id,)]
    assert events == ["lock", "hits"]
    if early:
        assert change_set_id is None
    else:
        assert change_set_id is not None
        detail = await ontology_service.get_change_set(db, change_set_id)
        assert detail.suppressed_total == 2
        assert detail.suppressed[0].memory_entry_id == rejected.id
        calls = list(gateway.calls)
        assert await extractor(document.id, held) == change_set_id
        assert gateway.calls == calls
        assert hits == [(rejected.id,)]
