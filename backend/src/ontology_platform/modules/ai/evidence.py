"""Evidence grounding: a quote the model cites must actually occur in the source text.

Models paraphrase and hallucinate quotes; anything we cannot find verbatim (modulo whitespace)
is flagged instead of being shown as evidence.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Located:
    char_start: int
    char_end: int


@dataclass(frozen=True)
class _View:
    """The text with whitespace normalized, and each character's offset in the original."""

    text: str
    origin: tuple[int, ...]

    def find(self, needle: str) -> Located | None:
        position = self.text.find(needle) if needle else -1
        if position < 0:
            return None
        return Located(self.origin[position], self.origin[position + len(needle) - 1] + 1)


def _view(text: str, *, keep_spaces: bool) -> _View:
    out: list[str] = []
    origin: list[int] = []
    previous_space = False
    for index, char in enumerate(text):
        if char.isspace():
            if not keep_spaces or previous_space:
                continue
            char, previous_space = " ", True
        else:
            previous_space = False
        out.append(char)
        origin.append(index)
    return _View("".join(out), tuple(origin))


@lru_cache(maxsize=512)
def _views(text: str) -> tuple[_View, _View]:
    # Every quote is tried against every chunk; build each chunk's views once.
    return _view(text, keep_spaces=True), _view(text, keep_spaces=False)


def locate_quote(quote: str, text: str) -> Located | None:
    """Offsets of `quote` in `text`, ignoring differences in whitespace. None when absent.

    First whitespace runs count as one space; then whitespace is ignored altogether, because
    text extracted from Chinese PDFs breaks lines mid-sentence and models quote without them.
    """
    squashed, stripped = _views(text)
    found = squashed.find(_WHITESPACE.sub(" ", quote).strip())
    return found or stripped.find(_WHITESPACE.sub("", quote))
