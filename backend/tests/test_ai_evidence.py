"""Quotes cited by the model must be found in the source text."""

from ontology_platform.modules.ai.evidence import locate_quote

TEXT = "转炉出钢后，钢水进入 LF 精炼炉。\n  精炼结束后，钢包吊运至连铸机。"


def test_exact_quote_is_located() -> None:
    found = locate_quote("钢水进入 LF 精炼炉", TEXT)
    assert found is not None
    assert TEXT[found.char_start : found.char_end] == "钢水进入 LF 精炼炉"


def test_whitespace_differences_are_ignored_and_offsets_map_to_the_original() -> None:
    found = locate_quote("精炼炉。 精炼结束后", TEXT)
    assert found is not None
    assert TEXT[found.char_start : found.char_end] == "精炼炉。\n  精炼结束后"


def test_paraphrased_quote_is_not_found() -> None:
    assert locate_quote("钢水送入精炼炉", TEXT) is None


def test_blank_quote_is_not_found() -> None:
    assert locate_quote("   ", TEXT) is None


def test_line_breaks_inside_a_sentence_are_ignored() -> None:
    # PDF text extraction breaks Chinese lines mid-sentence; the model quotes without the break.
    text = "板坯连铸时，结晶器\n液面波动应控制在\n±3 mm 以内。"
    found = locate_quote("结晶器液面波动应控制在±3 mm 以内", text)
    assert found is not None
    assert text[found.char_start : found.char_end] == "结晶器\n液面波动应控制在\n±3 mm 以内"
