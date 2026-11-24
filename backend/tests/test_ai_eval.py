"""Scoring of the extraction evaluation: synonyms count, direction does not, only core recalls."""

import json
from uuid import uuid4

from ontology_platform.modules.ai.eval import accept, dump_elements, load_elements, score
from ontology_platform.modules.ai.extraction import KnownElement, Proposal

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


def test_accept_then_score() -> None:
    proposals = [
        create("entity_type", "new:Heat", "冶炼炉次", synonyms=[{"lang": "en", "text": "Heat"}]),
        create("entity_type", "new:Cast", "浇次"),
        create("entity_type", "new:Crane", "行车"),  # not expected: lowers precision
        create(
            "relation_type", "new:inSequence", "属于", domainRef="new:Cast", rangeRef="new:Heat"
        ),
    ]
    known = accept([], proposals)
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
    [merged] = accept([element], [update])
    assert merged.synonyms == ("钢卷",)
    assert score([merged], EXPECTED)["entityTypes"]["missedCore"] == ["炉次", "浇次"]


def test_unmatched_relations_are_listed_by_their_ends() -> None:
    proposals = [
        create("entity_type", "new:Heat", "炉次"),
        create("entity_type", "new:Crane", "行车"),
        create("relation_type", "new:lifts", "吊运", domainRef="new:Crane", rangeRef="new:Heat"),
    ]
    result = score(accept([], proposals), EXPECTED)
    assert result["relations"]["unmatched"] == ["行车 → 炉次（吊运）"]


def test_saved_elements_score_the_same_after_loading() -> None:
    proposals = [
        create("entity_type", "new:Heat", "冶炼炉次", synonyms=[{"lang": "en", "text": "Heat"}]),
        create("entity_type", "new:Cast", "浇次"),
        create(
            "relation_type", "new:inSequence", "属于", domainRef="new:Cast", rangeRef="new:Heat"
        ),
    ]
    known = accept([], proposals)
    saved = json.loads(json.dumps(dump_elements(known)))
    assert load_elements(saved) == known
    assert score(load_elements(saved), EXPECTED) == score(known, EXPECTED)
