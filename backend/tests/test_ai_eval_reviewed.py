"""Reviewed sequential evaluation uses an in-memory reviewer and memory."""

import base64
import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast
from unittest.mock import patch
from uuid import UUID

import pytest
from pydantic import BaseModel

import ontology_platform.modules.ai.eval as eval_module
from ontology_platform.modules.ai import extraction
from ontology_platform.modules.ai.candidates import THRESHOLD, Names
from ontology_platform.modules.ai.candidates import score as candidate_score
from ontology_platform.modules.ai.eval import (
    MemoryStep,
    OracleReviewer,
    WorkingVersion,
    evaluate,
    memory_metrics,
    run_case,
    stable_id,
)
from ontology_platform.modules.ai.extraction import TYPES_BATCH_TERMS, ProposedMatch, types_context
from ontology_platform.modules.ai.gateway import InputFile
from ontology_platform.modules.ai.replay import ReplayGateway
from ontology_platform.modules.ontology.review_memory import (
    MemoryEntry,
    ReviewMemory,
    collect,
    pair_key,
)
from test_ai_eval import CASE_FILES, MODELS, ModelStandIn, _relation, _type, create

EXPECTED = {
    "entity_types": [{"names": ["炉次", "Heat"], "core": True}],
    "relations": [{"domain": "炉次", "range": "炉次", "core": True}],
}


def test_oracle_rejects_unknown_type_with_reason() -> None:
    reviewer = OracleReviewer(EXPECTED)
    decision = reviewer.review([create("entity_type", "new:Noise", "噪声")], "a", None)
    assert decision[1][0].decision == "rejected"
    assert decision[1][0].reject_reason == "incorrect"


def test_oracle_renames_alias_to_first_name() -> None:
    reviewer = OracleReviewer(EXPECTED)
    accepted, decided = reviewer.review([create("entity_type", "new:Heat", "Heat")], "a", None)
    assert accepted[0].fields["labelZh"] == "炉次"
    assert decided[0].proposed_label_zh == "Heat"


def test_oracle_rejects_unknown_relation() -> None:
    reviewer = OracleReviewer(EXPECTED)
    proposal = create("relation_type", "new:Other", "其他", domainRef="new:A", rangeRef="new:B")
    assert reviewer.review([proposal], "a", None)[1][0].decision == "rejected"


def test_oracle_accepts_property_without_expected_list() -> None:
    reviewer = OracleReviewer(EXPECTED)
    proposal = create("property", "new:P", "温度", domainRef="new:Heat")
    assert reviewer.review([proposal], "a", None)[1][0].decision == "accepted"


def test_oracle_alignment_uses_expected_groups() -> None:
    reviewer = OracleReviewer(
        {
            "entity_types": [
                {"names": ["炉次", "Heat"], "core": True},
                {"names": ["浇次"], "core": True},
            ],
            "relations": [],
        }
    )
    heat = create("entity_type", "new:Heat", "Heat")
    same = create("entity_type", "new:AnotherHeat", "炉次")
    different = create("entity_type", "new:Cast", "浇次")
    reviewer.remember("a", [heat])
    decide = reviewer.decider(WorkingVersion(), [same, different])
    from ontology_platform.modules.ai.eval import item_id

    record = ProposedMatch("possible", item_id=item_id("a", 1))
    assert decide(same, record) == "same"
    assert decide(different, record) == "different"


def test_empty_memory_metrics_have_null_ratios() -> None:
    result = memory_metrics([], ReviewMemory(UUID(int=0), ()), enabled=True)
    for key in (
        "reproposeModel",
        "reproposeReview",
        "variantRepropose",
        "renameReuse",
        "keptApartViolation",
    ):
        assert result[key] == {"numerator": 0, "denominator": 0, "ratio": None}


@pytest.mark.parametrize("field", ["reviewed", "noMemory"])
def test_flags_must_be_boolean(field: str) -> None:
    bundle: dict[str, Any] = {"files": {}, field: "true"}
    with pytest.raises(ValueError, match=field):
        evaluate(bundle)


async def test_legacy_sequential_output_is_identical_with_explicit_false() -> None:
    files = CASE_FILES
    first = ReplayGateway({}, ModelStandIn())
    previous = await run_case(files, first, MODELS, ["sequential"])
    recordings = first.recording_files()
    second = ReplayGateway({}, ModelStandIn())
    current = await run_case(files, second, MODELS, ["sequential"], reviewed=False)
    assert {k: v for k, v in current.items() if k != "usage"} == {
        k: v for k, v in previous.items() if k != "usage"
    }
    assert [
        (name, json.loads(data).get("input", data)) for name, data in second.recording_files()
    ] == [(name, json.loads(data).get("input", data)) for name, data in recordings]


def _bundle(**extra: Any) -> dict[str, Any]:
    return {
        "files": {name: base64.b64encode(data).decode() for name, data in CASE_FILES.items()},
        "scenarios": ["sequential"],
        **extra,
    }


async def test_reviewed_run_reports_memory() -> None:
    result = await run_case(
        REPEATED_FILES, ReplayGateway({}, RepeatingModel()), MODELS, ["sequential"], reviewed=True
    )
    control = await run_case(
        REPEATED_FILES,
        ReplayGateway({}, RepeatingModel()),
        MODELS,
        ["sequential"],
        reviewed=True,
        no_memory=True,
    )
    assert result["memory"]["entries"] == 1
    assert control["memory"]["entries"] == 1
    assert result["merge"]["review"] == "oracle"


class RepeatingModel(ModelStandIn):
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
        if purpose == "extract.types":
            self.calls += 1
            return schema.model_validate({"entity_types": [_type("new:Noise", "噪声", "Noise")]})
        if purpose == "extract.relations":
            self.calls += 1
            return schema.model_validate({"relations": [], "properties": []})
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


REPEATED_FILES = {
    "docs/a.md": "# 一\n\n噪声是一种类型。\n".encode(),
    "docs/b.md": "# 二\n\n噪声是一种类型。\n".encode(),
    "eval/expected.toml": (
        'entity_types = [{ names = ["炉次"], core = true }]\n'
        'relations = [{ domain = "炉次", range = "炉次", core = true }]\n'
    ).encode(),
}


async def test_memory_suppresses_a_rejected_type_in_second_document() -> None:
    result = await run_case(
        REPEATED_FILES,
        ReplayGateway({}, RepeatingModel()),
        MODELS,
        ["sequential"],
        reviewed=True,
    )
    assert result["memory"]["reproposeModel"] == {
        "numerator": 1,
        "denominator": 1,
        "ratio": 1.0,
    }
    assert result["memory"]["reproposeReview"] == {
        "numerator": 0,
        "denominator": 1,
        "ratio": 0.0,
    }
    assert result["proposals"] == 1


async def test_without_memory_rejected_type_reaches_second_change_set() -> None:
    result = await run_case(
        REPEATED_FILES,
        ReplayGateway({}, RepeatingModel()),
        MODELS,
        ["sequential"],
        reviewed=True,
        no_memory=True,
    )
    assert result["memory"]["enabled"] is False
    assert result["memory"]["reproposeReview"] == {
        "numerator": 1,
        "denominator": 1,
        "ratio": 1.0,
    }


async def test_renamed_name_is_reused_on_next_document() -> None:
    class RenamedModel(RepeatingModel):
        async def structured[T: BaseModel](self, **call: Any) -> T:
            if call["purpose"] == "extract.types":
                self.calls += 1
                label = (
                    "炉次" if call["document_id"] == stable_id("document", "docs/b.md") else "Heat"
                )
                return cast(
                    T,
                    call["schema"].model_validate(
                        {"entity_types": [_type("new:Heat", label, "Heat")]}
                    ),
                )
            return await super().structured(**call)

    files = {
        **CASE_FILES,
        "docs/a.md": b"# Heat\n\nHeat is a type.\n",
        "docs/b.md": "# 炉次\n\n炉次是一个类型。\n".encode(),
        "eval/expected.toml": (
            'entity_types = [{ names = ["炉次", "Heat"], core = true }]\n'
            'relations = [{ domain = "炉次", range = "炉次", core = true }]\n'
        ).encode(),
    }
    result = await run_case(
        files, ReplayGateway({}, RenamedModel()), MODELS, ["sequential"], reviewed=True
    )
    assert result["memory"]["renameReuse"] == {
        "numerator": 1,
        "denominator": 1,
        "ratio": 1.0,
    }


@pytest.mark.parametrize("kind", ["relation_type", "property"])
def test_oracle_reviews_dependents_against_expected_type_groups(kind: str) -> None:
    reviewer = OracleReviewer({**EXPECTED, "properties": [{"names": ["炉号"], "domain": "炉次"}]})
    version = WorkingVersion()
    version.merge([create("entity_type", "new:Known", "炉次")])
    heat = create("entity_type", "new:Heat", "冶炼批次", synonyms=[{"lang": "en", "text": "Heat"}])
    noise = create("entity_type", "new:Noise", "噪声")
    # Only the accepted type belongs to an expected group. The range is an existing type.
    fields = {"rangeRef": str(version.elements[0].id)} if kind == "relation_type" else {}
    wanted = create(kind, "new:Wanted", "炉号", domainRef="new:Heat", **fields)
    unwanted = create(kind, "new:Unwanted", "炉号", domainRef="new:Noise", **fields)
    accepted, decided = reviewer.review([heat, noise, wanted, unwanted], "a", version)
    assert [p.temp_ref for p in accepted] == ["new:Heat", "new:Wanted"]
    assert [d.decision for d in decided] == ["accepted", "rejected", "accepted", "rejected"]


def _entry(kind: str, key: str, label: str, other: str | None = None) -> MemoryEntry:
    from datetime import UTC, datetime

    return MemoryEntry(
        id=UUID(int=1),
        kind=cast(Any, kind),
        element_kind="entity_type",
        key=key,
        label=label,
        reason=None,
        label_en=None,
        domain=None,
        range=None,
        to_label_zh=None,
        to_label_en=None,
        element_id=None,
        other_label=other,
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        last_hit_at=None,
    )


def test_variant_repropose_counts_similar_new_type() -> None:
    memory = ReviewMemory(UUID(int=0), (_entry("rejected", "t:钢包车", "钢包车"),))
    variant = create("entity_type", "new:V", "钢包车辆")
    similarity = candidate_score(Names.of("钢包车辆", None, ()), Names.of("钢包车", None, ()))
    assert similarity.value >= THRESHOLD
    step = MemoryStep(memory, (variant,), (variant,), ())
    result = memory_metrics([step], memory, enabled=True)
    assert result["variantRepropose"] == {"numerator": 1, "denominator": 1, "ratio": 1.0}


def test_kept_apart_violation_counts_marked_pair() -> None:
    memory = ReviewMemory(
        UUID(int=0), (_entry("kept_apart", pair_key("炉次", "浇次"), "炉次", "浇次"),)
    )
    first = create("entity_type", "new:A", "炉次")
    second = create("entity_type", "new:B", "浇次")
    second = replace(second, match=ProposedMatch("possible", temp_ref="new:A"))
    step = MemoryStep(memory, (first, second), (first, second), ())
    result = memory_metrics([step], memory, enabled=True)
    assert result["keptApartViolation"] == {"numerator": 1, "denominator": 1, "ratio": 1.0}


class ExistingTypeLinksModel(RepeatingModel):
    def __init__(self, kind: str) -> None:
        super().__init__()
        self.kind = kind

    async def structured[T: BaseModel](self, **call: Any) -> T:
        purpose = call["purpose"]
        first = call["document_id"] == stable_id("document", "docs/a.md")
        if purpose == "extract.types":
            self.calls += 1
            types = [_type("new:Heat", "炉次", "Heat")] if first else []
            return cast(T, call["schema"].model_validate({"entity_types": types}))
        if purpose == "extract.relations":
            self.calls += 1
            if first:
                values: dict[str, Any] = {"relations": [], "properties": []}
            elif self.kind == "relation_type":
                values = {"relations": [_relation("E1", "E1")], "properties": []}
            else:
                values = {
                    "relations": [],
                    "properties": [
                        {
                            "label_zh": "炉号",
                            "local_name": "heatNumber",
                            "domain": "E1",
                            "datatype": "string",
                            "unit": None,
                            "required": False,
                            "multiple": False,
                            "definition_zh": None,
                            "confidence": 0.9,
                            "sentence": "0.2",
                        }
                    ],
                }
            return cast(T, call["schema"].model_validate(values))
        return await super().structured(**call)


@pytest.mark.parametrize("kind", ["relation_type", "property"])
@pytest.mark.parametrize("no_memory", [False, True])
async def test_repeated_link_to_existing_type_counts_model_reproposal(
    kind: str, no_memory: bool
) -> None:
    files = {
        "docs/a.md": "# 一\n\n炉次是一种类型。\n".encode(),
        "docs/b.md": "# 二\n\n炉次包含炉次，炉次有炉号。\n".encode(),
        "docs/c.md": "# 三\n\n炉次包含炉次，炉次有炉号。\n".encode(),
        "eval/expected.toml": (
            'entity_types = [{ names = ["炉次"], core = true }, '
            '{ names = ["浇次"], core = true }]\n'
            'relations = [{ domain = "炉次", range = "浇次", core = true }]\n'
            "properties = []\n"
        ).encode(),
    }
    result = await run_case(
        files,
        ReplayGateway({}, ExistingTypeLinksModel(kind)),
        MODELS,
        ["sequential"],
        reviewed=True,
        no_memory=no_memory,
    )
    assert result["memory"]["reproposeModel"] == {
        "numerator": 1,
        "denominator": 1,
        "ratio": 1.0,
    }
    assert result["memory"]["reproposeReview"]["numerator"] == int(no_memory)


class DocumentModel(ModelStandIn):
    """Return each document's scripted outputs at the same stages as the extractor."""

    def __init__(self, replies: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
        super().__init__()
        self.replies = {stable_id("document", path): reply for path, reply in replies.items()}

    async def structured[T: BaseModel](
        self, *, purpose: str, schema: type[T], document_id: UUID | None = None, **kwargs: Any
    ) -> T:
        assert document_id is not None
        reply = self.replies[document_id]
        fields = {
            "extract.terms": ("terms",),
            "extract.types": ("entity_types",),
            "extract.resolve": ("decisions",),
            "extract.relations": ("relations", "properties"),
        }[purpose]
        self.calls += 1
        return schema.model_validate({key: reply.get(key, []) for key in fields})


HEAT_AND_CAST = (
    'entity_types = [{ names = ["浇次", "Cast"], core = true }, '
    '{ names = ["炉次", "Heat"], core = true }]\n'
    'relations = [{ domain = "炉次", range = "浇次", core = true }]\n'
).encode()


@pytest.mark.parametrize("same_document", [False, True])
async def test_rejected_relation_uses_final_endpoint_name_in_run(same_document: bool) -> None:
    files = {
        "docs/a.md": "# 一\n\nHeat 包含 Heat。\n".encode(),
        "docs/b.md": "# 二\n\n炉次包含炉次。\n".encode(),
        "eval/expected.toml": HEAT_AND_CAST,
    }
    replies = {
        "docs/a.md": {"entity_types": [_type("new:Heat", "Heat", "Heat")]},
        "docs/b.md": {"relations": [_relation("E1", "E1")]},
    }
    if same_document:
        replies["docs/a.md"]["relations"] = [_relation("new:Heat", "new:Heat")]
    else:
        files["docs/c.md"] = "# 三\n\n炉次包含炉次。\n".encode()
        replies["docs/c.md"] = {"relations": [_relation("E1", "E1")]}
    result = await run_case(
        files,
        ReplayGateway({}, DocumentModel(replies)),
        MODELS,
        ["sequential"],
        reviewed=True,
        no_memory=True,
    )
    assert [e["label_zh"] for e in result["elements"]] == ["炉次"]
    assert result["proposals"] == 3
    assert result["memory"]["reproposeModel"] == {"numerator": 1, "denominator": 1, "ratio": 1.0}


async def test_type_stage_existing_short_id_counts_rename_reuse() -> None:
    files = {
        "docs/a.md": b"# Heat\n\nHeat is a type.\n",
        "docs/b.md": "# 炉次\n\n炉次又称 Heat。\n".encode(),
        "eval/expected.toml": HEAT_AND_CAST,
    }
    # The second label is still the old name. Only its reference can count as reuse.
    model = DocumentModel(
        {
            "docs/a.md": {"entity_types": [_type("new:Heat", "Heat", "Heat")]},
            "docs/b.md": {"entity_types": [_type("E1", "Heat", "Heat")]},
        }
    )
    result = await run_case(files, ReplayGateway({}, model), MODELS, ["sequential"], reviewed=True)
    assert result["memory"]["renameReuse"] == {"numerator": 1, "denominator": 1, "ratio": 1.0}


async def test_capture_ignores_empty_normalized_term_at_batch_boundary() -> None:
    names = [f"Type{i}" for i in range(TYPES_BATCH_TERMS + 1)]
    terms: list[dict[str, Any]] = [
        {"name": name, "english": None, "definition": None, "category": "entity", "quotes": []}
        for name in ["   ", *names]
    ]
    files = {"docs/a.md": b"# Types\n\nSome terms.\n", "eval/expected.toml": HEAT_AND_CAST}
    model = DocumentModel({"docs/a.md": {"terms": terms}})
    with (
        patch.object(extraction, "types_context", wraps=types_context) as extractor,
        patch.object(eval_module, "types_context", wraps=types_context) as capture,
    ):
        await run_case(files, ReplayGateway({}, model), MODELS, ["sequential"], reviewed=True)
    batches = [call.args[1] for call in extractor.call_args_list]
    assert batches == [names[:-1], names[-1:]]
    assert [call.args[1] for call in capture.call_args_list] == batches


async def test_rejected_type_dependent_link_is_not_collected() -> None:
    files = {"docs/a.md": "# 一\n\n噪声包含噪声。\n".encode(), "eval/expected.toml": HEAT_AND_CAST}
    model = DocumentModel(
        {
            "docs/a.md": {
                "entity_types": [_type("new:Noise", "噪声", "Noise")],
                "relations": [_relation("new:Noise", "new:Noise")],
            }
        }
    )
    result = await run_case(files, ReplayGateway({}, model), MODELS, ["sequential"], reviewed=True)
    assert result["literalShare"]["relations"] == 1.0
    assert result["proposals"] == 2
    assert result["merge"]["skipped"] == 0
    assert result["elements"] == []
    assert result["memory"]["entries"] == 1


async def test_accepted_type_merged_into_existing_uses_target_labels() -> None:
    files = {
        "docs/a.md": "# 一\n\n浇次又称 Cast。\n".encode(),
        "docs/b.md": "# 二\n\nHeat 包含 Heat，资料又称它为浇次。\n".encode(),
        "eval/expected.toml": HEAT_AND_CAST,
    }
    # Heat is renamed to 炉次 by its own group. Its synonym matches the first group for alignment.
    model = DocumentModel(
        {
            "docs/a.md": {"entity_types": [_type("new:Cast", "浇次", "Cast")]},
            "docs/b.md": {
                "entity_types": [{**_type("new:Heat", "Heat", "Heat"), "synonyms": ["浇次"]}],
                "decisions": [{"type": "T1", "candidate": "C1", "verdict": "unsure", "reason": ""}],
                "relations": [_relation("new:Heat", "new:Heat")],
            },
        }
    )
    # Merging into an existing element creates no renamed entry. Inspect the input to collection.
    with patch.object(eval_module, "collect", wraps=collect) as collected:
        result = await run_case(
            files, ReplayGateway({}, model), MODELS, ["sequential"], reviewed=True
        )
    (target,) = result["elements"]
    assert (target["label_zh"], target["label_en"]) == ("浇次", "Cast")
    assert "炉次" in target["synonyms"]
    item, link = collected.call_args_list[1].args[1]
    assert (item.op, item.decision, item.match_decision) == ("create", "accepted", "same")
    assert item.proposed_label_zh == "Heat"
    assert (item.final_label_zh, item.final_label_en) == (target["label_zh"], target["label_en"])
    assert (link.decision, link.domain_label, link.range_label) == ("rejected", "浇次", "浇次")
