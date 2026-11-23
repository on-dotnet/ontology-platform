"""Split text without changing the characters used for evidence offsets."""

import re
from dataclasses import dataclass

from ontology_platform.modules.documents.parsers import ParsedPage

_BOUNDARIES = (
    re.compile(r"(?:\r?\n)[ \t]*(?:\r?\n)"),
    re.compile(r"\r\n|[\r\n]"),
    re.compile(r"[.。！？!?；;]"),
)


@dataclass(frozen=True, slots=True)
class TextChunk:
    text: str
    page: int | None
    heading: str | None
    char_count: int


def chunk_pages(pages: list[ParsedPage], max_chars: int = 2000) -> list[TextChunk]:
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks: list[TextChunk] = []
    for page in pages:
        start = 0
        while start < len(page.text):
            end = min(start + max_chars, len(page.text))
            if end < len(page.text):
                for boundary in _BOUNDARIES:
                    last = max(
                        (m.end() for m in boundary.finditer(page.text, start, end)), default=0
                    )
                    if last:
                        end = last
                        break
            text = page.text[start:end]
            chunks.append(TextChunk(text, page.number, page.heading, len(text)))
            start = end
    return chunks
