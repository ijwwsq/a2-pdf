"""Сборка .docx в оформлении A2DATA из тех же блоков, что и PDF.

Word собирается нативными средствами: обложка, колонтитулы, заголовки, списки,
таблицы, код и цитаты — редактируемый текст, а не картинки. Оформление
сдержанное и деловое: фирменные цвета, логотип, тонкие линии, без фонов
и фотографий (вся визуальная часть живёт в PDF).

Картинками вставляются только диаграммы mermaid — их Word рисовать не умеет.
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
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt, RGBColor

from . import core

NAVY = RGBColor(0x0B, 0x26, 0x60)
BLUE = RGBColor(0x1F, 0xA8, 0xFC)
BLUE_DARK = RGBColor(0x12, 0x89, 0xD5)
AMBER = RGBColor(0xB8, 0x6A, 0x06)
INK = RGBColor(0x11, 0x17, 0x22)
GRAY = RGBColor(0x6B, 0x72, 0x80)
LIGHT = RGBColor(0x9C, 0xA3, 0xAF)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
# В Word нельзя рассчитывать на фирменные шрифты: если Inter не установлен,
# документ подставит засечки. Берём системные, ближайшие по духу к брендбуку.
FONT = "Segoe UI"
MONO = "Consolas"
DPI = 150

HEX_NAVY = "0B2660"
HEX_BLUE = "1FA8FC"
HEX_AMBER = "FF9F1C"
HEX_LINE = "E1E4EA"
HEX_SOFT = "F7F8FA"
HEX_AMBER_BG = "FFF8EC"


# --------------------------------------------------------------------------- #
# Мелкие помощники для XML, которого нет в python-docx
# --------------------------------------------------------------------------- #

def _shade(element, color: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), color)
    element.append(shd)


def _borders(paragraph, **sides) -> None:
    """Границы абзаца: _borders(p, left=('1FA8FC', 18), bottom=('E1E4EA', 6))."""
    pbdr = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        if side not in sides:
            continue
        color, size = sides[side]
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), "6")
        node.set(qn("w:color"), color)
        pbdr.append(node)
    paragraph._p.get_or_add_pPr().append(pbdr)


def _cell_borders(cell, color: str = HEX_LINE, size: int = 4,
                  sides: tuple[str, ...] = ("top", "bottom")) -> None:
    props = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        node = OxmlElement(f"w:{side}")
        if side in sides:
            node.set(qn("w:val"), "single")
            node.set(qn("w:sz"), str(size))
            node.set(qn("w:color"), color)
        else:
            node.set(qn("w:val"), "nil")
        borders.append(node)
    props.append(borders)


def _repeat_header(row) -> None:
    """Шапка таблицы повторяется на каждой странице."""
    props = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    props.append(header)


def _field(paragraph, code: str, size: float = 8,
           color: RGBColor = NAVY, mono: bool = True):
    """Поле Word — например номер страницы, который считается сам."""
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {code} "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    run.font.name = MONO if mono else FONT
    run.font.size = Pt(size)
    run.font.color.rgb = color
    return run


def _tabs(paragraph, positions) -> None:
    """Табстопы: [(см, 'right'|'center'|'left'), …].

    Свои позиции задаём с нуля: у стиля колонтитула уже есть центр и право,
    иначе текст уезжает к ближайшей чужой позиции."""
    paragraph.paragraph_format.tab_stops.clear_all()
    pPr = paragraph._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    for position, align in positions:
        node = OxmlElement("w:tab")
        node.set(qn("w:val"), align)
        node.set(qn("w:pos"), str(int(Cm(position).twips)))
        tabs.append(node)
    pPr.append(tabs)


def _spacing(paragraph, before: float = 0, after: float = 0,
             line: float | None = None) -> None:
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    if line:
        fmt.line_spacing = line


# --------------------------------------------------------------------------- #
# Текст
# --------------------------------------------------------------------------- #

INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")


def _style_run(run, size: float, color: RGBColor, name: str = FONT) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = color
    rpr = run._r.get_or_add_rPr().get_or_add_rFonts()
    rpr.set(qn("w:eastAsia"), name)
    rpr.set(qn("w:cs"), name)


def _runs(paragraph, text: str, size: float = 10.5,
          color: RGBColor = INK, bold: bool = False) -> None:
    """Разбирает **жирный**, *курсив* и `код` в отдельные run-ы."""
    for part in INLINE_RE.split(str(text)):
        if not part:
            continue
        run = paragraph.add_run()
        if part.startswith("**") and part.endswith("**"):
            run.text = part[2:-2]
            run.bold = True
            _style_run(run, size, color)
        elif part.startswith("`") and part.endswith("`"):
            run.text = part[1:-1]
            _style_run(run, size - 1.5, NAVY, MONO)
        elif part.startswith("*") and part.endswith("*"):
            run.text = part[1:-1]
            run.italic = True
            _style_run(run, size, color)
        else:
            run.text = part
            _style_run(run, size, color)
        if bold:
            run.bold = True


def _plain(text: str) -> str:
    return re.sub(r"[*`]", "", str(text))


# --------------------------------------------------------------------------- #
# Диаграммы: их рисует браузер, Word получает картинку
# --------------------------------------------------------------------------- #

def _content_box(page) -> pymupdf.Rect:
    """Прямоугольник вокруг нарисованного — чтобы не тащить поля страницы."""
    box = pymupdf.Rect()
    for drawing in page.get_drawings():
        box |= drawing["rect"]
    for word in page.get_text("words"):
        box |= pymupdf.Rect(word[:4])
    if box.is_empty or box.is_infinite:
        return page.rect
    box += (-6, -6, 6, 6)          # немного воздуха вокруг схемы
    return box & page.rect


def _pages_to_png(html_text: str, chrome: str, name: str,
                  wait_ms: int = 15000,
                  crop: bool = False) -> list[tuple[bytes, float]]:
    """Возвращает картинки страниц и соотношение сторон каждой."""
    core.TMP.mkdir(parents=True, exist_ok=True)
    html_path = core.TMP / f"{name}.html"
    pdf_path = core.TMP / f"{name}.pdf"
    html_path.write_text(html_text, encoding="utf-8")
    try:
        core.print_pdf(html_path, pdf_path, chrome, wait_ms)
        images = []
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                clip = _content_box(page) if crop else None
                pixmap = page.get_pixmap(dpi=DPI, clip=clip)
                images.append((pixmap.tobytes("png"),
                               pixmap.height / max(pixmap.width, 1)))
        return images
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def _diagram_images(sources: list[str], chrome: str,
                    name: str) -> list[tuple[bytes, float]]:
    if not sources:
        return []
    fonts = (core.ASSETS / "fonts.css").read_text(encoding="utf-8")
    lib = (core.ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
    body = "".join(
        '<div class="page"><div class="dg dg-mermaid"><pre class="mermaid">'
        f'{html_mod.escape(src)}</pre></div></div>' for src in sources)
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<style>{fonts}</style><style>{core.BODY_CSS}'
            '@page{size:A4;margin:8mm}'
            '.page{break-after:page;display:flex;align-items:center;'
            'justify-content:center;height:281mm}'
            '.dg{border:0;background:none;margin:0;padding:0;width:100%}'
            '.dg-mermaid svg{max-height:275mm}'
            f'</style></head><body>{body}'
            f'<script>{lib}</script>'
            f'<script type="module">{core.MERMAID_INIT}</script></body></html>')
    return _pages_to_png(page, chrome, f"{name}-diagrams", crop=True)


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
# Стили, обложка и колонтитулы
# --------------------------------------------------------------------------- #

def _setup_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.line_spacing = 1.3
    rpr = normal.element.get_or_add_rPr().get_or_add_rFonts()
    rpr.set(qn("w:eastAsia"), FONT)
    rpr.set(qn("w:cs"), FONT)

    for name, size, color, before in (
            ("Heading 1", 16, NAVY, 18),
            ("Heading 2", 12.5, NAVY, 14),
            ("Heading 3", 11, INK, 10)):
        style = document.styles[name]
        style.font.name = FONT
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = color
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(5)
        style.paragraph_format.keep_with_next = True

    for name in ("List Bullet", "List Number"):
        style = document.styles[name]
        style.font.name = FONT
        style.font.size = Pt(10.5)
        style.font.color.rgb = INK
        style.paragraph_format.space_after = Pt(3)


def _wordmark(paragraph, width_cm: float = 3.2) -> None:
    """Логотип картинкой из брендбука — не зависит от шрифтов в системе."""
    logo = core.ASSETS / "logo" / "logo-color.png"
    if logo.is_file():
        paragraph.add_run().add_picture(str(logo), width=Cm(width_cm))
        return
    a2 = paragraph.add_run("A2")
    a2.bold = True
    _style_run(a2, width_cm * 3.4, NAVY)
    data = paragraph.add_run("DATA")
    data.bold = True
    _style_run(data, width_cm * 3.4, BLUE)


def _accent_bar(document: Document, width_cm: float = 2.2,
                color: str = HEX_AMBER) -> None:
    """Короткий цветной штрих — тот же акцент, что на обложке PDF."""
    table = document.add_table(rows=1, cols=1)
    table.autofit = False
    cell = table.rows[0].cells[0]
    cell.width = Cm(width_cm)
    _shade(cell._tc.get_or_add_tcPr(), color)
    _cell_borders(cell, sides=())
    paragraph = cell.paragraphs[0]
    paragraph.text = ""
    _spacing(paragraph, after=0, line=0.2)
    run = paragraph.add_run(" ")
    _style_run(run, 2, WHITE)


def _cover(document: Document, front: dict) -> None:
    """Деловая титульная страница: акцент, логотип, заголовок и реквизиты."""
    section = document.sections[0]
    section.top_margin = Cm(2.8)
    section.bottom_margin = Cm(2.4)
    section.left_margin = section.right_margin = Cm(2.4)

    _accent_bar(document)

    logo = document.add_paragraph()
    _spacing(logo, before=10, after=4)
    _wordmark(logo, 3.2)

    rule = document.add_paragraph()
    _spacing(rule, before=0, after=0)
    _borders(rule, bottom=(HEX_LINE, 6))

    spacer = document.add_paragraph()
    _spacing(spacer, after=140)

    kicker_parts = []
    if front.get("index"):
        kicker_parts.append(str(front["index"]))
    if front.get("kicker"):
        kicker_parts.append(str(front["kicker"]))
    if kicker_parts:
        line = document.add_paragraph()
        _spacing(line, after=8)
        run = line.add_run("   ".join(kicker_parts).upper())
        _style_run(run, 8.5, BLUE_DARK, MONO)

    title = document.add_paragraph()
    _spacing(title, after=8, line=1.05)
    run = title.add_run(_plain(front.get("title", "")))
    run.bold = True
    _style_run(run, 30, NAVY)

    if front.get("subtitle"):
        subtitle = document.add_paragraph()
        _spacing(subtitle, after=10, line=1.25)
        _runs(subtitle, str(front["subtitle"]), size=12.5, color=GRAY)

    if front.get("confidential"):
        chip = document.add_paragraph()
        _spacing(chip, before=6, after=0)
        _borders(chip, left=(HEX_AMBER, 18))
        chip.paragraph_format.left_indent = Cm(0.3)
        run = chip.add_run(str(front["confidential"]).upper())
        run.bold = True
        _style_run(run, 8.5, AMBER, MONO)

    meta = list((front.get("meta") or {}).items())
    tail = document.add_paragraph()
    _spacing(tail, after=0)
    tail.paragraph_format.space_before = Pt(120 if not meta else 80)

    if meta:
        table = document.add_table(rows=2, cols=len(meta))
        table.alignment = WD_TABLE_ALIGNMENT.LEFT
        for index, (key, value) in enumerate(meta):
            head_cell = table.rows[0].cells[index]
            head_cell.paragraphs[0].text = ""
            _spacing(head_cell.paragraphs[0], after=2)
            run = head_cell.paragraphs[0].add_run(str(key).upper())
            _style_run(run, 7.5, LIGHT, MONO)
            _cell_borders(head_cell, sides=("top",))

            value_cell = table.rows[1].cells[index]
            value_cell.paragraphs[0].text = ""
            _spacing(value_cell.paragraphs[0], after=0)
            run = value_cell.paragraphs[0].add_run(_plain(value))
            _style_run(run, 10, NAVY, MONO)
            _cell_borders(value_cell, sides=())

    foot = document.add_paragraph()
    _spacing(foot, before=18, after=0)
    _tabs(foot, [(16.2, "right")])
    left = foot.add_run(str(front.get("place", "Almaty, Kazakhstan")))
    _style_run(left, 8, LIGHT, MONO)
    right = foot.add_run("\t" + core.SITE)
    _style_run(right, 8, NAVY, MONO)


def _runner_table(container, width_cm: float):
    """Строка колонтитула: слева логотип или подпись, справа — текст."""
    table = container.add_table(rows=1, cols=2, width=Cm(width_cm))
    table.autofit = False
    table.columns[0].width = Cm(width_cm * 0.5)
    table.columns[1].width = Cm(width_cm * 0.5)
    left, right = table.rows[0].cells
    left.width = Cm(width_cm * 0.5)
    right.width = Cm(width_cm * 0.5)
    for cell in (left, right):
        _cell_borders(cell, sides=())
        cell.paragraphs[0].text = ""
        _spacing(cell.paragraphs[0], after=0)
    right.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return table, left.paragraphs[0], right.paragraphs[0]


def _runners(document: Document, front: dict) -> None:
    """Колонтитулы: логотип и название сверху, подпись и номера страниц снизу."""
    section = document.sections[-1]
    section.is_linked_to_previous = False  # титульная остаётся без колонтитулов
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    section.header_distance = Cm(1.1)
    section.footer_distance = Cm(1.1)
    width = Emu(section.page_width - section.left_margin
                - section.right_margin).cm

    header = section.header
    header.paragraphs[0].text = ""
    _spacing(header.paragraphs[0], after=0, line=0.6)
    table, left, right = _runner_table(header, width)
    _wordmark(left, 1.7)
    caption = right.add_run(_plain(front.get("header", front.get("title", ""))))
    _style_run(caption, 8, GRAY)
    rule = header.add_paragraph()
    _spacing(rule, before=0, after=0, line=0.6)
    _borders(rule, top=(HEX_LINE, 4))

    footer = section.footer
    footer.paragraphs[0].text = ""
    _spacing(footer.paragraphs[0], after=0, line=0.6)
    _borders(footer.paragraphs[0], bottom=(HEX_LINE, 4))
    table, left, right = _runner_table(footer, width)
    signature = left.add_run(_plain(front.get("footer", "")))
    _style_run(signature, 8, LIGHT)
    _field(right, "PAGE")
    separator = right.add_run(" / ")
    _style_run(separator, 8, LIGHT, MONO)
    _field(right, "NUMPAGES", color=LIGHT)


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
    if with_cover:
        _cover(document, front)
        document.add_section(WD_SECTION.NEW_PAGE)

    section = document.sections[-1]
    section.top_margin = Cm(2.4)
    section.bottom_margin = Cm(2.2)
    section.left_margin = section.right_margin = Cm(2.2)
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
            paragraph = document.add_paragraph(style="Heading 1")
            _borders(paragraph, top=(HEX_LINE, 4))
            if numbered:
                number = paragraph.add_run(f"{section_no:02d}   ")
                _style_run(number, 10, BLUE_DARK, MONO)
            _runs(paragraph, block[1], size=16, color=NAVY, bold=True)
        elif kind in ("h3", "h4"):
            paragraph = document.add_paragraph(style="Heading 3")
            _runs(paragraph, block[1], size=11, color=INK, bold=True)
        elif kind == "p":
            _runs(document.add_paragraph(), block[1])
        elif kind in ("ul", "ol"):
            style = "List Bullet" if kind == "ul" else "List Number"
            for item in block[1]:
                paragraph = document.add_paragraph(style=style)
                _runs(paragraph, item)
        elif kind == "code":
            for line in str(block[2]).split("\n"):
                paragraph = document.add_paragraph()
                _spacing(paragraph, after=0, line=1.15)
                paragraph.paragraph_format.left_indent = Cm(0.5)
                _shade(paragraph._p.get_or_add_pPr(), HEX_SOFT)
                _borders(paragraph, left=(HEX_BLUE, 18))
                run = paragraph.add_run(line or " ")
                _style_run(run, 8.5, INK, MONO)
            document.add_paragraph()
        elif kind == "note":
            paragraph = document.add_paragraph()
            _spacing(paragraph, before=4, after=8, line=1.25)
            paragraph.paragraph_format.left_indent = Cm(0.5)
            _shade(paragraph._p.get_or_add_pPr(), HEX_AMBER_BG)
            _borders(paragraph, left=(HEX_AMBER, 18))
            _runs(paragraph, block[1], size=10)
        elif kind == "cap":
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _spacing(paragraph, before=2, after=10)
            run = paragraph.add_run(_plain(block[1]))
            run.italic = True
            _style_run(run, 8.5, GRAY)
        elif kind == "hr":
            paragraph = document.add_paragraph()
            _spacing(paragraph, before=6, after=6)
            _borders(paragraph, bottom=(HEX_LINE, 6))
        elif kind == "table":
            head, rows = block[1], block[2]
            table = document.add_table(rows=1, cols=len(head))
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            _repeat_header(table.rows[0])
            for cell, title in zip(table.rows[0].cells, head):
                _shade(cell._tc.get_or_add_tcPr(), HEX_NAVY)
                _cell_borders(cell, color=HEX_NAVY, sides=())
                cell.paragraphs[0].text = ""
                _spacing(cell.paragraphs[0], before=3, after=3)
                run = cell.paragraphs[0].add_run(_plain(title))
                run.bold = True
                _style_run(run, 9, WHITE)
            for row in rows:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    _cell_borders(cell, sides=("bottom",))
                    cell.paragraphs[0].text = ""
                    _spacing(cell.paragraphs[0], before=3, after=3, line=1.2)
                    _runs(cell.paragraphs[0], str(value), size=9.5)
            document.add_paragraph()
        elif kind == "mermaid":
            if diagram_no < len(diagrams):
                blob, ratio = diagrams[diagram_no]
                width = content_width
                tallest = Cm(17)          # схема не должна занимать весь лист
                if width * ratio > tallest:
                    width = Emu(int(tallest / ratio))
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _spacing(paragraph, before=6, after=4)
                paragraph.add_run().add_picture(io.BytesIO(blob), width=width)
                diagram_no += 1
        elif kind == "image":
            data = _load_image(block[1])
            if data:
                paragraph = document.add_paragraph()
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _spacing(paragraph, before=6, after=6)
                try:
                    paragraph.add_run().add_picture(io.BytesIO(data),
                                                    width=content_width)
                except Exception:
                    pass

    document.core_properties.title = _plain(front["title"])
    document.core_properties.author = "A2DATA"
    document.core_properties.comments = _plain(front.get("subtitle", ""))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(out_path)
    return out_path
