import pytest

from ontology_platform.modules.documents.chunking import chunk_pages
from ontology_platform.modules.documents.parsers import ParsedPage


@pytest.mark.parametrize("boundary", ["\n\n", "\r\n\r\n", "\n", "。", "!", ".", ";"])
def test_boundary_retained_in_preceding_chunk(boundary: str) -> None:
    prefix = "start" + boundary
    pages = [ParsedPage(3, prefix + "x" * 16, "A")]
    chunks = chunk_pages(pages, max_chars=12)
    assert chunks[0].text == prefix
    assert "".join(chunk.text for chunk in chunks) == pages[0].text
    assert all(chunk.char_count == len(chunk.text) <= 12 for chunk in chunks)
    assert all((chunk.page, chunk.heading) == (3, "A") for chunk in chunks)


def test_paragraph_boundary_precedes_sentence_and_pages_never_mix() -> None:
    text = "abc\n\nline. tail  " + "z" * 2000
    pages = [ParsedPage(1, text, "one"), ParsedPage(2, "  next\t", "two")]
    chunks = chunk_pages(pages)
    assert chunks[0].text == "abc\n\n"
    assert "".join(chunk.text for chunk in chunks[:-1]) == text
    assert max(chunk.char_count for chunk in chunks) <= 2000
    assert (chunks[-1].text, chunks[-1].page, chunks[-1].heading) == ("  next\t", 2, "two")
