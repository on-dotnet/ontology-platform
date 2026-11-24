from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document
from openpyxl import Workbook  # type: ignore[import-untyped]
from pypdf import PdfReader, PdfWriter

from ontology_platform.errors import AppError
from ontology_platform.modules.documents import parsers
from ontology_platform.modules.documents.parsers import ParsedPage, detect_type, parse_document

FIXTURES = Path(__file__).parent / "fixtures" / "documents"


def parse(filename: str, data: bytes) -> list[ParsedPage]:
    return parse_document(detect_type(filename, data), data).pages


@pytest.mark.parametrize("filename", ["notes.TXT", "notes.md"])
def test_plain_text_preserves_whitespace(filename: str) -> None:
    content = "  熔炼\r\n\r\nnext line   \n"
    assert parse(filename, content.encode("utf-8-sig")) == [ParsedPage(None, content)]


def test_gbk_text_is_decoded() -> None:
    assert parse("notes.txt", "炉次与浇次".encode("gbk")) == [ParsedPage(None, "炉次与浇次")]


def test_empty_and_undecodable_text() -> None:
    for data in (b"", b"\xff"):
        with pytest.raises(AppError) as exc:
            parse("notes.txt", data)
        assert exc.value.code == "documents.unreadable"


def test_word_headings_and_tables_follow_document_order() -> None:
    document = Document()
    document.add_paragraph("Preface")
    document.add_heading("Steel", level=1)
    document.add_heading("Slabs", level=2)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Grade"
    table.cell(0, 1).text = "Count"
    table.cell(1, 0).text = "A|B"
    table.cell(1, 1).text = "0"
    document.add_paragraph("After table")
    file = BytesIO()
    document.save(file)
    pages = parse("example.docx", file.getvalue())
    assert pages[0] == ParsedPage(None, "Preface")
    assert pages[-1].heading == "Steel / Slabs"
    assert pages[-1].text == (
        "Slabs\n\n| Grade | Count |\n| --- | --- |\n| A\\|B | 0 |\n\nAfter table"
    )
    with pytest.raises(AppError) as exc:
        detect_type("fake.xlsx", file.getvalue())
    assert exc.value.code == "documents.unsupported_type"


def test_workbook_skips_empty_sheets_and_preserves_sheet_numbers() -> None:
    workbook = Workbook()
    sheet = workbook.create_sheet("Heat")
    sheet.append(["Grade", "Count"])
    sheet.append(["Q235", 0])
    file = BytesIO()
    workbook.save(file)
    assert parse("example.xlsx", file.getvalue()) == [
        ParsedPage(2, "| Grade | Count |\n| --- | --- |\n| Q235 | 0 |", "Heat")
    ]


def test_expanded_workbook_grid_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    workbook = Workbook()
    workbook.active["C3"] = "nonempty"
    file = BytesIO()
    workbook.save(file)
    monkeypatch.setattr(parsers, "_MAX_SHEET_CELLS", 8)
    with pytest.raises(AppError) as exc:
        parse("large.xlsx", file.getvalue())
    assert exc.value.code == "documents.unreadable"


@pytest.mark.parametrize(
    ("filename", "data"),
    [("fake.txt", b"%PDF-1.4"), ("fake.pdf", b"Hello"), ("fake.docx", b"Hello"), ("a.bin", b"")],
)
def test_mismatched_types(filename: str, data: bytes) -> None:
    with pytest.raises(AppError) as exc:
        detect_type(filename, data)
    assert (exc.value.status, exc.value.code) == (415, "documents.unsupported_type")


def test_zip_without_matching_content_type_is_rejected() -> None:
    file = BytesIO()
    with ZipFile(file, "w") as archive:
        archive.writestr("word/document.xml", "")
        archive.writestr("[Content_Types].xml", "<Types/>")
    with pytest.raises(AppError) as exc:
        detect_type("fake.docx", file.getvalue())
    assert exc.value.code == "documents.unsupported_type"


def test_damaged_pdf() -> None:
    with pytest.raises(AppError) as exc:
        parse("bad.pdf", b"%PDF-1.4\ntruncated")
    assert exc.value.code == "documents.unreadable"


def test_damaged_office_document() -> None:
    file = BytesIO()
    Document().save(file)
    damaged = BytesIO()
    with ZipFile(file) as source, ZipFile(damaged, "w") as output:
        for name in source.namelist():
            content = b"<broken" if name == "word/document.xml" else source.read(name)
            output.writestr(name, content)
    with pytest.raises(AppError) as exc:
        parse("broken.docx", damaged.getvalue())
    assert exc.value.code == "documents.unreadable"


def test_pdf_text_and_scan_detection() -> None:
    for filename, needs_vision in [("text.pdf", False), ("blank.pdf", True)]:
        data = (FIXTURES / filename).read_bytes()
        result = parse_document(detect_type(filename, data), data)
        assert result.page_count == 1
        assert result.needs_vision is needs_vision
        if needs_vision:
            assert result.pages == []
        else:
            assert result.pages[0].number == 1
            assert "Steel" in result.pages[0].text


def test_a_scan_is_split_into_parts_for_transcription() -> None:
    writer = PdfWriter()
    for _ in range(12):
        writer.add_blank_page(width=200, height=200)
    file = BytesIO()
    writer.write(file)

    result = parse_document("application/pdf", file.getvalue())

    assert (result.needs_vision, result.page_count) == (True, 12)
    assert [(p.first_page, p.page_count) for p in result.scan_parts] == [(1, 5), (6, 5), (11, 2)]
    assert [len(PdfReader(BytesIO(p.data)).pages) for p in result.scan_parts] == [5, 5, 2]


def test_a_text_pdf_has_no_scan_parts() -> None:
    data = (FIXTURES / "text.pdf").read_bytes()
    assert parse_document("application/pdf", data).scan_parts == ()


def test_a_scan_over_the_page_limit_is_not_split() -> None:
    writer = PdfWriter()
    for _ in range(12):
        writer.add_blank_page(width=200, height=200)
    file = BytesIO()
    writer.write(file)

    result = parse_document("application/pdf", file.getvalue(), max_scanned_pages=11)

    assert (result.needs_vision, result.page_count, result.scan_parts) == (True, 12, ())
