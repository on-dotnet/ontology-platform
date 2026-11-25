"""Sentence units of a chunk's text (spec 004, section 8).

A relation's direct evidence is the sentence its quote touches, whatever the file format: a
PDF breaks a sentence over several lines where the page ends, while a Markdown or Word line is
a whole paragraph. Units are spans of the original text, so that evidence offsets map onto them.
"""

import math
import re
import unicodedata
from collections.abc import Sequence

# A unit longer than this is cut; lines joined this far without a sentence end are not joined.
MAX_UNIT = 300
# A line at least this share of the block's usual width (90th percentile) was broken by layout.
WRAP_SHARE = 0.8
WRAP_PERCENTILE = 0.9

_ENDS = frozenset("。！？；!?;")  # noqa: RUF001 (full-width punctuation)
_CLOSERS = frozenset("”’」』）)】》\"'")  # noqa: RUF001
# A line starting like this is a list item, table row or heading of its own.
_MARKER = re.compile(r"\s*(?:[-*•|#]|\d+(?:[.．](?!\d)|、))")  # noqa: RUF001
_HEADING = re.compile(r"\s*#")
_NUMBER_ONLY = re.compile(r"\s*\d+")
_CUTS = ("\n", "，", ",")

Span = tuple[int, int]


def split_sentences(text: str) -> list[Span]:
    """The (start, end) of every unit, in order, without surrounding whitespace."""
    lines = _lines(text)
    widths = [_width(text[start:end].rstrip()) for start, end in lines if text[start:end].strip()]
    usual = _percentile(widths, WRAP_PERCENTILE)
    units: list[Span] = []
    block_start = 0
    for index, (start, end) in enumerate(lines):
        if block_start == index and not text[start:end].strip():
            block_start = index + 1
            continue
        following = lines[index + 1] if index + 1 < len(lines) else None
        if following is not None and _wrapped(text[start:end], text[slice(*following)], usual):
            continue
        units += _block(text, lines[block_start][0], end)
        block_start = index + 1
    return units


def covering(units: Sequence[Span], start: int, end: int) -> Span | None:
    """From the first to the last unit that the span [start, end) touches; None if none."""
    touched = [
        (unit_start, unit_end)
        for unit_start, unit_end in units
        if unit_start < max(end, start + 1) and start < unit_end
    ]
    if not touched:
        return None
    return touched[0][0], touched[-1][1]


def _lines(text: str) -> list[Span]:
    spans: list[Span] = []
    start = 0
    for line in text.split("\n"):
        spans.append((start, start + len(line)))
        start += len(line) + 1
    return spans


def _width(line: str) -> int:
    """Display width: full-width characters count twice."""
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in line)


def _percentile(values: Sequence[int], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def _wrapped(line: str, following: str, usual: float) -> bool:
    """Whether the line break after `line` is the layout's, inside a sentence."""
    current = line.strip()
    if not current or not following.strip() or _MARKER.match(following) or _HEADING.match(line):
        return False
    if _ends_sentence(current):
        return False
    return _width(line.rstrip()) >= WRAP_SHARE * usual


def _ends_sentence(line: str) -> bool:
    last = line.rstrip("".join(_CLOSERS)) or line
    if last[-1] in _ENDS:
        return True
    return last[-1] == "." and not _NUMBER_ONLY.fullmatch(last[:-1])


def _block(text: str, start: int, end: int) -> list[Span]:
    """Units of lines joined by layout breaks: sentences, guarded and cut to length."""
    units: list[Span] = []
    for piece_start, piece_end in _sentences(text, start, end):
        piece = text[piece_start:piece_end]
        if "\n" in piece and len(piece.strip()) > MAX_UNIT:
            # So long without a sentence end, these are rows (a table), not one sentence.
            units += [
                (line_start + piece_start, line_end + piece_start)
                for line_start, line_end in _lines(piece)
            ]
        else:
            units.append((piece_start, piece_end))
    return [cut for unit in units for cut in _cut(text, *_strip(text, *unit))]


def _sentences(text: str, start: int, end: int) -> list[Span]:
    spans: list[Span] = []
    begin = start
    index = start
    while index < end:
        if _is_end(text, index, end):
            stop = index + 1
            while stop < end and text[stop] in _CLOSERS:
                stop += 1
            spans.append((begin, stop))
            begin = index = stop
            continue
        index += 1
    spans.append((begin, end))
    return spans


def _is_end(text: str, index: int, end: int) -> bool:
    char = text[index]
    if char in _ENDS:
        return True
    if char != "." or (index + 1 < end and not text[index + 1].isspace()):
        return False
    line_start = text.rfind("\n", 0, index) + 1
    if _NUMBER_ONLY.fullmatch(text[line_start:index]):
        return False  # the number of a list item: "1. 装料"
    following = index + 1
    while following < end and text[following].isspace():
        following += 1
    return not (
        index > 0 and text[index - 1].isdigit() and following < end and text[following].isdigit()
    )


def _strip(text: str, start: int, end: int) -> Span:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _cut(text: str, start: int, end: int) -> list[Span]:
    """A unit longer than MAX_UNIT, cut at the last line break or comma within the limit."""
    if start == end:
        return []
    pieces: list[Span] = []
    while end - start > MAX_UNIT:
        window = text[start : start + MAX_UNIT]
        at = max(window.rfind(mark) for mark in _CUTS)
        stop = start + at + 1 if at > 0 else start + MAX_UNIT
        piece = _strip(text, start, stop)
        if piece[0] < piece[1]:
            pieces.append(piece)
        start = _strip(text, stop, end)[0]
    if start < end:
        pieces.append((start, end))
    return pieces
