"""Scoring of the extraction evaluation: synonyms count, direction does not, only core recalls."""

import base64
import json
import re
import tomllib
from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai.eval import (
    ExpectedError,
    WorkingVersion,
    check_expected,
    dump_elements,
    evaluate,
    load_elements,
    merge_counts,
    parse_expected,
    run_case,
    score,
)
from ontology_platform.modules.ai.extraction import ExtractionModels, KnownElement, Proposal
from ontology_platform.modules.ai.gateway import AiUnavailableError, InputFile
from ontology_platform.modules.ai.replay import ReplayGateway, ReplayMissError, load_recordings
from ontology_platform.settings import Settings

EXPECTED = {
    "entity_types": [
        {"names": ["炉次", "Heat"], "core": True},
        {"names": ["浇次", "CastingSequence"], "core": True},
        {"names": ["结晶器"], "core": False},
        {"names": ["钢卷", "Coil"], "core": True},
    ],
    "relations": [
        {"domain": "炉次", "range": "浇次", "core": True},
        {"domain": "钢卷", "range": "炉次", "core": True},
    ],
}


def create(kind: str, temp: str, label: str, **fields: object) -> Proposal:
    return Proposal(
        op="create",
        kind=kind,  # type: ignore[arg-type]
        temp_ref=temp,
        fields={"localName": temp.split(":")[1], "labelZh": label, "synonyms": [], **fields},
    )


def merged(
    proposals: Sequence[Proposal],
    *,
    known: Sequence[KnownElement] = (),
    parents: dict[UUID, UUID] | None = None,
) -> list[KnownElement]:
    """The elements after merging one change set with everything accepted."""
    version = WorkingVersion()
    version.elements = list(known)
    assert version.merge(proposals) == []
    if parents is not None:
        parents.update(version.parents)
    return version.elements


def test_merge_then_score() -> None:
    proposals = [
        create("entity_type", "new:Heat", "冶炼炉次", synonyms=[{"lang": "en", "text": "Heat"}]),
        create("entity_type", "new:Cast", "浇次"),
        create("entity_type", "new:Crane", "行车"),  # not expected: lowers precision
        create(
            "relation_type", "new:inSequence", "属于", domainRef="new:Cast", rangeRef="new:Heat"
        ),
    ]
    known = merged(proposals)
    result = score(known, EXPECTED)

    assert result["entityTypes"]["predicted"] == 3
    assert result["entityTypes"]["precision"] == round(2 / 3, 3)
    assert result["entityTypes"]["recall"] == round(2 / 3, 3)  # 钢卷 missed; 结晶器 is not core
    assert result["entityTypes"]["unmatched"] == ["行车"]
    assert result["entityTypes"]["missedCore"] == ["钢卷"]
    # direction is ignored: 浇次 → 炉次 matches the expected 炉次 → 浇次
    assert result["relations"] == {
        "predicted": 1,
        "precision": 1.0,
        "recall": 0.5,
        "unmatched": [],
    }


def test_updates_add_synonyms_to_existing_elements() -> None:
    element = KnownElement(id=uuid4(), kind="entity_type", local_name="Coil", label_zh="卷")
    update = Proposal(
        op="update",
        kind="entity_type",
        target_element_id=element.id,
        fields={"synonyms": [{"lang": "zh", "text": "钢卷"}]},
    )
    [updated] = merged([update], known=[element])
    assert updated.synonyms == ("钢卷",)
    assert score([updated], EXPECTED)["entityTypes"]["missedCore"] == ["炉次", "浇次"]


def test_unmatched_relations_are_listed_by_their_ends() -> None:
    proposals = [
        create("entity_type", "new:Heat", "炉次"),
        create("entity_type", "new:Crane", "行车"),
        create("relation_type", "new:lifts", "吊运", domainRef="new:Crane", rangeRef="new:Heat"),
    ]
    result = score(merged(proposals), EXPECTED)
    assert result["relations"]["unmatched"] == ["行车 → 炉次（吊运）"]


def test_saved_elements_score_the_same_after_loading() -> None:
    proposals = [
        create("entity_type", "new:Heat", "冶炼炉次", synonyms=[{"lang": "en", "text": "Heat"}]),
        create("entity_type", "new:Cast", "浇次"),
        create(
            "relation_type", "new:inSequence", "属于", domainRef="new:Cast", rangeRef="new:Heat"
        ),
    ]
    known = merged(proposals)
    saved = json.loads(json.dumps(dump_elements(known)))
    assert load_elements(saved) == known
    assert score(load_elements(saved), EXPECTED) == score(known, EXPECTED)


# ---------------------------------------------------------------- merging by the merge plan


def test_change_sets_are_merged_by_the_merge_plan() -> None:
    version = WorkingVersion()
    first = [
        create("entity_type", "new:Converter", "转炉", definitionZh="炼钢设备"),
        create("entity_type", "new:Heat", "炉次"),
        create(
            "relation_type", "new:smelts", "冶炼", domainRef="new:Heat", rangeRef="new:Converter"
        ),
        create("property", "new:weight", "装入量", domainRef="new:Heat"),
    ]
    # Identified against the same baseline: the second proposes the same concepts again.
    second = [
        create("entity_type", "new:BOF", "转炉", synonyms=[{"lang": "zh", "text": "氧气转炉"}]),
        create("entity_type", "new:Heat", "炉次"),
        create("relation_type", "new:makes", "冶炼", domainRef="new:Heat", rangeRef="new:BOF"),
        create("property", "new:weight", "出钢量", domainRef="new:Heat"),
    ]
    assert version.merge(first) == []
    assert version.merge(second) == []

    by_kind = sorted((e.kind, e.label_zh, e.local_name) for e in version.elements)
    assert by_kind == [
        ("entity_type", "炉次", "Heat"),
        ("entity_type", "转炉", "Converter"),
        ("property", "出钢量", "weight2"),  # another property: renamed, not skipped
        ("property", "装入量", "weight"),
        ("relation_type", "冶炼", "smelts"),
    ]
    [converter] = [e for e in version.elements if e.label_zh == "转炉"]
    assert (converter.synonyms, converter.definition_zh) == (("氧气转炉",), "炼钢设备")
    assert converter.revision == 2


def test_merge_counts_report_skipped_items_and_duplicates() -> None:
    expected = {
        "entity_types": [
            {"names": ["钢包", "盛钢桶"], "core": True},
            {"names": ["炉次"], "core": True},
            {"names": ["转炉"], "core": True},
        ],
        "relations": [{"domain": "炉次", "range": "转炉", "core": True}],
    }
    marked = create("entity_type", "new:Vessel", "盛钢桶")
    marked.flags.append("possible_duplicate")
    proposals = [
        create("entity_type", "new:Ladle", "钢包"),
        marked,
        create("entity_type", "new:Heat", "炉次"),
        # One change set only sees the working version: the plan does not merge within it.
        create("entity_type", "new:Heat2", "炉次"),
        create("entity_type", "new:Converter", "转炉"),
        create("entity_type", "new:BOF", "氧气转炉"),
        create("relation_type", "new:a", "使用", domainRef="new:Heat", rangeRef="new:Ladle"),
        create("relation_type", "new:b", "使用", domainRef="new:Heat", rangeRef="new:Ladle"),
        create("entity_type", "new:Orphan", "孤儿", parentRef="new:Ghost"),
        create("property", "new:d", "温度", domainRef="new:Orphan"),
    ]
    version = WorkingVersion()
    skipped = version.merge(proposals)
    counts = merge_counts(version, skipped, expected)

    assert counts["skippedByCode"] == {
        "changeset.dependency_skipped": 1,
        "changeset.invalid_item": 1,
    }
    assert (counts["skipped"], counts["duplicateRelations"]) == (2, 1)
    assert counts["duplicateTypeGroups"] == {
        "total": 2,
        "sameMainName": 1,
        "marked": 1,
        "unmarked": 0,
        # 氧气转炉 is no name of the expected 转炉 group: unexpected, not a duplicate.
        "groups": ["炉次 / 炉次", "钢包 / 盛钢桶"],
    }


def test_an_item_referencing_one_listed_after_it_is_merged_as_the_merge_does() -> None:
    proposals = [
        create("entity_type", "new:Converter", "转炉", parentRef="new:Equipment"),
        create(
            "relation_type", "new:smelts", "冶炼", domainRef="new:Heat", rangeRef="new:Converter"
        ),
        create("entity_type", "new:Equipment", "设备"),
        create("entity_type", "new:Heat", "炉次"),
    ]
    version = WorkingVersion()
    assert version.merge(proposals) == []

    # Elements keep the order of their items, as the ids the model is shown are derived in.
    names = [e.local_name for e in version.elements]
    assert names == ["Converter", "smelts", "Equipment", "Heat"]
    converter, smelts, equipment, heat = version.elements
    assert version.parents == {converter.id: equipment.id}
    assert (smelts.domain_id, smelts.range_id) == (heat.id, converter.id)


def test_a_reference_to_an_element_of_another_kind_is_an_invalid_item() -> None:
    proposals = [
        create("entity_type", "new:Heat", "炉次"),
        create("relation_type", "new:smelts", "冶炼", domainRef="new:Heat", rangeRef="new:Heat"),
        create("property", "new:weight", "装入量", domainRef="new:smelts"),
    ]
    version = WorkingVersion()
    assert version.merge(proposals) == ["changeset.invalid_item"]
    assert [e.local_name for e in version.elements] == ["Heat", "smelts"]


# ---------------------------------------------------------------- properties and hierarchy

EXPECTED_MORE = {
    "entity_types": [
        *EXPECTED["entity_types"],
        {"names": ["设备", "Equipment"], "core": False},
        {"names": ["转炉", "Converter"], "core": True},
    ],
    "relations": EXPECTED["relations"],
    "properties": [
        {"domain": "炉次", "names": ["出钢温度", "TappingTemperature"], "core": True},
        {"domain": "钢卷", "names": ["卷重"], "core": True},
        {"domain": "炉次", "names": ["炉龄"], "core": False},
    ],
    "hierarchy": [
        {"child": "转炉", "parent": "设备", "core": True},
        {"child": "钢卷", "parent": "设备", "core": False},
    ],
}


def test_merged_ids_follow_from_names_so_that_reruns_prompt_the_same() -> None:
    def run() -> tuple[list[KnownElement], dict[UUID, UUID]]:
        parents: dict[UUID, UUID] = {}
        known = merged(
            [
                create("entity_type", "new:Equipment", "设备"),
                create("entity_type", "new:Converter", "转炉", parentRef="new:Equipment"),
            ],
            parents=parents,
        )
        return known, parents

    (first, first_parents), (second, second_parents) = run(), run()
    assert [e.id for e in first] == [e.id for e in second]
    assert first_parents == second_parents == {first[1].id: first[0].id}


def test_properties_count_by_their_type_and_name() -> None:
    proposals = [
        create("entity_type", "new:Heat", "冶炼炉次", synonyms=[{"lang": "en", "text": "Heat"}]),
        create("entity_type", "new:Coil", "钢卷"),
        # the English local name matches TappingTemperature after normalizing
        create("property", "new:tappingTemperature", "出钢温度℃", domainRef="new:Heat"),
        create("property", "new:coilWeight", "卷重", domainRef="new:Heat"),  # wrong type
        create("property", "new:liningAge", "炉龄", domainRef="new:Heat"),  # acceptable
        create("property", "new:colour", "颜色", domainRef="new:Heat"),
    ]
    result = score(merged(proposals), EXPECTED_MORE)["properties"]
    assert result == {
        "predicted": 4,
        "precision": 0.5,
        "recall": 0.5,
        "unmatched": ["冶炼炉次.卷重", "冶炼炉次.颜色"],
        "missedCore": ["钢卷.卷重"],
    }


def test_hierarchy_counts_child_parent_pairs_in_their_direction() -> None:
    proposals = [
        create("entity_type", "new:Equipment", "设备"),
        create("entity_type", "new:Converter", "转炉", parentRef="new:Equipment"),
        create("entity_type", "new:Coil", "钢卷"),
        create("entity_type", "new:Heat", "炉次", parentRef="new:Coil"),
    ]
    parents: dict[UUID, UUID] = {}
    known = merged(proposals, parents=parents)
    result = score(known, EXPECTED_MORE, parents)["hierarchy"]
    assert result == {
        "predicted": 2,
        "precision": 0.5,
        "recall": 1.0,
        "unmatched": ["炉次 → 钢卷"],
        "missedCore": [],
    }

    flipped = {parent: child for child, parent in parents.items()}
    upside_down = score(known, EXPECTED_MORE, flipped)["hierarchy"]
    assert upside_down["precision"] == 0.0
    assert upside_down["missedCore"] == ["转炉 → 设备"]


def test_a_case_without_the_new_sections_scores_as_before() -> None:
    proposals = [
        create("entity_type", "new:Heat", "炉次"),
        create("entity_type", "new:Cast", "浇次", parentRef="new:Heat"),
        create("property", "new:weight", "重量", domainRef="new:Heat"),
    ]
    parents: dict[UUID, UUID] = {}
    result = score(merged(proposals, parents=parents), EXPECTED, parents)
    assert set(result) == {"entityTypes", "relations", "properties", "hierarchy"}
    assert result["properties"] == {"predicted": 1}
    assert result["hierarchy"] == {"predicted": 1}


# ---------------------------------------------------------------- whole runs and replay

_HEAT_ID = re.compile(r"^- ([0-9a-f-]{36}) \| 炉次", re.MULTILINE)


class ModelStandIn:
    """Answers like a model would: the second document reuses the first one's type by its id
    when it is shown one, and proposes it again otherwise."""

    def __init__(self) -> None:
        self.calls = 0

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
        self.calls += 1
        second = "b.md" in text.splitlines()[0]
        if purpose == "extract.terms":
            return schema.model_validate({"terms": []})
        shown = _HEAT_ID.findall(text)
        heat = shown[0] if second and shown else "new:Heat"
        if purpose == "extract.types":
            types = [_type(heat, "炉次", "Heat", "每个炉次有炉号")]
            if second:
                types.append(_type("new:Cast", "浇次", "CastingSequence", "一个浇次由若干炉次组成"))
            return schema.model_validate({"entity_types": types})
        relations = [_relation("new:Cast", heat, "一个浇次由若干炉次组成")] if second else []
        return schema.model_validate({"relations": relations, "properties": []})

    async def ping(self) -> bool:
        return True


def _type(ref: str, label: str, english: str, quote: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "label_zh": label,
        "label_en": english,
        "local_name": english,
        "definition_zh": None,
        "synonyms": [],
        "parent": None,
        "confidence": 0.9,
        "rationale": "",
        "quotes": [{"chunk": 0, "text": quote}],
    }


def _relation(domain: str, range_: str, quote: str) -> dict[str, Any]:
    return {
        "label_zh": "包含",
        "label_en": "includes",
        "local_name": "includesHeat",
        "domain": domain,
        "range": range_,
        "required": False,
        "multiple": True,
        "definition_zh": None,
        "confidence": 0.9,
        "rationale": "",
        "quotes": [{"chunk": 0, "text": quote}],
    }


CASE_FILES = {
    "docs/a.md": "# 炼钢\n\n每个炉次有炉号。\n".encode(),
    "docs/b.md": "# 连铸\n\n一个浇次由若干炉次组成。\n".encode(),
    "eval/expected.toml": (
        'entity_types = [{ names = ["炉次"], core = true }, { names = ["浇次"], core = true }]\n'
        'relations = [{ domain = "炉次", range = "浇次", core = true }]\n'
    ).encode(),
}
MODELS = ExtractionModels(standard="m-standard", reasoning="m-reasoning")


def _scores(result: dict[str, Any]) -> dict[str, Any]:
    """Without the usage, which differs between recording and replaying, also nested."""
    return {
        key: _scores(value) if key == "sameBaseline" else value
        for key, value in result.items()
        if key != "usage"
    }


async def test_a_replayed_run_scores_the_same_without_calling_the_model() -> None:
    model = ModelStandIn()
    recorder = ReplayGateway({}, model)
    recorded = await run_case(CASE_FILES, recorder, MODELS)
    assert recorded["relations"]["recall"] == 1.0
    # Terms, types and relations of each document, and two more: in the same-baseline scenario
    # b.md is shown no 炉次 of a.md, so its types and relations calls see another input.
    assert model.calls == 8
    assert recorded["usage"]["documents"]["docs/b.md"]["extract.types"]["calls"] == 1
    assert recorded["sameBaseline"]["usage"]["total"] == {
        "calls": 2,
        "replayed": 4,
        "seconds": recorded["sameBaseline"]["usage"]["total"]["seconds"],
        "inputTokens": 0,
        "outputTokens": 0,
    }

    recordings = load_recordings(text for _, text in recorder.recording_files())
    replayed = await run_case(CASE_FILES, ReplayGateway(recordings, None), MODELS)

    assert _scores(replayed) == _scores(recorded)
    assert replayed["usage"]["total"]["calls"] == 0
    assert replayed["usage"]["total"]["replayed"] == 6


async def test_the_same_baseline_scenario_merges_what_documents_proposed_twice() -> None:
    result = await run_case(CASE_FILES, ReplayGateway({}, ModelStandIn()), MODELS)

    same = result["sameBaseline"]
    # Both documents proposed 炉次; merging the second change set puts it into the first one's.
    assert same["entityTypes"]["predicted"] == 2
    assert same["relations"]["recall"] == 1.0
    assert same["merge"] == {
        "review": "acceptAll",
        "skipped": 0,
        "skippedByCode": {},
        "duplicateRelations": 0,
        "duplicateTypeGroups": {
            "total": 0,
            "sameMainName": 0,
            "marked": 0,
            "unmarked": 0,
            "groups": [],
        },
    }
    assert same["proposals"] == result["proposals"] + 1  # b.md proposes 炉次 once more


async def test_the_same_baseline_scenario_can_be_left_out() -> None:
    model = ModelStandIn()
    result = await run_case(CASE_FILES, ReplayGateway({}, model), MODELS, ["sequential"])
    assert "sameBaseline" not in result
    assert model.calls == 6
    with pytest.raises(ValueError, match="sequential"):
        await run_case(CASE_FILES, ReplayGateway({}, model), MODELS, ["sameBaseline"])


async def test_a_case_without_answers_is_run_but_not_scored_and_can_be_scored_later() -> None:
    unanswered = {path: data for path, data in CASE_FILES.items() if path.startswith("docs/")}
    result = await run_case(unanswered, ReplayGateway({}, ModelStandIn()), MODELS)

    assert result["scored"] is False
    assert result["entityTypes"] == {"predicted": 2}
    assert result["relations"] == {"predicted": 1}
    assert result["usage"]["total"]["calls"] == 6

    expected = tomllib.loads(CASE_FILES["eval/expected.toml"].decode())
    parents = {UUID(c): UUID(p) for c, p in result["parents"].items()}
    later = score(load_elements(result["elements"]), expected, parents)
    scored = await run_case(CASE_FILES, ReplayGateway({}, ModelStandIn()), MODELS)
    assert scored["scored"] is True
    assert {key: scored[key] for key in later} == later


class FailsAfter(ModelStandIn):
    """A model that answers `good` calls, then fails as a provider outage would."""

    def __init__(self, good: int) -> None:
        super().__init__()
        self.good = good

    async def structured[T: BaseModel](self, **call: Any) -> T:
        if self.calls >= self.good:
            self.calls += 1
            raise AiUnavailableError("Model call failed: InternalServerError", retryable=False)
        return await super().structured(**call)


def _bundle(files: dict[str, bytes], **extra: Any) -> dict[str, Any]:
    encoded = {path: base64.b64encode(data).decode() for path, data in files.items()}
    return {"files": encoded, "mode": "record", **extra}


def test_a_failed_run_still_returns_the_calls_it_paid_for() -> None:
    output, code = evaluate(_bundle(CASE_FILES), FailsAfter(good=2))
    assert code == 1
    assert output["error"] == "AiUnavailableError: Model call failed: InternalServerError"
    names = [file["name"] for file in output["files"]]
    assert len(names) == 3  # two recordings and the models
    assert names[-1] == "models.json"
    models = json.loads(output["files"][-1]["content"])["models"]
    assert models == {"standard": Settings().ai_model, "reasoning": Settings().ai_reasoning_model}


def test_a_run_that_recorded_nothing_leaves_the_models_file_alone() -> None:
    output, code = evaluate(_bundle(CASE_FILES), FailsAfter(good=0))
    assert code == 1
    assert output["files"] == []


def test_malformed_answers_fail_before_any_model_call() -> None:
    model = ModelStandIn()
    wrong_child = 'hierarchy = [{ child = "炉", parent = "浇次", core = true }]\n'
    answers = CASE_FILES["eval/expected.toml"] + wrong_child.encode()
    output, code = evaluate(_bundle({**CASE_FILES, "eval/expected.toml": answers}), model)
    assert code == 1
    assert "hierarchy[0].child" in output["error"]
    assert model.calls == 0


def test_answers_are_checked_for_every_field_they_need() -> None:
    good: dict[str, Any] = tomllib.loads(CASE_FILES["eval/expected.toml"].decode())
    check_expected(good)
    with pytest.raises(ExpectedError, match="relations"):
        check_expected({"entity_types": good["entity_types"]})
    with pytest.raises(ExpectedError, match=r"entity_types\[0\]"):
        check_expected({**good, "entity_types": [{"names": ["炉次"]}]})
    with pytest.raises(ExpectedError, match=r"properties\[0\] needs names"):
        check_expected({**good, "properties": [{"domain": "炉次", "core": True}]})
    # a string would be read character by character
    with pytest.raises(ExpectedError, match=r"entity_types\[0\] needs names \(a list\)"):
        check_expected({**good, "entity_types": [{"names": "炉次", "core": True}]})
    # score divides by the number of core entries
    with pytest.raises(ExpectedError, match="relations needs at least one core entry"):
        check_expected({**good, "relations": [{**good["relations"][0], "core": False}]})
    with pytest.raises(ExpectedError, match="not valid TOML"):
        parse_expected("entity_types = [")


def test_sections_without_a_denominator_score_none() -> None:
    expected = {
        **EXPECTED_MORE,
        "hierarchy": [{"child": "转炉", "parent": "设备", "core": False}],
    }
    result = score(merged([create("entity_type", "new:Heat", "炉次")]), expected, {})
    assert result["properties"]["precision"] is None  # nothing predicted
    assert result["hierarchy"]["recall"] is None  # no core pair


async def test_replay_only_fails_on_the_first_call_it_has_no_recording_for() -> None:
    recorder = ReplayGateway({}, ModelStandIn())
    await run_case({**CASE_FILES, "docs/b.md": b"# x\n\nother text\n"}, recorder, MODELS)
    recordings = load_recordings(text for _, text in recorder.recording_files())
    with pytest.raises(ReplayMissError, match=r"docs/b\.md.*extract\.terms"):
        await run_case(CASE_FILES, ReplayGateway(recordings, None), MODELS)
