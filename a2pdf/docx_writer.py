"""Сборка .docx в оформлении A2DATA из тех же блоков, что и PDF.

Обложка и диаграммы рисуются тем же headless-браузером, что печатает PDF,
и вставляются в документ картинками — так Word выглядит один в один с PDF.
Остальное собирается настоящими объектами Word: заголовки, списки, таблицы,
код и цитаты остаются редактируемым текстом.
"""
from __future__ import annotations

import base64
import html as html_mod
import io
import pathlib
import re
import urllib.request

import pymupdf
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import core

NAVY = RGBColor(0x0B, 0x26, 0x60)
BLUE = RGBColor(0x12, 0x89, 0xD5)
INK = RGBColor(0x11, 0x17, 0x22)
GRAY = RGBColor(0x6B, 0x72, 0x80)
FONT = "Inter"
MONO = "JetBrains Mono"
DPI = 150


# --------------------------------------------------------------------------- #
# Картинки: обложка и диаграммы рисуются браузером
# --------------------------------------------------------------------------- #

def _pages_to_png(html_text: str, chrome: str, name: str,
                  wait_ms: int = 15000) -> list[bytes]:
    """Печатает HTML в PDF и отдаёт страницы картинками."""
    core.TMP.mkdir(parents=True, exist_ok=True)
    html_path = core.TMP / f"{name}.html"
    pdf_path = core.TMP / f"{name}.pdf"
    html_path.write_text(html_text, encoding="utf-8")
    try:
        core.print_pdf(html_path, pdf_path, chrome, wait_ms)
        with pymupdf.open(pdf_path) as doc:
            return [page.get_pixmap(dpi=DPI).tobytes("png") for page in doc]
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def _diagram_images(sources: list[str], chrome: str, name: str) -> list[bytes]:
    """Каждая диаграмма — отдельная страница, чтобы получить её картинкой."""
    if not sources:
        return []
    fonts = (core.ASSETS / "fonts.css").read_text(encoding="utf-8")
    lib = (core.ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
    body = "".join(
        '<div class="page"><div class="dg dg-mermaid"><pre class="mermaid">'
        f'{html_mod.escape(src)}</pre></div></div>' for src in sources)
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<style>{fonts}</style><style>{core.BODY_CSS}'
            '@page{size:A4;margin:10mm}'
            '.page{break-after:page;display:flex;align-items:center;'
            'justify-content:center;height:277mm}'
            '.dg{border:0;background:none;margin:0;padding:0;width:100%}'
            '.dg-mermaid svg{max-height:265mm}'
            f'</style></head><body>{body}'
            f'<script>{lib}</script>'
            f'<script type="module">{core.MERMAID_INIT}</script></body></html>')
    return _pages_to_png(page, chrome, f"{name}-diagrams")


def _cover_image(front: dict, chrome: str, name: str) -> bytes | None:
    pages = _pages_to_png(core.cover_html(front), chrome, f"{name}-cover",
                          wait_ms=4000)
    return pages[0] if pages else None


def _load_image(src: str) -> bytes | None:
    if src.startswith("data:"):
        _, _, payload = src.partition(",")
        try:
            return base64.b64decode(payload)
        except Exception:
            return None
    if src.startswith(("http://", "https://")):
        try:
            req = urllib.request.Request(src, headers={"User-Agent": "a2pdf"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read(8 * 1024 * 1024)
        except Exception:
            return None
    path = pathlib.Path(src)
    return path.read_bytes() if path.is_file() else None


# --------------------------------------------------------------------------- #
# Оформление документа
# --------------------------------------------------------------------------- #

def _shade(element, color: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    element.append(shd)


def _left_bar(paragraph, color: str) -> None:
    """Цветная линия слева — как в PDF у кода и цитат."""
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), "18")
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), color)
    borders.append(left)
    paragraph._p.get_or_add_pPr().append(borders)


def _rule(paragraph) -> None:
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "E1E4EA")
    borders.append(bottom)
    paragraph._p.get_or_add_pPr().append(borders)


def _page_field(paragraph) -> None:
    """Номер страницы: Word считает его сам."""
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            mark = OxmlElement("w:fldChar")
            mark.set(qn("w:fldCharType"), kind)
            run._r.append(mark)
        else:
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = f" {text} "
            run._r.append(instr)
    run.font.name = MONO
    run.font.size = Pt(8)
    run.font.color.rgb = NAVY


INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")


def _runs(paragraph, text: str, size: float = 10.5,
          color: RGBColor = INK, bold: bool = False) -> None:
    """Разбирает **жирный**, *курсив* и `код` в отдельные run-ы."""
    for part in INLINE_RE.split(text):
        if not part:
            continue
        run = paragraph.add_run()
        if part.startswith("**") and part.endswith("**"):
            run.text, run.bold = part[2:-2], True
        elif part.startswith("`") and part.endswith("`"):
            run.text = part[1:-1]
            run.font.name = MONO
            run.font.size = Pt(size - 1.5)
            run.font.color.rgb = NAVY
        elif part.startswith("*") and part.endswith("*"):
            run.text, run.italic = part[1:-1], True
        else:
            run.text = part
        if run.font.name is None:
            run.font.name = FONT
        if run.font.size is None:
            run.font.size = Pt(size)
        if run.font.color.rgb is None:
            run.font.color.rgb = color
        if bold:
            run.bold = True


def _setup_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25
    rpr = normal.element.get_or_add_rPr().get_or_add_rFonts()
    rpr.set(qn("w:eastAsia"), FONT)

    for name, size in (("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 11.5)):
        style = document.styles[name]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = NAVY
        style.paragraph_format.space_before = Pt(14 if size > 12 else 10)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True


def _runners(document: Document, front: dict) -> None:
    section = document.sections[-1]
    header = section.header.paragraphs[0]
    header.text = ""
    mark = header.add_run("A2")
    mark.font.name, mark.font.size, mark.bold = FONT, Pt(8), True
    mark.font.color.rgb = NAVY
    data = header.add_run("DATA")
    data.font.name, data.font.size, data.bold = FONT, Pt(8), True
    data.font.color.rgb = BLUE
    right = header.add_run("\t" + str(front.get("header", front.get("title", ""))))
    right.font.name, right.font.size = FONT, Pt(8)
    right.font.color.rgb = GRAY
    _rule(header)

    footer = section.footer.paragraphs[0]
    footer.text = ""
    left = footer.add_run(str(front.get("footer", "")) + "\t")
    left.font.name, left.font.size = FONT, Pt(8)
    left.font.color.rgb = GRAY
    _page_field(footer)


# --------------------------------------------------------------------------- #
# Сборка
# --------------------------------------------------------------------------- #

def write_docx(blocks: list[tuple], front: dict, out_path: pathlib.Path,
               chrome: str | None = None, name: str = "document") -> pathlib.Path:
    """Собирает .docx и возвращает путь к файлу."""
    core.ensure_assets(quiet=True)
    chrome = chrome or core.find_chrome()
    front = dict(front)
    if not front.get("title"):
        first = next((b[1] for b in blocks if b[0] == "h1"), name)
        front["title"] = re.sub(r"^Задание\s+\d+\.\s*", "", str(first))

    document = Document()
    _setup_styles(document)

    with_cover = str(front.get("cover", "true")).lower() not in ("false", "0", "no")
    cover_png = _cover_image(front, chrome, name) if with_cover else None

    section = document.sections[0]
    if cover_png:
        for attr in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
            setattr(section, attr, Cm(0))
        document.add_paragraph().add_run().add_picture(
            io.BytesIO(cover_png), width=section.page_width)
        document.add_section(WD_SECTION.NEW_PAGE)
        section = document.sections[-1]

    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2)
    section.left_margin = section.right_margin = Cm(2)
    _runners(document, front)

    diagrams = _diagram_images([b[1] for b in blocks if b[0] == "mermaid"],
                               chrome, name)
    diagram_no = 0
    numbered = str(front.get("numbered", "true")).lower() not in ("false", "0", "no")
    section_no = 0
    content_width = section.page_width - section.left_margin - section.right_margin

    for block in blocks:
        kind = block[0]

        if kind == "h1":
            continue
        if kind == "h2":
            section_no += 1
            prefix = f"{section_no:02d}   " if numbered else ""
            paragraph = document.add_paragraph(style="Heading 1")
            if prefix:
                run = paragraph.add_run(prefix)
                run.font.name, run.font.size = MONO, Pt(10)
                run.font.color.rgb = BLUE
            _runs(paragraph, block[1], size=18, color=NAVY, bold=True)
        elif kind in ("h3", "h4"):
            paragraph = document.add_paragraph(style="Heading 3")
            _runs(paragraph, block[1], size=11.5, color=INK, bold=True)
        elif kind == "p":
            _runs(document.add_paragraph(), block[1])
        elif kind in ("ul", "ol"):
            style = "List Bullet" if kind == "ul" else "List Number"
            for item in block[1]:
                _runs(document.add_paragraph(style=style), item)
        elif kind == "code":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.4)
            _shade(paragraph._p.get_or_add_pPr(), "F7F8FA")
            _left_bar(paragraph, "1FA8FC")
            run = paragraph.add_run(block[2])
            run.font.name, run.font.size = MONO, Pt(8.5)
            run.font.color.rgb = INK
        elif kind == "note":
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Cm(0.4)
            _shade(paragraph._p.get_or_add_pPr(), "FFF8EC")
            _left_bar(paragraph, "FF9F1C")
            _runs(paragraph, block[1])
        elif kind == "cap":
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _runs(paragraph, block[1], size=8.5, color=GRAY)
        elif kind == "hr":
            _rule(document.add_paragraph())
        elif kind == "table":
            head, rows = block[1], block[2]
            table = document.add_table(rows=1, cols=len(head))
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for cell, title in zip(table.rows[0].cells, head):
                _shade(cell._tc.get_or_add_tcPr(), "0B2660")
                cell.paragraphs[0].text = ""
                run = cell.paragraphs[0].add_run(re.sub(r"[*`]", "", str(title)))
                run.font.name, run.font.size, run.bold = FONT, Pt(9), True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            for index, row in enumerate(rows):
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    if index % 2:
                        _shade(cell._tc.get_or_add_tcPr(), "F7F8FA")
                    cell.paragraphs[0].text = ""
                    _runs(cell.paragraphs[0], str(value), size=9)
            document.add_paragraph()
        elif kind == "mermaid":
            if diagram_no < len(diagrams):
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                paragraph.add_run().add_picture(
                    io.BytesIO(diagrams[diagram_no]), width=content_width)
                diagram_no += 1
        elif kind == "image":
            data = _load_image(block[1])
            if data:
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                try:
                    paragraph.add_run().add_picture(io.BytesIO(data),
                                                    width=content_width)
                except Exception:
                    pass

    document.core_properties.title = str(front["title"])
    document.core_properties.author = "A2DATA"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path
