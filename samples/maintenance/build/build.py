# Builds the maintenance sample documents (PDF, Word, Excel) in ../docs from the plain-text sources in src/.
# ruff: noqa: E402
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab import rl_config

# Must be set before any canvas is created so that PDFs are byte-for-byte reproducible.
rl_config.invariant = 1

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT = "CJK"
DEFAULT_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
FIXED_TIME = dt.datetime(2026, 11, 1, 9, 0, 0)
MARGIN = 20 * mm
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CORE_TIME_RE = re.compile(rb"(<dcterms:(created|modified)[^>]*>)[^<]*(</dcterms:\2>)")

Block = tuple[str, object]


# Source markup, one item per line:
#   @title / @header / @author <text>   document metadata
#   @sheet <name>                       starts an Excel worksheet
#   # text, ## text                     level 1 / level 2 headings
#   | a | b | c |                       table row; consecutive rows form one table, the first is the header
#   ---page---                          page break
#   anything else                       a body paragraph
def parse(path: Path) -> tuple[dict[str, str], list[Block]]:
    meta: dict[str, str] = {}
    blocks: list[Block] = []
    table: list[list[str]] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("|"):
            if table is None:
                table = []
                blocks.append(("table", table))
            table.append([cell.strip() for cell in line.strip("|").split("|")])
            continue
        table = None
        if not line:
            continue
        if line.startswith("@"):
            key, _, value = line[1:].partition(" ")
            if key == "sheet":
                blocks.append(("sheet", value.strip()))
            else:
                meta[key] = value.strip()
        elif line == "---page---":
            blocks.append(("page", ""))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        else:
            blocks.append(("p", line))
    return meta, blocks


def text_width(text: str) -> float:
    # CJK glyphs are full width; Latin letters and digits are roughly half.
    return sum(1.0 if ord(ch) > 0x2E7F else 0.55 for ch in text)


def pad(rows: list[list[str]]) -> list[list[str]]:
    ncols = max(len(row) for row in rows)
    return [row + [""] * (ncols - len(row)) for row in rows]


# ---------- PDF ----------


class NumberedCanvas(canvas.Canvas):
    """Holds pages back until save() so every footer can show the total page count."""

    header = ""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._held_pages: list[dict[str, object]] = []

    def showPage(self) -> None:  # noqa: N802 - reportlab API
        self._held_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._held_pages)
        for state in self._held_pages:
            self.__dict__.update(state)
            self._decorate(total)
            super().showPage()
        super().save()

    def _decorate(self, total: int) -> None:
        width, height = A4
        self.setFont(FONT, 9)
        self.drawString(MARGIN, height - 14 * mm, self.header)
        self.setLineWidth(0.5)
        self.line(MARGIN, height - 15.5 * mm, width - MARGIN, height - 15.5 * mm)
        self.drawCentredString(width / 2, 11 * mm, f"第 {self.getPageNumber()} 页 共 {total} 页")


def pdf_styles() -> dict[str, ParagraphStyle]:
    common = {"fontName": FONT, "wordWrap": "CJK"}
    return {
        "title": ParagraphStyle("title", fontSize=16, leading=26, alignment=TA_CENTER, spaceAfter=10, **common),
        "h1": ParagraphStyle("h1", fontSize=13, leading=20, spaceBefore=8, spaceAfter=4, keepWithNext=1, **common),
        "h2": ParagraphStyle("h2", fontSize=11.5, leading=18, spaceBefore=5, spaceAfter=2, keepWithNext=1, **common),
        "p": ParagraphStyle("p", fontSize=10.5, leading=16, firstLineIndent=21, spaceAfter=3, **common),
        "cell": ParagraphStyle("cell", fontSize=9.5, leading=13, **common),
    }


def pdf_table(rows: list[list[str]], styles: dict[str, ParagraphStyle], avail: float) -> Table:
    rows = pad(rows)
    ncols = len(rows[0])
    weights = [min(max(text_width(row[i]) for row in rows), 22.0) + 2.0 for i in range(ncols)]
    widths = [avail * w / sum(weights) for w in weights]
    data = [[Paragraph(escape(cell), styles["cell"]) for cell in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6E6E6")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def build_pdf(meta: dict[str, str], blocks: list[Block], out: Path) -> None:
    styles = pdf_styles()
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=24 * mm,
        bottomMargin=20 * mm,
        title=meta.get("title", ""),
        author=meta.get("author", ""),
    )
    story: list[object] = []
    if "title" in meta:
        story.append(Paragraph(escape(meta["title"]), styles["title"]))
    for kind, value in blocks:
        if kind == "table":
            story += [pdf_table(value, styles, doc.width), Spacer(1, 6)]  # type: ignore[arg-type]
        elif kind == "page":
            story.append(PageBreak())
        elif kind in styles:
            story.append(Paragraph(escape(str(value)), styles[kind]))
    canvas_class = type("HeaderCanvas", (NumberedCanvas,), {"header": meta.get("header", "")})
    doc.build(story, canvasmaker=canvas_class)  # type: ignore[arg-type]


# ---------- Word ----------


def add_field(paragraph: object, code: str) -> None:
    run = paragraph.add_run()  # type: ignore[attr-defined]
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = code
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, end])


def set_east_asian_font(style: object, font: str) -> None:
    rfonts = style.element.get_or_add_rPr().get_or_add_rFonts()  # type: ignore[attr-defined]
    rfonts.attrib.pop(qn("w:eastAsiaTheme"), None)
    rfonts.set(qn("w:eastAsia"), font)


def build_docx(meta: dict[str, str], blocks: list[Block], out: Path) -> None:
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10.5)
    set_east_asian_font(doc.styles["Normal"], "宋体")
    for name in ("Title", "Heading 1", "Heading 2"):
        set_east_asian_font(doc.styles[name], "黑体")

    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.header.paragraphs[0].text = meta.get("header", "")
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.add_run("第 ")
    add_field(footer, "PAGE")
    footer.add_run(" 页 共 ")
    add_field(footer, "NUMPAGES")
    footer.add_run(" 页")

    if "title" in meta:
        doc.add_heading(meta["title"], level=0)
    for kind, value in blocks:
        if kind == "h1":
            doc.add_heading(str(value), level=1)
        elif kind == "h2":
            doc.add_heading(str(value), level=2)
        elif kind == "p":
            doc.add_paragraph(str(value))
        elif kind == "page":
            doc.add_page_break()
        elif kind == "table":
            rows = pad(value)  # type: ignore[arg-type]
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Table Grid"
            for r, row in enumerate(rows):
                for c, text in enumerate(row):
                    cell = table.cell(r, c)
                    cell.text = text
                    if r == 0:
                        for run in cell.paragraphs[0].runs:
                            run.bold = True

    props = doc.core_properties
    props.title = meta.get("title", "")
    props.author = meta.get("author", "")
    props.last_modified_by = meta.get("author", "")
    props.created = props.modified = FIXED_TIME
    props.revision = 1
    doc.save(str(out))
    normalize_zip(out)


# ---------- Excel ----------


def cell_value(text: str) -> object:
    if not text:
        return None
    return dt.date.fromisoformat(text) if DATE_RE.match(text) else text


def build_xlsx(meta: dict[str, str], blocks: list[Block], out: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    sheet = None
    for kind, value in blocks:
        if kind == "sheet":
            sheet = wb.create_sheet(str(value))
        elif kind == "table" and sheet is not None:
            for row in pad(value):  # type: ignore[arg-type]
                sheet.append([cell_value(text) for text in row])
    for sheet in wb.worksheets:
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        sheet.freeze_panes = "A2"
        for column in sheet.columns:
            width = max(text_width(str(c.value or "")) * 2 for c in column)
            sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)
    wb.properties.creator = meta.get("author", "")
    wb.properties.title = meta.get("title", "")
    wb.properties.created = wb.properties.modified = FIXED_TIME
    wb.save(str(out))
    normalize_zip(out)


def normalize_zip(path: Path) -> None:
    # Office files are zip archives: pin entry timestamps and core.xml dates so rebuilds are identical.
    with zipfile.ZipFile(path) as src:
        entries = [(info.filename, src.read(info)) for info in src.infolist()]
    stamp = FIXED_TIME.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(path, "w") as dst:
        for name, data in entries:
            if name == "docProps/core.xml":
                data = CORE_TIME_RE.sub(rb"\g<1>" + stamp + rb"\g<3>", data)
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME.timetuple()[:6])
            dst.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)


BUILDERS = {".pdf": build_pdf, ".docx": build_docx, ".xlsx": build_xlsx}


def main() -> None:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Build the maintenance sample documents from src/.")
    parser.add_argument("--out", type=Path, default=here.parent / "docs", help="output directory (default: ../docs)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont(FONT, os.environ.get("OP_CJK_FONT", DEFAULT_FONT_PATH), subfontIndex=0))
    for src in sorted((here / "src").glob("*.txt")):
        target = args.out / src.stem  # "01-xxx.pdf.txt" -> "01-xxx.pdf"
        meta, blocks = parse(src)
        BUILDERS[target.suffix](meta, blocks, target)
        print(target)


if __name__ == "__main__":
    main()
