"""Sentence units of a chunk (spec 004, section 8): where direct evidence of a relation ends."""

from ontology_platform.modules.ai.sentences import covering, split_sentences


def units(text: str) -> list[str]:
    return [text[start:end] for start, end in split_sentences(text)]


def test_sentence_end_punctuation_ends_a_unit() -> None:
    text = "每个炉次只冶炼一个钢种；钢种由计划确定。钢包吊运至精炼炉！是否合格？Done! Next."
    assert units(text) == [
        "每个炉次只冶炼一个钢种；",
        "钢种由计划确定。",
        "钢包吊运至精炼炉！",
        "是否合格？",
        "Done!",
        "Next.",
    ]


def test_a_comma_or_a_point_inside_a_number_does_not() -> None:
    text = "出钢温度为1650.5℃，钢包容量120 t. 板坯厚度230 mm，宽度1.2 m。"
    assert units(text) == ["出钢温度为1650.5℃，钢包容量120 t.", "板坯厚度230 mm，宽度1.2 m。"]


def test_closing_quotes_stay_with_their_sentence() -> None:
    assert units("判定为“合格”。结果记入台账。") == ["判定为“合格”。", "结果记入台账。"]
    assert units('判定为"不合格。"然后复检。') == ['判定为"不合格。"', "然后复检。"]


def test_blank_lines_list_items_table_rows_and_headings_are_units() -> None:
    text = "\n".join(
        [
            "# 转炉炼钢",
            "转炉冶炼过程中",
            "",
            "钢水温度逐步升高",
            "- 炉次以炉号标识",
            "* 钢种按牌号区分",
            "• 钢包循环使用",
            "1. 装料",
            "2、兑铁",
            "| 炉号 | 钢种 |",
            "| 0457 | Q235B |",
        ]
    )
    assert units(text) == [
        "# 转炉炼钢",
        "转炉冶炼过程中",
        "钢水温度逐步升高",
        "- 炉次以炉号标识",
        "* 钢种按牌号区分",
        "• 钢包循环使用",
        "1. 装料",
        "2、兑铁",
        "| 炉号 | 钢种 |",
        "| 0457 | Q235B |",
    ]


def test_a_line_broken_by_the_layout_continues_its_sentence() -> None:
    # Text extracted from a PDF: lines are as wide as the page, the last one of a paragraph
    # is shorter and the next paragraph starts on a new line.
    text = (
        "每个炉次的钢水出钢后装入钢包，随后由行车\n"
        "吊运至精炼炉进行成分和温度调整，精炼结束\n"
        "后送往连铸机。\n"
        "连铸机按浇次组织生产。\n"
        "短行不是被折断的\n"
        "下一行是新的一句。"
    )
    assert units(text) == [
        "每个炉次的钢水出钢后装入钢包，随后由行车\n吊运至精炼炉进行成分和温度调整，精炼结束\n后送往连铸机。",
        "连铸机按浇次组织生产。",
        "短行不是被折断的",
        "下一行是新的一句。",
    ]


def test_a_wide_line_ending_a_sentence_does_not_join_the_next() -> None:
    text = "钢卷在精整线上由表面检测仪和人工共同检查。\n发现的缺陷记录为缺陷记录并关联到钢卷位置\n"
    assert units(text) == [
        "钢卷在精整线上由表面检测仪和人工共同检查。",
        "发现的缺陷记录为缺陷记录并关联到钢卷位置",
    ]


def test_a_table_without_punctuation_is_not_joined_into_one_unit() -> None:
    # A table extracted from a PDF: rows without punctuation and about as wide as each other.
    rows = [
        f"2611-2-{index:04d}  Q235B  1650  转炉{index % 3 + 1}  钢包{index:02d}  合格"
        for index in range(30)
    ]
    assert units("\n".join(rows)) == rows


def test_a_unit_longer_than_300_characters_is_cut_at_a_comma_or_line_break() -> None:
    clause = "钢水经过精炼处理后成分均匀"  # 13 characters
    text = "，".join([clause] * 30) + "。"
    pieces = units(text)
    assert len(pieces) > 1
    assert all(len(piece) <= 300 for piece in pieces)
    assert all(piece.endswith(("，", "。")) for piece in pieces)
    assert "".join(pieces) == text


def test_without_any_break_a_long_unit_is_cut_at_300_characters() -> None:
    text = "钢" * 650
    assert [len(piece) for piece in units(text)] == [300, 300, 50]


def test_covering_takes_every_unit_a_span_touches() -> None:
    text = "炉次在转炉冶炼。钢水装入钢包。钢包运往精炼炉。"
    spans = split_sentences(text)
    start = text.index("装入")
    one = covering(spans, start, start + 2)
    assert one is not None
    assert text[slice(*one)] == "钢水装入钢包。"
    end = text.index("运往") + 2
    both = covering(spans, start, end)
    assert both is not None
    assert text[slice(*both)] == "钢水装入钢包。钢包运往精炼炉。"
    assert covering(spans, len(text) + 5, len(text) + 6) is None
