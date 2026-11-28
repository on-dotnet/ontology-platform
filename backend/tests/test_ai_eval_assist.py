"""Score advisory reviews against the same unmerged proposals as the oracle."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Literal
from uuid import UUID

import pytest
from pydantic import BaseModel

from ontology_platform.modules.ai import eval as evaluation
from ontology_platform.modules.ai import replay, schemas
from ontology_platform.modules.ai.eval import OracleReviewer, WorkingVersion, item_id, run_case
from ontology_platform.modules.ai.extraction import (
    KnownElement,
    Proposal,
    ProposedEvidence,
    ProposedMatch,
)
from ontology_platform.modules.ai.gateway import (
    AiInvalidOutputError,
    AiNotConfiguredError,
    AiUnavailableError,
)
from ontology_platform.modules.ai.replay import ReplayGateway, ReplayMissError, load_recordings
from ontology_platform.modules.ontology.review_context import item_fingerprint
from ontology_platform.modules.ontology.service import RecordedItem
from test_ai_eval import CASE_FILES, MODELS, ModelStandIn, _bundle, _type, create

EXPECTED = {
    "entity_types": [{"names": ["Heat", "Melt"], "core": True}],
    "relations": [{"domain": "Heat", "range": "Heat", "core": True}],
}
FILES = {
    "docs/a.md": b"# Types\n\nMelt and Noise appear in this document.\n",
    "eval/expected.toml": (
        b'entity_types = [{ names = ["Heat", "Melt"], core = true }]\n'
        b'relations = [{ domain = "Heat", range = "Heat", core = true }]\n'
    ),
}


def _answer(
    label: str,
    seq: int,
    suggestion: schemas.AssistSuggestion | None = None,
    *,
    rename: schemas.AssistRename | None = None,
    risks: Sequence[schemas.AssistRisk] = (),
) -> schemas.AssistItem:
    return schemas.AssistItem(
        item_id=item_id(label, seq),
        stale=False,
        risks=list(risks),
        suggestion=suggestion,
        reason=None,
        rename=rename,
    )


def _step(
    label: str,
    proposals: Sequence[Proposal],
    answers: Sequence[schemas.AssistItem],
    status: Literal["done", "partial", "failed"] = "done",
    *,
    expected: Mapping[str, Any] = EXPECTED,
) -> evaluation.AssistStep:
    _, decisions = OracleReviewer(expected).review(proposals, label, None)
    return evaluation.AssistStep(proposals, decisions, answers, status)


def test_reject_precision_and_recall_sum_counts_over_checked_items() -> None:
    unknown = create("entity_type", "new:Noise", "Noise")
    known = create("entity_type", "new:Melt", "Melt")
    first = _step("a", [unknown], [_answer("a", 1, "reject")])
    second = _step(
        "b",
        [known, unknown, unknown, unknown],
        [
            _answer("b", 1, "reject"),
            _answer("b", 2, "accept"),
            _answer("b", 3, "unsure"),
            _answer("b", 4),
        ],
        "partial",
    )
    failed = _step("c", [unknown], [], "failed")
    metrics = evaluation.assist_metrics([first, second, failed], EXPECTED)
    assert metrics["rejectPrecision"] == {"numerator": 1, "denominator": 2, "ratio": 0.5}
    assert metrics["rejectRecall"] == {"numerator": 1, "denominator": 3, "ratio": 0.333}
    assert (metrics["documents"], metrics["items"], metrics["aiChecked"]) == (3, 6, 4)
    assert metrics["statuses"] == {"done": 1, "partial": 1, "failed": 1}


def test_edit_hit_checks_canonical_name_and_group_membership() -> None:
    alias = create("entity_type", "new:Alias", "Batch", synonyms=[{"lang": "en", "text": "Melt"}])
    unknown = create("entity_type", "new:Noise", "Noise")
    step = _step(
        "a",
        [alias, alias, unknown],
        [
            _answer("a", 1, "edit", rename=schemas.AssistRename(label_en=" \uff28eat ")),
            _answer("a", 2, "edit", rename=schemas.AssistRename(label_zh="Melt")),
            _answer("a", 3, "edit", rename=schemas.AssistRename(label_zh="Heat")),
        ],
    )
    assert evaluation.assist_metrics([step], EXPECTED)["editHit"] == {
        "numerator": 1,
        "denominator": 3,
        "ratio": 0.333,
    }


def _duplicate(
    source: Literal["rule", "ai"], *, items: Sequence[UUID] = (), elements: Sequence[UUID] = ()
) -> schemas.AssistRisk:
    return schemas.AssistRisk(
        code="duplicate",
        source=source,
        detail="undecided_match" if source == "rule" else None,
        reason=None,
        related_item_ids=list(items),
        related_element_ids=list(elements),
        memory_entry_id=None,
    )


def test_local_name_only_matches_score_type_and_property_edits_and_duplicates() -> None:
    expected = {
        "entity_types": [{"names": ["炉次", "Heat"], "core": True}],
        "relations": [{"domain": "炉次", "range": "炉次", "core": True}],
        "properties": [{"domain": "炉次", "names": ["炉号", "heatNumber"], "core": True}],
    }
    heat = KnownElement(UUID(int=1), "entity_type", "Heat", "Existing batch")
    number = KnownElement(UUID(int=2), "property", "heatNumber", "Existing ID", domain_id=heat.id)
    proposals = [
        create("entity_type", "new:Heat", "批次", labelEn="Batch"),
        create("property", "new:heatNumber", "标识", labelEn="Identifier", domainRef="new:Heat"),
    ]
    answers = [
        _answer(
            "a",
            seq,
            "edit",
            rename=schemas.AssistRename(label_zh=canonical),
            risks=[_duplicate("ai", elements=[peer.id])],
        )
        for seq, canonical, peer in [(1, "炉次", heat), (2, "炉号", number)]
    ]
    step = _step("a", proposals, answers, expected=expected)
    metrics = evaluation.assist_metrics([step], expected, [heat, number])
    assert (
        metrics["editHit"]
        == metrics["duplicatePrecision"]
        == {
            "numerator": 2,
            "denominator": 2,
            "ratio": 1.0,
        }
    )
    assert metrics["rejectRecall"] == {"numerator": 0, "denominator": 2, "ratio": 0.0}


def test_duplicate_precision_scores_each_risk_and_its_source() -> None:
    known = KnownElement(UUID(int=1), "entity_type", "Batch", "Batch", synonyms=("Melt",))
    heat = create("entity_type", "new:Heat", "Heat")
    previous = _step("a", [heat], [_answer("a", 1, "accept")])
    melt = replace(
        create("entity_type", "new:Melt", "Melt"),
        match=ProposedMatch("possible", item_id=item_id("a", 1)),
    )
    noise = replace(
        create("entity_type", "new:Noise", "Noise"),
        match=ProposedMatch("possible", temp_ref="new:Melt"),
    )
    step = _step(
        "b",
        [melt, noise, heat],
        [
            _answer("b", 1, risks=[_duplicate("rule")]),
            _answer("b", 2, risks=[_duplicate("rule")]),
            _answer(
                "b",
                3,
                "accept",
                risks=[
                    _duplicate("ai", items=[item_id("b", 1), item_id("b", 2)]),
                    _duplicate("ai", elements=[known.id]),
                    _duplicate("ai", items=[item_id("b", 3)]),
                    _duplicate("ai"),
                ],
            ),
        ],
    )
    metrics = evaluation.assist_metrics([previous, step], EXPECTED, [known])
    assert metrics["duplicatePrecision"] == {"numerator": 3, "denominator": 6, "ratio": 0.5}
    assert metrics["duplicatePrecisionBySource"] == {
        "rule": {"numerator": 1, "denominator": 2, "ratio": 0.5},
        "ai": {"numerator": 2, "denominator": 4, "ratio": 0.5},
    }


def test_mixed_duplicate_targets_count_as_one_hit() -> None:
    expected = {
        **EXPECTED,
        "entity_types": [*EXPECTED["entity_types"], {"names": ["Coil"], "core": True}],
    }
    proposals = [create("entity_type", f"new:{name}", name) for name in ("Heat", "Coil", "Melt")]
    risk = _duplicate("ai", items=[item_id("a", 2), item_id("a", 3)])
    step = _step("a", proposals, [_answer("a", 1, risks=[risk])], expected=expected)
    metrics = evaluation.assist_metrics([step], expected)
    hit = {"numerator": 1, "denominator": 1, "ratio": 1.0}
    assert metrics["duplicatePrecision"] == metrics["duplicatePrecisionBySource"]["ai"] == hit


def test_relation_duplicate_risks_are_unscored_for_both_sources() -> None:
    heat = create("entity_type", "new:Heat", "Heat")
    melt = create("entity_type", "new:Melt", "Melt")
    ends = {"domainRef": "new:Heat", "rangeRef": "new:Melt"}
    links = [create("relation_type", f"new:{name}", name, **ends) for name in ("owns", "feeds")]
    answers = [
        _answer("a", 1, risks=[_duplicate("ai", items=[item_id("a", 2)])]),
        _answer("a", 3, risks=[_duplicate("rule"), _duplicate("ai", items=[item_id("a", 4)])]),
        _answer("a", 4, risks=[_duplicate("ai", items=[item_id("a", 3)])]),
    ]
    metrics = evaluation.assist_metrics([_step("a", [heat, melt, *links], answers)], EXPECTED)
    assert metrics["duplicateUnscored"] == 3
    hit = {"numerator": 1, "denominator": 1, "ratio": 1.0}
    assert metrics["duplicatePrecision"] == hit
    assert metrics["duplicatePrecisionBySource"] == {
        "rule": {"numerator": 0, "denominator": 0, "ratio": None},
        "ai": hit,
    }


def test_empty_assist_metrics_have_null_ratios() -> None:
    metrics = evaluation.assist_metrics([], EXPECTED)
    empty = {"numerator": 0, "denominator": 0, "ratio": None}
    for name in ("rejectPrecision", "rejectRecall", "editHit", "duplicatePrecision"):
        assert metrics[name] == empty
    assert metrics["duplicatePrecisionBySource"] == {"rule": empty, "ai": empty}
    assert metrics["statuses"] == {"done": 0, "partial": 0, "failed": 0}


def test_property_edit_and_duplicate_require_the_expected_domain() -> None:
    expected = {**EXPECTED, "properties": [{"domain": "Heat", "names": ["Number", "ID"]}]}
    proposals = [
        create("entity_type", "new:Melt", "Melt"),
        create("entity_type", "new:Noise", "Noise"),
        create("property", "new:id", "ID", domainRef="new:Melt"),
        create("property", "new:other", "ID", domainRef="new:Noise"),
    ]
    existing_type = KnownElement(UUID(int=1), "entity_type", "Heat", "Heat")
    existing_prop = KnownElement(
        UUID(int=2), "property", "number", "Number", domain_id=existing_type.id
    )
    answers = [
        _answer(
            "a",
            seq,
            "edit",
            rename=schemas.AssistRename(label_en="Number"),
            risks=[_duplicate("ai", elements=[existing_prop.id])],
        )
        for seq in (3, 4)
    ]
    step = _step("a", proposals, answers, expected=expected)
    metrics = evaluation.assist_metrics([step], expected, [existing_type, existing_prop])
    for key in ("editHit", "duplicatePrecision"):
        assert metrics[key] == {"numerator": 1, "denominator": 2, "ratio": 0.5}


def test_assist_scores_near_property_renames_and_duplicate_rejections() -> None:
    expected = {
        **EXPECTED,
        "properties": [
            {"domain": "Heat", "names": ["Number", "ID"]},
            {"domain": "Heat", "names": ["Mass"]},
        ],
    }
    proposals = [
        create("entity_type", "new:Melt", "Melt"),
        create("property", "new:Mass", "Batch number", domainRef="new:Melt"),
        create("property", "new:LongID", "Sample batch number", domainRef="new:Melt"),
        create("property", "new:Weight", "Batch mass", domainRef="new:Melt"),
    ]
    answers = [
        _answer("a", 2, "edit", rename=schemas.AssistRename(label_en="Number")),
        _answer("a", 3, "reject", risks=[_duplicate("ai", items=[item_id("a", 2)])]),
        _answer("a", 4, "reject"),
    ]
    metrics = evaluation.assist_metrics(
        [_step("a", proposals, answers, expected=expected)], expected
    )
    hit = {"numerator": 1, "denominator": 1, "ratio": 1.0}
    assert metrics["editHit"] == hit
    assert metrics["rejectRecall"] == hit
    assert metrics["rejectPrecision"] == {"numerator": 1, "denominator": 2, "ratio": 0.5}
    assert metrics["duplicatePrecision"] == hit


def test_context_uses_stored_fields_sequence_evidence_and_open_match_targets() -> None:
    version = WorkingVersion()
    parent = KnownElement(UUID(int=10), "entity_type", "Parent", "Parent")
    heat = KnownElement(
        UUID(int=11), "entity_type", "Heat", "Heat", definition_zh="Old", revision=3
    )
    version.elements.extend([parent, heat])
    version.parents[heat.id] = parent.id
    earlier = RecordedItem(item_id("a", 1), UUID(int=12), label_zh="Earlier")
    update = Proposal("update", "entity_type", {"definitionZh": "New"}, heat.id, target_revision=1)
    alias = replace(
        create("entity_type", "new:Melt", "Melt", parentRef=str(parent.id)),
        match=ProposedMatch("possible", item_id=earlier.id),
        flags=["possible_duplicate", "possible_duplicate"],
        evidence=[
            ProposedEvidence(UUID(int=2), "last", 0, 4),
            ProposedEvidence(UUID(int=1), "unlocated", None, None),
            ProposedEvidence(UUID(int=1), "Q" * 220, 0, 220),
        ],
    )
    another = replace(
        create("entity_type", "new:Other", "Other"),
        match=ProposedMatch("same", temp_ref="new:Melt"),
    )
    rel = create("relation_type", "new:links", "links", domainRef="new:Melt", rangeRef=str(heat.id))
    ctx, _ = evaluation.prepare_assist(
        "b", [update, alias, another, rel], version, {earlier.id: earlier}
    )
    assert [(i.id, i.seq, i.kind) for i in ctx.items] == [
        (item_id("b", i), i, p.kind) for i, p in enumerate([update, alias, another, rel], 1)
    ]
    changed, melt, other, link = ctx.items
    assert (changed.label_zh, changed.local_name, changed.definition) == ("Heat", "Heat", "New")
    assert changed.fingerprint == item_fingerprint(
        "entity_type", "update", heat.id, {"definitionZh": "New"}, None
    )
    assert changed.target_stale
    assert changed.kept_fields == ("definitionZh",)
    assert (melt.parent, melt.match_other_label, other.match_other_label) == (
        "Parent",
        "Earlier",
        "Melt",
    )
    assert melt.has_evidence
    assert melt.quotes == ("Q" * 200, "unlocated")
    assert melt.flags == ("possible_duplicate",)
    assert (link.domain, link.range) == ("new:Melt", "Heat")
    assert [(e.local_name, e.parent) for e in ctx.elements] == [
        ("Heat", "Parent"),
        ("Parent", None),
    ]
    assert ctx.rejected == ()


def test_oversized_model_fields_are_clipped_for_both_reviewers() -> None:
    long_name = "A" * 210
    proposal = create("entity_type", "new:Long", long_name)
    matched = replace(
        create("entity_type", "new:Other", "Other"),
        match=ProposedMatch("possible", temp_ref="new:Long"),
    )
    ctx, stored = evaluation.prepare_assist("a", [proposal, matched], WorkingVersion())
    assert proposal.fields["labelZh"] == long_name
    assert (
        stored[0].fields["labelZh"]
        == ctx.items[0].label_zh
        == ctx.items[1].match_other_label
        == long_name[:200]
    )
    assert ctx.items[0].fingerprint == item_fingerprint(
        "entity_type", "create", None, stored[0].fields, None
    )


class AssistModel(ModelStandIn):
    def __init__(self, *, second_batch_error: Exception | None = None) -> None:
        super().__init__()
        self.second_batch_error = second_batch_error
        self.purposes: list[str] = []
        self.assist_calls: list[tuple[str, str]] = []

    async def structured[T: BaseModel](
        self, *, purpose: str, model: str, text: str, schema: type[T], **kwargs: Any
    ) -> T:
        self.purposes.append(purpose)
        if purpose == "extract.types":
            self.calls += 1
            return schema.model_validate(
                {"entity_types": [_type(f"new:{name}", name, name) for name in ("Melt", "Noise")]}
            )
        if purpose == "review.assist":
            self.assist_calls.append((model, text))
            if self.second_batch_error is not None and len(self.assist_calls) == 2:
                raise self.second_batch_error
            items = [
                {
                    "ref": item["ref"],
                    "suggestion": "reject" if item["labelZh"] == "Noise" else "edit",
                    "rename": None if item["labelZh"] == "Noise" else {"labelEn": "Heat"},
                    "risks": [],
                    "reason": "test",
                }
                for item in json.loads(text.split("\n", 1)[1])["items"]
            ]
            return schema.model_validate({"summary": "review", "groups": [], "items": items})
        if purpose == "review.assist.summary":
            return schema.model_validate({"summary": "combined", "groups": []})
        return await super().structured(
            purpose=purpose, model=model, text=text, schema=schema, **kwargs
        )


@pytest.mark.parametrize(
    ("fields", "locale"),
    [
        (b"", "zh-CN"),
        (b'locale = "en"\n', "en"),
        (b'language = "en"\n', "en"),
        (b'locale = "zh-CN"\nlanguage = "en"\n', "zh-CN"),
    ],
    ids=["default", "locale", "language", "locale-first"],
)
async def test_same_baseline_assist_is_scored_and_replays_without_a_model(
    fields: bytes,
    locale: str,
) -> None:
    files = dict(FILES)
    files["eval/expected.toml"] += fields
    model = AssistModel()
    recorder = ReplayGateway({}, model)
    result = await run_case(files, recorder, MODELS, assist=True)
    metrics = result["sameBaseline"]["assist"]
    assert "assist" not in result
    [(used_model, prompt)] = model.assist_calls
    assert used_model == MODELS.standard
    assert prompt.splitlines()[0] == f"language: {locale}"
    assert (metrics["documents"], metrics["items"], metrics["aiChecked"]) == (1, 2, 2)
    assert metrics["statuses"] == {"done": 1, "partial": 0, "failed": 0}
    assert metrics["duplicateUnscored"] == 0
    for key in ("rejectPrecision", "rejectRecall", "editHit"):
        assert metrics[key] == {"numerator": 1, "denominator": 1, "ratio": 1.0}
    records = load_recordings(content for _, content in recorder.recording_files())
    replayed = await run_case(files, ReplayGateway(records, None), MODELS, assist=True)
    assert replayed["sameBaseline"]["assist"] == metrics
    stage = replayed["sameBaseline"]["usage"]["stages"]["review.assist"]
    assert (stage["calls"], stage["replayed"]) == (0, 1)
    extraction_only = {k: v for k, v in records.items() if v["purpose"] != "review.assist"}
    with pytest.raises(ReplayMissError, match=r"review\.assist"):
        await run_case(files, ReplayGateway(extraction_only, None), MODELS, assist=True)


@pytest.mark.parametrize(
    ("fields", "field", "value"),
    [
        (b'locale = "fr"\nlanguage = "en"\n', "locale", "fr"),
        (b'language = "en-US"\n', "language", "en-US"),
        (b'locale = ["en"]\n', "locale", "['en']"),
    ],
    ids=["locale", "language", "wrong-type"],
)
async def test_invalid_assist_locale_fails_before_any_model_call(
    fields: bytes, field: str, value: str
) -> None:
    files = dict(FILES)
    files["eval/expected.toml"] += fields
    model = AssistModel()
    with pytest.raises(ValueError, match=field) as exc:
        await run_case(files, ReplayGateway({}, model), MODELS, assist=True)
    assert value in str(exc.value)
    assert model.purposes == []


async def test_second_document_assist_sees_pending_items_against_empty_baseline() -> None:
    files = {**FILES, "docs/b.md": b"# Reuse\n\nNoise and Melt recur in another document.\n"}
    model = AssistModel()
    result = await run_case(files, ReplayGateway({}, model), MODELS, assist=True)
    assert result["sameBaseline"]["assist"]["documents"] == 2
    first, second = (json.loads(prompt.split("\n", 1)[1]) for _, prompt in model.assist_calls)
    assert first["elements"] == second["elements"] == []
    assert {i["labelZh"]: i["matchOtherLabel"] for i in first["items"]} == {
        "Melt": None,
        "Noise": None,
    }
    assert {i["labelZh"]: i["matchOtherLabel"] for i in second["items"]} == {
        "Melt": "Melt",
        "Noise": "Noise",
    }


def test_bundle_records_and_replays_both_batches_and_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OP_REVIEW_ASSIST_BATCH", "1")
    lines: list[dict[str, Any]] = []
    output, code = evaluation.evaluate(_bundle(FILES, assist=True), AssistModel(), lines.append)
    assert code == 0
    records = [line["content"] for line in lines if line["name"] != "models.json"]
    replayed, code = evaluation.evaluate(
        _bundle(FILES, mode="replay", assist=True, recordings=records, manifest=lines[0]["content"])
    )
    assert code == 0
    same = json.loads(replayed["result"])["sameBaseline"]
    assert same["assist"] == json.loads(output["result"])["sameBaseline"]["assist"]
    stages = same["usage"]["stages"]
    assert (stages["review.assist"]["replayed"], stages["review.assist.summary"]["replayed"]) == (
        2,
        1,
    )
    assert same["usage"]["total"]["calls"] == 0


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (None, "done"),
        (TimeoutError(), "partial"),
        (AiUnavailableError("test", retryable=False), "partial"),
        (AiInvalidOutputError("test", retryable=False), "partial"),
    ],
    ids=["cap", "timeout", "unavailable", "invalid_output"],
)
async def test_unchecked_rejections_do_not_enter_recall(
    error: Exception | None, status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_REVIEW_ASSIST_BATCH", "1")
    if error is None:
        monkeypatch.setenv("OP_REVIEW_ASSIST_ITEMS_MAX", "1")
    model = AssistModel(second_batch_error=error)
    result = await run_case(FILES, ReplayGateway({}, model), MODELS, assist=True)
    metrics = result["sameBaseline"]["assist"]
    assert metrics["statuses"][status] == 1
    assert (metrics["items"], metrics["aiChecked"]) == (2, 1)
    assert metrics["editHit"] == {"numerator": 1, "denominator": 1, "ratio": 1.0}
    assert metrics["rejectRecall"] == {"numerator": 0, "denominator": 0, "ratio": None}


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("unexpected review failure"),
        KeyError("internal lookup"),
        AiNotConfiguredError(),
    ],
    ids=["runtime", "lookup", "configuration"],
)
async def test_second_batch_internal_error_propagates(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_REVIEW_ASSIST_BATCH", "1")
    model = AssistModel(second_batch_error=error)
    with pytest.raises(type(error)) as exc:
        await run_case(FILES, ReplayGateway({}, model), MODELS, assist=True)
    assert exc.value is error
    assert model.purposes.count("review.assist") == 2


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("review.assist", OSError("cannot write assist recording")),
        ("review.assist.summary", ValueError("summary recording stream is closed")),
    ],
    ids=["batch", "summary"],
)
def test_assist_recording_write_error_fails_evaluation(
    stage: str, error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OP_REVIEW_ASSIST_BATCH", "1")
    written: list[str] = []

    def write(line: dict[str, Any]) -> None:
        if line["name"] != "models.json":
            purpose = json.loads(line["content"])["purpose"]
            if purpose == stage:
                raise error
            written.append(purpose)

    output, code = evaluation.evaluate(_bundle(FILES, assist=True), AssistModel(), write)
    assert "extract.types" in written
    assert code == 1
    assert output == {"type": "error", "error": type(error).__name__}


async def test_assist_false_preserves_output_and_recording_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = SimpleNamespace(monotonic=lambda: 0.0)
    monkeypatch.setattr(evaluation, "time", clock)
    monkeypatch.setattr(replay, "time", clock)
    old = ReplayGateway({}, ModelStandIn())
    default = await run_case(CASE_FILES, old, MODELS)
    legacy = json.dumps([default, old.recording_files()], ensure_ascii=False).encode()
    # Captured on f75f5826 with this model and frozen clock, including every recording key.
    assert hashlib.sha256(legacy).hexdigest() == (
        "5993bc48e89b325826300d70f10e56607958842778139bdf08d36db2e9672945"
    )
    current = ReplayGateway({}, ModelStandIn())
    disabled = await run_case(CASE_FILES, current, MODELS, assist=False)
    assert "assist" not in default["sameBaseline"]
    assert json.dumps(default, ensure_ascii=False) == json.dumps(disabled, ensure_ascii=False)
    assert old.recording_files() == current.recording_files()


@pytest.mark.parametrize("options", [{}, {"assist": False}], ids=["omitted", "false"])
def test_disabled_bundle_never_calls_assist(options: dict[str, bool]) -> None:
    files = dict(FILES)
    files["eval/expected.toml"] += b'locale = "fr"\n'
    model = AssistModel()
    output, code = evaluation.evaluate(_bundle(files, **options), model)
    assert code == 0
    assert "assist" not in json.loads(output["result"])["sameBaseline"]
    assert "extract.types" in model.purposes
    assert {"review.assist", "review.assist.summary"}.isdisjoint(model.purposes)


@pytest.mark.parametrize("value", [1, "true", None])
def test_bundle_assist_must_be_boolean(value: object) -> None:
    with pytest.raises(ValueError, match="assist"):
        evaluation.evaluate(_bundle(FILES, assist=value), AssistModel())


@pytest.mark.parametrize("scenarios", [[], ["sequential"]])
def test_bundle_assist_requires_same_baseline(scenarios: list[str]) -> None:
    with pytest.raises(ValueError, match="sameBaseline"):
        evaluation.evaluate(_bundle(FILES, assist=True, scenarios=scenarios), AssistModel())


def test_bundle_assist_needs_answers_before_identification() -> None:
    model = AssistModel()
    output, code = evaluation.evaluate(_bundle({"docs/a.md": b"sample"}, assist=True), model)
    assert code == 1
    assert "expected.toml" in output["error"]
    assert model.calls == 0
