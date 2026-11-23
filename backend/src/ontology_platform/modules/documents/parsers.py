"""Detect supported originals and extract pages in reading order."""

import re
import zlib
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from xml.parsers import expat
from zipfile import BadZipFile, ZipFile, is_zipfile

from docx import Document
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook  # type: ignore[import-untyped]
from pypdf import PdfReader

from ontology_platform.errors import AppError

_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_MEDIA = {
    ".docx": _DOCX,
    ".xlsx": _XLSX,
    ".pdf": "application/pdf",
    ".md": "text/markdown",
    ".txt": "text/plain",
}
_PARTS = {_DOCX: "word/document.xml", _XLSX: "xl/workbook.xml"}
_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
# Bound parser memory independently of the compressed upload size.
_MAX_EXPANDED_BYTES = 128 * 1024 * 1024
_MAX_SHEET_CELLS = 1_000_000


@dataclass(frozen=True, slots=True)
class ParsedPage:
    number: int | None
    text: str
    heading: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    pages: list[ParsedPage]
    page_count: int
    needs_vision: bool = False


def _unsupported() -> AppError:
    return AppError(415, "documents.unsupported_type", "Unsupported document type.")


def _unreadable() -> AppError:
    return AppError(422, "documents.unreadable", "The document could not be read.")


def _declares_part(manifest: bytes, part: str, media: str) -> bool:
    found = False

    def start_element(name: str, attrs: dict[str, str]) -> None:
        nonlocal found
        if (
            name == _TYPES_NS + " Override"
            and attrs.get("PartName") == "/" + part
            and attrs.get("ContentType") == media + ".main+xml"
        ):
            found = True

    def reject_doctype(*args: object) -> None:
        raise _unsupported()

    parser = expat.ParserCreate(namespace_separator=" ")
    parser.StartElementHandler = start_element
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.Parse(manifest, True)
    return found


def _check_office(data: bytes, media: str) -> None:
    part = _PARTS[media]
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist()) > _MAX_EXPANDED_BYTES:
                raise _unreadable()
            archive.getinfo(part)
            manifest = archive.getinfo("[Content_Types].xml")
            if manifest.file_size > 1024 * 1024:
                raise _unsupported()
            if _declares_part(archive.read(manifest), part, media):
                return
    except (BadZipFile, KeyError, RuntimeError, ValueError, expat.ExpatError, zlib.error) as exc:
        raise _unsupported() from exc
    raise _unsupported()


def detect_type(filename: str, data: bytes) -> str:
    media = _MEDIA.get(Path(filename).suffix.lower())
    if media is None:
        raise _unsupported()
    if media in _PARTS:
        _check_office(data, media)
    elif media == "application/pdf":
        if not data.startswith(b"%PDF-"):
            raise _unsupported()
    elif data.startswith(b"%PDF-") or b"\x00" in data or is_zipfile(BytesIO(data)):
        raise _unsupported()
    return media


def _markdown_table(rows: list[list[str]]) -> str:
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return ""

    def line(row: list[str]) -> str:
        cells = [escape(value) for value in row]
        cells.extend([""] * (width - len(row)))
        return "| " + " | ".join(cells) + " |"

    def escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")

    return "\n".join([line(rows[0]), line(["---"] * width), *(line(row) for row in rows[1:])])


def _word(data: bytes) -> ParsedDocument:
    pages: list[ParsedPage] = []
    headings: list[tuple[int, str]] = []
    paragraphs: list[str] = []

    def flush() -> None:
        if paragraphs:
            heading = " / ".join(text for _, text in headings) or None
            pages.append(ParsedPage(None, "\n\n".join(paragraphs), heading))
            paragraphs.clear()

    for block in Document(BytesIO(data)).iter_inner_content():
        if isinstance(block, Paragraph):
            style = block.style
            heading = re.fullmatch(r"Heading (\d+)", style.name or "") if style else None
            if heading:
                flush()
                level = int(heading.group(1))
                headings = [(n, title) for n, title in headings if n < level]
                headings.append((level, block.text))
            paragraphs.append(block.text)
        else:
            rows = [[cell.text for cell in row.cells] for row in block.rows]
            paragraphs.append(_markdown_table(rows))
    flush()
    return ParsedDocument(pages, 1)


def _workbook(data: bytes) -> ParsedDocument:
    workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
    pages: list[ParsedPage] = []
    remaining = _MAX_SHEET_CELLS
    remaining_chars = _MAX_EXPANDED_BYTES
    try:
        for number, sheet in enumerate(workbook.worksheets, 1):
            # Some producers advertise an entire grid for a sheet holding only a few cells.
            sheet.reset_dimensions()
            rows: list[list[str]] = []
            width = 0
            for row in sheet.iter_rows(values_only=True):
                width = max(1, width, len(row))
                if (len(rows) + 1) * width > remaining:
                    raise _unreadable()
                cells = [str(value) if value is not None else "" for value in row]
                remaining_chars -= sum(map(len, cells))
                if remaining_chars < 0:
                    raise _unreadable()
                rows.append(cells)
            remaining -= len(rows) * width
            if any(any(row) for row in rows):
                pages.append(ParsedPage(number, _markdown_table(rows), sheet.title))
        return ParsedDocument(pages, len(workbook.worksheets))
    finally:
        workbook.close()


def _text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Text saved by Chinese Windows tools is often GBK; GB 18030 is its superset.
        return data.decode("gb18030")


def _pdf(data: bytes) -> ParsedDocument:
    reader = PdfReader(BytesIO(data))
    pages = [ParsedPage(number, page.extract_text()) for number, page in enumerate(reader.pages, 1)]
    chars = sum(not char.isspace() for page in pages for char in page.text)
    if pages and chars < 50 * len(pages):
        return ParsedDocument([], len(pages), needs_vision=True)
    return ParsedDocument(pages, len(pages))


def parse_document(media_type: str, data: bytes) -> ParsedDocument:
    try:
        if media_type in {"text/markdown", "text/plain"}:
            result = ParsedDocument([ParsedPage(None, _text(data))], 1)
        elif media_type == _DOCX:
            result = _word(data)
        elif media_type == _XLSX:
            result = _workbook(data)
        elif media_type == "application/pdf":
            result = _pdf(data)
        else:
            raise _unsupported()
    except AppError:
        raise
    except Exception as exc:
        # Library exceptions (including malformed XML, fonts, and encrypted files) are internal.
        raise _unreadable() from exc
    if not result.needs_vision and not any(page.text.strip() for page in result.pages):
        raise _unreadable()
    return result
