"""The name shortlist of alignment candidates (spec 004, 4.1)."""

import pytest

from ontology_platform.modules.ai.candidates import (
    Names,
    group_recall,
    main_name,
    same_main_name,
    score,
    shortlist,
    similarity,
)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("转炉", "转炉", 1.0),
        ("转炉", "氧气转炉", 0.8),  # one contains the other
        ("钢包", "钢水包", 0.8),  # SequenceMatcher: the abbreviation
        ("钢种", "钢种成分要求", 0.733),
        ("转炉", "电炉", 0.5),
        ("钢种", "钢号", 0.5),
        ("炉次", "转炉", 0.5),
        ("钢包", "盛钢桶", 0.4),  # what the shortlist cannot see
        ("炉", "转炉", 0.0),  # one character, not the same: nothing
        ("炉", "炉", 1.0),
    ],
)
def test_similarity_of_two_names(a: str, b: str, expected: float) -> None:
    assert round(similarity(a, b), 3) == expected


def test_a_pair_of_types_scores_its_best_weighted_pair_of_names() -> None:
    converter = Names.of("转炉", "Converter", ["炼钢炉"])
    # Main against main: the English labels count as main names.
    assert score(converter, Names.of("顶吹炉", "converter", [])).value == 1.0
    # Main against synonym weighs 0.9, synonym against synonym 0.8.
    assert score(converter, Names.of("BOF", None, ["转炉"])).value == 0.9
    assert score(converter, Names.of("电炉", None, ["炼钢炉"])).value == 0.8


def test_a_pair_reached_only_through_a_one_character_name_is_marked() -> None:
    furnace = Names.of("加热炉", None, ["炉"])
    converter = Names.of("转炉", None, ["炉"])
    found = score(furnace, converter)
    assert (found.value, found.one_character) == (0.8, True)
    # 加热炉 against 炼钢加热炉 scores on longer names: not a one-character match.
    assert not score(furnace, Names.of("炼钢加热炉", None, ["炉"])).one_character


def test_the_shortlist_keeps_the_best_three_at_or_above_the_threshold() -> None:
    names = Names.of("转炉", None, [])
    pool = [
        ("a", Names.of("电炉", None, [])),  # 0.5
        ("b", Names.of("氧气转炉", None, [])),  # 0.8
        ("c", Names.of("钢包", None, [])),  # 0
        ("d", Names.of("转炉设备", None, [])),  # 0.8
        ("e", Names.of("顶底复吹转炉", None, [])),  # 0.733
    ]
    assert [key for key, _ in shortlist(names, pool)] == ["b", "d", "e"]
    assert [key for key, _ in shortlist(names, pool, threshold=0.6, limit=5)] == ["b", "d", "e"]
    assert [key for key, _ in shortlist(names, pool, limit=5)] == ["b", "d", "e", "a"]


def test_main_names_and_their_equality() -> None:
    assert main_name(" 转 炉 ", "Converter") == "转炉"
    assert main_name(None, "Converter") == "converter"
    assert same_main_name("钢", None, "钢", "Steel")
    assert not same_main_name("转炉", "Converter", "电炉", "converter")
    assert same_main_name(None, "Converter", "转炉", "converter")


def test_group_recall_counts_the_pairs_of_names_that_become_candidates() -> None:
    groups = [["钢包", "钢水包", "盛钢桶"], ["转炉"]]
    # 钢包/钢水包 0.8; 钢包/盛钢桶 0.4; 钢水包/盛钢桶 0.33.
    assert group_recall(groups) == (1, 3)
    assert group_recall(groups, threshold=0.3) == (3, 3)
