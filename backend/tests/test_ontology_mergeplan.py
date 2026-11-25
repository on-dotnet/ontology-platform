"""The merge plan of an AI-extracted change set: a pure function of items and elements."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from ontology_platform.modules.ai.extraction import normalize
from ontology_platform.modules.ontology.mergeplan import (
    PlanElement,
    PlanItem,
    PlanMatch,
    PlanMatchedBy,
    Resolution,
    changes_the_merge,
    name_key,
    plan_merge,
    plan_token,
)
from ontology_platform.modules.ontology.schemas import ElementFields

BASE = "https://example.org/ontology/steel#"
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def existing(kind: str, local_name: str, label_zh: str | None, **values: Any) -> PlanElement:
    data: dict[str, Any] = {
        "id": uuid4(),
        "kind": kind,
        "status": "active",
        "local_name": local_name,
        "iri": BASE + local_name,
        "label_zh": label_zh,
        "label_en": None,
        "definition_zh": None,
        "definition_en": None,
        "parent_id": None,
        "domain_id": None,
        "range_id": None,
        "datatype": None,
        "unit": None,
        "required": False,
        "multiple": False,
        "revision": 1,
        "created_at": T0,
    }
    data.update(values)
    return PlanElement(**data)


def proposed(seq: int, op: str, kind: str, **values: Any) -> PlanItem:
    meta = {
        key: values.pop(key)
        for key in ("decision", "temp_ref", "target", "target_revision", "edited")
        if key in values
    }
    target: PlanElement | None = meta.get("target")
    return PlanItem(
        id=uuid4(),
        seq=seq,
        op=op,
        kind=kind,
        decision=meta.get("decision", "accepted"),
        temp_ref=meta.get("temp_ref"),
        target_element_id=target.id if target else None,
        target_revision=meta.get("target_revision", target.revision if target else None),
        fields=ElementFields(**values),
        edited=meta.get("edited", False),
    )


def new_type(seq: int, local_name: str, label_zh: str, **values: Any) -> PlanItem:
    values.setdefault("temp_ref", f"new:{local_name}")
    return proposed(
        seq, "create", "entity_type", local_name=local_name, label_zh=label_zh, **values
    )


def plan(items: list[PlanItem], elements: list[PlanElement]) -> dict[UUID, Resolution]:
    return plan_merge(items, elements, base_iri=BASE)


def modes(items: list[PlanItem], elements: list[PlanElement]) -> list[str | None]:
    result = plan(items, elements)
    return [result[item.id].mode if item.id in result else None for item in items]


def test_a_type_named_like_an_active_type_goes_into_it() -> None:
    converter = existing("entity_type", "Converter", "转炉", revision=4)
    # Another local name, full-width letters and spaces: still the same name.
    item = new_type(1, "BofConverter", " 转 炉 ")

    result = plan([item], [converter])

    assert result[item.id] == Resolution("into", element_id=converter.id, element_revision=4)


def test_the_oldest_of_several_types_of_the_name_is_the_one() -> None:
    later = existing("entity_type", "Converter2", "转炉", created_at=T0 + timedelta(days=1))
    first = existing("entity_type", "Converter", "转炉")
    item = new_type(1, "Bof", "转炉")

    assert plan([item], [later, first])[item.id].element_id == first.id


def test_a_deleted_type_is_no_target_but_holds_its_local_name() -> None:
    gone = existing("entity_type", "Converter", "转炉", status="deprecated")
    item = new_type(1, "Converter", "转炉")

    assert plan([item], [gone])[item.id] == Resolution("rename", local_name="Converter2")


def test_a_taken_local_name_gets_a_number_that_no_other_item_asked_for() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    items = [
        new_type(1, "Converter", "变流器"),
        new_type(2, "Converter2", "电炉"),
        new_type(3, "Converter", "变频器"),
    ]

    result = plan(items, [converter])

    assert [result[item.id] for item in items] == [
        Resolution("rename", local_name="Converter3"),
        Resolution("create"),
        Resolution("rename", local_name="Converter4"),
    ]


def test_an_iri_an_imported_element_holds_counts_as_taken() -> None:
    imported = existing("entity_type", "Furnace", "炉", iri=BASE + "Ladle")
    item = new_type(1, "Ladle", "钢包")

    assert plan([item], [imported])[item.id] == Resolution("rename", local_name="Ladle2")


def test_english_labels_decide_only_where_a_chinese_one_is_missing() -> None:
    imported = existing("entity_type", "Ladle", None, label_en="Steel ladle")
    unlabelled = existing("entity_type", "Tundish", None)
    converter = existing("entity_type", "Converter", "转炉", label_en="Converter")
    items = [
        new_type(1, "SteelLadle", "钢包", label_en="steel ladle"),
        # An element without labels goes by its local name.
        new_type(2, "TundishVessel", "中间包", label_en="Tundish"),
        # Both have Chinese labels, and they differ: the shared English one does not decide.
        new_type(3, "FrequencyConverter", "变频器", label_en="Converter"),
    ]

    result = plan(items, [imported, unlabelled, converter])

    assert [result[item.id].element_id for item in items] == [imported.id, unlabelled.id, None]


def test_relations_and_properties_follow_the_type_they_hang_on() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    ladle = existing("entity_type", "Ladle", "钢包")
    heat = existing("entity_type", "Heat", "炉次")
    taps = existing(
        "relation_type", "tapsInto", "出钢至", domain_id=converter.id, range_id=ladle.id
    )
    capacity = existing(
        "property", "capacity", "公称容量", domain_id=converter.id, datatype="decimal", unit="t"
    )
    items = [
        new_type(1, "Bof", "转炉"),
        proposed(
            2,
            "create",
            "relation_type",
            local_name="pours",
            label_zh="出钢至",
            domain_ref="new:Bof",
            range_ref=str(ladle.id),
        ),
        # The same label and domain, another range: another relation.
        proposed(
            3,
            "create",
            "relation_type",
            local_name="poursFor",
            label_zh="出钢至",
            domain_ref="new:Bof",
            range_ref=str(heat.id),
        ),
        proposed(
            4,
            "create",
            "property",
            local_name="nominalCapacity",
            label_zh="公称容量",
            domain_ref="new:Bof",
            datatype="integer",
            unit="吨",
        ),
        # The same label on another type: another property, and its local name is free.
        proposed(
            5,
            "create",
            "property",
            local_name="ladleCapacity",
            label_zh="公称容量",
            domain_ref=str(ladle.id),
            datatype="decimal",
        ),
    ]

    result = plan(items, [converter, ladle, heat, taps, capacity])

    assert [(result[i.id].mode, result[i.id].element_id) for i in items] == [
        ("into", converter.id),
        ("into", taps.id),
        ("create", None),
        ("into", capacity.id),
        ("create", None),
    ]
    # The existing property keeps its datatype and unit; the reviewer is shown that they differ.
    assert result[items[3].id].kept_fields == ("datatype", "unit")


def test_what_hangs_on_a_new_type_is_new() -> None:
    ladle = existing("entity_type", "Ladle", "钢包")
    other = existing("entity_type", "Crane", "行车")
    lifts = existing("relation_type", "lifts", "吊运", domain_id=other.id, range_id=ladle.id)
    items = [
        new_type(1, "Hoist", "天车"),
        proposed(
            2,
            "create",
            "relation_type",
            local_name="lifts",
            label_zh="吊运",
            domain_ref="new:Hoist",
            range_ref=str(ladle.id),
        ),
    ]

    result = plan(items, [ladle, other, lifts])

    # Not the existing 吊运 (its domain is another type), and that one holds the local name.
    assert result[items[1].id] == Resolution("rename", local_name="lifts2")


def test_rejected_items_are_not_planned_and_nothing_follows_them() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    ladle = existing("entity_type", "Ladle", "钢包")
    taps = existing(
        "relation_type", "tapsInto", "出钢至", domain_id=converter.id, range_id=ladle.id
    )
    items = [
        new_type(1, "Bof", "转炉", decision="rejected"),
        proposed(
            2,
            "create",
            "relation_type",
            local_name="pours",
            label_zh="出钢至",
            domain_ref="new:Bof",
            range_ref=str(ladle.id),
        ),
    ]

    assert modes(items, [converter, ladle, taps]) == [None, "create"]


def test_an_element_keeps_what_it_has_and_the_plan_says_which_fields() -> None:
    parent = existing("entity_type", "Equipment", "设备")
    converter = existing(
        "entity_type",
        "Converter",
        "转炉",
        label_en="Converter",
        definition_zh="炼钢设备。",
        parent_id=parent.id,
    )
    furnace = existing("entity_type", "Furnace", "炉")
    item = new_type(
        1,
        "Bof",
        "转炉",
        label_en="Basic oxygen furnace",
        definition_zh="吹氧炼钢的炉子。",
        parent_ref=str(furnace.id),
    )
    same = new_type(2, "Bof2", "转炉", definition_zh="炼钢设备。", parent_ref=str(parent.id))

    result = plan([item, same], [parent, converter, furnace])

    assert result[item.id].kept_fields == ("labelEn", "definitionZh", "parentRef")
    assert result[same.id].kept_fields == ()


def test_updates_that_only_add_are_planned_whatever_the_revision() -> None:
    grade = existing("entity_type", "SteelGrade", "钢种", definition_zh="钢的牌号。", revision=5)
    gone = existing("entity_type", "Gone", "废弃", status="deprecated")
    synonyms = [{"lang": "zh", "text": "牌号"}]
    items = [
        proposed(1, "update", "entity_type", target=grade, target_revision=2, synonyms=synonyms),
        proposed(2, "update", "entity_type", target=grade, definition_zh="按成分划分的牌号。"),
        # Replaces a value: the optimistic lock stays.
        proposed(3, "update", "entity_type", target=grade, label_en="Steel grade"),
        # The reviewer's edit is theirs, whatever it says.
        proposed(4, "update", "entity_type", target=grade, synonyms=synonyms, edited=True),
        proposed(5, "update", "entity_type", target=gone, synonyms=synonyms),
        # Restored by another change set meanwhile: only the additions are left to apply.
        proposed(6, "restore", "entity_type", target=grade, target_revision=2, synonyms=synonyms),
        proposed(7, "restore", "entity_type", target=gone, synonyms=synonyms),
    ]

    result = plan(items, [grade, gone])

    assert modes(items, [grade, gone]) == ["update", "update", None, None, None, "update", None]
    assert result[items[0].id] == Resolution("update", element_id=grade.id, element_revision=5)
    assert result[items[1].id].kept_fields == ("definitionZh",)


def test_the_token_follows_the_plan_and_the_elements_it_touches() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    ladle = existing("entity_type", "Ladle", "钢包")
    items = [new_type(1, "Bof", "转炉"), new_type(2, "Tundish", "中间包")]

    def token(elements: list[PlanElement], given: list[PlanItem] = items) -> str:
        return plan_token(given, elements, plan(given, elements))

    before = token([converter, ladle])
    changed_target = existing(
        "entity_type", "Converter", "转炉", id=converter.id, revision=2, definition_zh="炼钢设备。"
    )
    changed_other = existing("entity_type", "Ladle", "钢包", id=ladle.id, revision=2)
    rejected = [
        PlanItem(
            id=items[0].id,
            seq=1,
            op="create",
            kind="entity_type",
            decision="rejected",
            temp_ref="new:Bof",
            target_element_id=None,
            target_revision=None,
            fields=items[0].fields,
            edited=False,
        ),
        items[1],
    ]

    assert token([converter, ladle]) == before
    assert token([changed_target, ladle]) != before
    assert token([converter, changed_other]) == before
    # Nothing left that depends on the working version: the token of an empty plan.
    assert token([converter, ladle], rejected) == plan_token([], [], {}) != before


def test_a_restore_is_in_the_token_with_the_state_of_its_target() -> None:
    gone = existing("entity_type", "Gone", "废弃", status="deprecated")
    item = proposed(1, "restore", "entity_type", target=gone)
    moved = existing("entity_type", "Gone", "废弃", status="deprecated", id=gone.id, revision=2)

    assert plan([item], [gone]) == {}
    assert plan_token([item], [gone], {}) != plan_token([item], [moved], {})


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (lambda t: [new_type(1, "Slab", "板坯")], False),
        (lambda t: [new_type(1, "Bof", "钢种")], True),  # into
        (lambda t: [new_type(1, "SteelGrade", "牌号")], True),  # rename
        (
            lambda t: [
                proposed(
                    1, "update", "entity_type", target=t, synonyms=[{"lang": "zh", "text": "x"}]
                )
            ],
            False,  # the target is as it was proposed against: applied as it always was
        ),
        (
            lambda t: [
                proposed(
                    1,
                    "update",
                    "entity_type",
                    target=t,
                    target_revision=1,
                    synonyms=[{"lang": "zh", "text": "x"}],
                )
            ],
            True,  # used to be skipped as stale
        ),
        (
            lambda t: [
                proposed(1, "update", "entity_type", target=t, target_revision=1, label_en="G")
            ],
            False,  # still skipped as stale
        ),
        (
            lambda t: [
                proposed(
                    1, "restore", "entity_type", target=t, synonyms=[{"lang": "zh", "text": "x"}]
                )
            ],
            True,  # used to be an invalid item
        ),
    ],
    ids=["create", "into", "rename", "update", "moved-update", "replacing-update", "restore"],
)
def test_only_plans_that_change_what_a_merge_does_need_the_token(
    build: Any, expected: bool
) -> None:
    grade = existing("entity_type", "SteelGrade", "钢种", revision=3)
    items = build(grade)

    assert changes_the_merge(items, plan(items, [grade])) is expected


@pytest.mark.parametrize("text", ["转 炉", "Ｃｏｎｖｅｒｔｅｒ　ＢＯＦ", "LF 精炼炉\n", "ℂ", ""])  # noqa: RUF001
def test_names_are_compared_as_the_extraction_compares_them(text: str) -> None:
    assert name_key(text) == normalize(text)


def test_a_restore_without_fields_of_a_type_restored_meanwhile_is_planned() -> None:
    restored = existing("entity_type", "Converter", "转炉", revision=3)
    gone = existing("entity_type", "Gone", "废弃", status="deprecated")
    items = [
        proposed(1, "restore", "entity_type", target=restored, target_revision=1),
        proposed(2, "restore", "entity_type", target=gone),
    ]

    result = plan(items, [restored, gone])

    assert result == {items[0].id: Resolution("update", element_id=restored.id, element_revision=3)}
    assert changes_the_merge(items, result) is True


def test_a_renamed_item_leaves_the_names_other_creations_asked_for() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    items = [
        new_type(1, "Converter", "变流器"),
        # Not planned: a constraint, and an item with an IRI of its own.
        proposed(
            2,
            "create",
            "constraint",
            local_name="Converter2",
            domain_ref=str(converter.id),
            rules=[],
        ),
        new_type(3, "Converter3", "变频器", iri="https://example.org/other#Converter3"),
    ]

    result = plan(items, [converter])

    assert result[items[0].id] == Resolution("rename", local_name="Converter4")
    assert items[1].id not in result
    assert result[items[2].id] == Resolution("create")


def test_no_rename_beyond_the_longest_local_name() -> None:
    longest = "A" * 128
    taken = existing("entity_type", longest, "甲")
    item = new_type(1, longest, "乙")

    assert plan([item], [taken])[item.id] == Resolution("create")


def test_a_parent_that_would_close_a_loop_is_named_among_the_kept_fields() -> None:
    converter = existing("entity_type", "Converter", "转炉")
    bof = existing("entity_type", "Bof", "氧气顶吹转炉", parent_id=converter.id)
    item = new_type(1, "Converter2", "转炉", parent_ref=str(bof.id))

    assert plan([item], [converter, bof])[item.id].kept_fields == ("parentRef",)


# ---------- alignment records (spec 004, 5.3 and 5.5; PR 3) ----------


def recorded(item: PlanItem, **values: Any) -> PlanItem:
    """`item` with its alignment record and the reviewer's decision on it."""

    decision = values.pop("decision", None)
    matched_by = values.pop("matched_by", ())
    match = PlanMatch(**values) if values else None
    return replace(item, match=match, match_decision=decision, matched_by=matched_by)


@pytest.mark.parametrize(
    ("kind", "decision", "other", "goes_into"),
    [
        ("same", None, None, True),  # the model judged it the same
        ("possible", None, None, False),  # a possible duplicate stays apart until decided
        ("possible", "same", None, True),  # the reviewer merged it
        ("same", "different", None, False),  # the reviewer kept it apart
        ("possible", None, "same", True),  # the other side's reviewer merged it
        ("same", "same", "different", False),  # kept apart on either side wins
    ],
)
def test_a_type_recorded_as_the_same_as_an_element_goes_into_it(
    kind: str, decision: str | None, other: str | None, goes_into: bool
) -> None:
    ladle = existing("entity_type", "Ladle", "钢包", revision=2)
    item = recorded(
        new_type(1, "TeemingLadle", "钢水包"),
        kind=kind,
        element_id=ladle.id,
        other_decision=other,
        decision=decision,
    )
    expected = Resolution("into", element_id=ladle.id, element_revision=2)
    assert (plan([item], [ladle])[item.id] == expected) is goes_into


def test_a_type_recorded_as_another_change_sets_item_goes_where_that_item_went() -> None:
    ladle = existing("entity_type", "Ladle", "钢包")
    other_item = uuid4()
    merged = recorded(
        new_type(1, "TeemingLadle", "钢水包"),
        kind="same",
        item_id=other_item,
        item_element_id=ladle.id,
    )
    pending = recorded(new_type(1, "TeemingLadle", "钢水包"), kind="same", item_id=other_item)
    assert plan([merged], [ladle])[merged.id].element_id == ladle.id
    # The other item is still pending: created as proposed; the other merges into it later.
    assert plan([pending], [ladle])[pending.id] == Resolution("create")


def test_a_type_that_a_merged_item_recorded_goes_into_what_that_item_became() -> None:

    ladle = existing("entity_type", "Ladle", "钢包")
    pot = existing("entity_type", "Pot", "铁水罐", created_at=T0 + timedelta(days=1))
    entries = (
        PlanMatchedBy("same", pot.id, None, T0 + timedelta(days=2)),
        PlanMatchedBy("same", ladle.id, None, T0 + timedelta(days=1)),
        PlanMatchedBy("possible", pot.id, None, T0),
    )
    item = recorded(new_type(1, "TeemingLadle", "钢水包"), matched_by=entries)
    # The oldest record that is in effect.
    assert plan([item], [ladle, pot])[item.id].element_id == ladle.id
    kept = recorded(new_type(1, "TeemingLadle", "钢水包"), matched_by=entries, decision="different")
    assert plan([kept], [ladle, pot])[kept.id] == Resolution("create")


def test_a_type_merged_into_an_item_of_its_own_change_set_waits_for_that_item() -> None:
    ladle = existing("entity_type", "Ladle", "钢包")
    first = new_type(1, "TeemingLadle", "钢水包")
    second = recorded(
        new_type(2, "Pot", "盛钢桶"), kind="possible", item_id=first.id, decision="same"
    )
    result = plan([first, second], [ladle])
    assert result[second.id] == Resolution("into", item_id=first.id)
    assert changes_the_merge([first, second], result)
    # An item of the change set that goes into an element takes this one with it.
    into_ladle = new_type(1, "Ladle2", "钢包")
    follower = recorded(
        new_type(2, "Pot", "盛钢桶"), kind="possible", item_id=into_ladle.id, decision="same"
    )
    assert plan([into_ladle, follower], [ladle])[follower.id].element_id == ladle.id
    # The token tells the two plans apart.
    token = plan_token([first, second], [ladle], result)
    assert token != plan_token([first, second], [ladle], plan([first], [ladle]))


def test_a_record_of_a_deleted_element_is_no_reason_to_go_into_it() -> None:
    gone = existing("entity_type", "Ladle", "钢包", status="deprecated")
    item = recorded(new_type(1, "TeemingLadle", "钢水包"), kind="same", element_id=gone.id)
    assert plan([item], [gone])[item.id] == Resolution("create")


def test_a_name_record_holds_while_the_main_names_agree() -> None:
    issue = existing("entity_type", "SparePartsIssue", "备件领用单")
    record = {"kind": "name", "item_id": uuid4(), "item_element_id": issue.id}
    slip = recorded(new_type(1, "IssueSlip", "领用单"), item_label_zh="领用单", **record)
    assert plan([slip], [issue])[slip.id].element_id == issue.id
    # No "keep apart" for it: renaming one side is what undoes it (spec 004, 5.5).
    kept = recorded(
        new_type(1, "IssueSlip", "领用单"), item_label_zh="领用单", decision="different", **record
    )
    assert plan([kept], [issue])[kept.id].element_id == issue.id
    renamed = recorded(new_type(1, "IssueSlip", "领料单"), item_label_zh="领用单", **record)
    assert plan([renamed], [issue])[renamed.id] == Resolution("create")


def test_relations_of_two_items_of_one_concept_in_a_change_set_become_one() -> None:
    heat = existing("entity_type", "Heat", "炉次")
    ladle = new_type(1, "Ladle", "钢包")
    pot = recorded(new_type(2, "Pot", "钢水包"), kind="same", item_id=ladle.id)

    def uses(seq: int, ref: str, local_name: str) -> PlanItem:
        return proposed(
            seq,
            "create",
            "relation_type",
            temp_ref=f"new:{local_name}",
            local_name=local_name,
            label_zh="使用",
            domain_ref=str(heat.id),
            range_ref=ref,
        )

    first, second = uses(3, "new:Ladle", "usesLadle"), uses(4, "new:Pot", "usesPot")
    result = plan([ladle, pot, first, second], [heat])
    assert result[pot.id] == Resolution("into", item_id=ladle.id)
    assert result[first.id] == Resolution("create")
    assert result[second.id] == Resolution("into", item_id=first.id)


def test_a_records_decision_is_not_taken_for_a_record_of_another_pair() -> None:
    ladle = existing("entity_type", "Ladle", "钢包")
    other = existing("entity_type", "Pot", "铁水罐")
    entry = PlanMatchedBy("possible", ladle.id, None, T0)
    # The item's own record points at 铁水罐; its "same" is about that pair, not about 钢包.
    item = recorded(
        new_type(1, "Teeming", "钢水包"),
        kind="possible",
        element_id=other.id,
        decision="same",
        matched_by=(entry,),
    )
    assert plan([item], [ladle, other])[item.id].element_id == other.id
    alone = recorded(new_type(1, "Teeming", "钢水包"), decision="same", matched_by=(entry,))
    assert plan([alone], [ladle, other])[alone.id].element_id == ladle.id
