"""Reviewed sequential evaluation uses an in-memory reviewer and memory."""

import base64
import json
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai.eval import (
    MemoryStep,
    OracleReviewer,
    WorkingVersion,
    evaluate,
    memory_metrics,
    run_case,
    stable_id,
)
from ontology_platform.modules.ai.extraction import ProposedMatch
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
    from uuid import UUID

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


def test_rejected_relation_uses_merged_renamed_domain() -> None:
    reviewer = OracleReviewer({"entity_types": [{"names": ["炉次", "Heat"]}], "relations": []})
    version = WorkingVersion()
    accepted, _ = reviewer.review([create("entity_type", "new:Heat", "Heat")], "a", version)
    version.merge(accepted, "a")
    relation = create(
        "relation_type",
        "new:R",
        "无效关系",
        domainRef=str(version.elements[0].id),
        rangeRef=str(version.elements[0].id),
    )
    _, decided = reviewer.review([relation], "b", version)
    assert decided[0].domain_label == "炉次"
    assert decided[0].range_label == "炉次"
    assert collect("ai_extraction", decided).upserts[0].key == "r:炉次|无效关系|炉次"


def test_rejected_type_leaves_dependent_relation_out_of_memory() -> None:
    reviewer = OracleReviewer(EXPECTED)
    proposals = [
        create("entity_type", "new:Noise", "噪声"),
        create("relation_type", "new:R", "无效关系", domainRef="new:Noise", rangeRef="new:Noise"),
    ]
    _, decided = reviewer.review(proposals, "a", WorkingVersion())
    assert decided[1].domain_label is None
    assert decided[1].range_label is None


def _entry(kind: str, key: str, label: str, other: str | None = None) -> MemoryEntry:
    from datetime import UTC, datetime
    from uuid import UUID

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
    from uuid import UUID

    memory = ReviewMemory(UUID(int=0), (_entry("rejected", "t:钢包车", "钢包车"),))
    variant = create("entity_type", "new:V", "钢包车辆")
    step = MemoryStep(memory, (variant,), (variant,), ())
    result = memory_metrics([step], memory, enabled=True)
    assert result["variantRepropose"]["numerator"] == 1


def test_kept_apart_violation_counts_marked_pair() -> None:
    from uuid import UUID

    memory = ReviewMemory(
        UUID(int=0), (_entry("kept_apart", pair_key("炉次", "浇次"), "炉次", "浇次"),)
    )
    first = create("entity_type", "new:A", "炉次")
    second = create("entity_type", "new:B", "浇次")
    second = replace(second, match=ProposedMatch("possible", temp_ref="new:A"))
    step = MemoryStep(memory, (first, second), (first, second), ())
    result = memory_metrics([step], memory, enabled=True)
    assert result["keptApartViolation"]["numerator"] == 1


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


async def test_rejected_type_dependent_link_is_not_collected() -> None:
    class DependentModel(RepeatingModel):
        async def structured[T: BaseModel](self, **call: Any) -> T:
            if call["purpose"] == "extract.relations":
                self.calls += 1
                return cast(
                    T,
                    call["schema"].model_validate(
                        {"relations": [_relation("new:Noise", "new:Noise")], "properties": []}
                    ),
                )
            return await super().structured(**call)

    result = await run_case(
        REPEATED_FILES,
        ReplayGateway({}, DependentModel()),
        MODELS,
        ["sequential"],
        reviewed=True,
    )
    assert result["memory"]["entries"] == 1
