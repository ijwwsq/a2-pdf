"""Готовит логотип A2DATA как графику.

Буквы вордмарка переводятся в кривые из фирменного Inter, поэтому логотип
выглядит одинаково везде и не зависит от установленных в системе шрифтов.
На выходе — SVG (для веба и PDF) и PNG (для Word).

    python tools/make_logo.py
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "a2pdf" / "assets"
OUT = ASSETS / "logo"
FONT = ASSETS / "Inter-ExtraBold.ttf"

NAVY = "#0B2660"
BLUE = "#1FA8FC"
WHITE = "#FFFFFF"
TRACKING = -0.045   # плотная посадка букв, как в брендбуке


def word_path(font: TTFont, text: str, scale: float, start: float) -> tuple[str, float]:
    """Возвращает SVG-путь слова и ширину в единицах шрифта."""
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap()
    units = font["head"].unitsPerEm
    pen = SVGPathPen(glyph_set)
    cursor = start
    for index, char in enumerate(text):
        name = cmap.get(ord(char))
        if not name:
            continue
        glyph = glyph_set[name]
        pen.moveTo  # noqa: B018 — pen требует прогрева атрибутов
        from fontTools.pens.transformPen import TransformPen

        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, 0)))
        cursor += glyph.width * scale + TRACKING * units * scale
    return pen.getCommands(), cursor


def build_svg(color_a2: str, color_data: str) -> str:
    font = TTFont(FONT)
    units = font["head"].unitsPerEm
    scale = 1.0
    a2, after_a2 = word_path(font, "A2", scale, 0)
    data, end = word_path(font, "DATA", scale, after_a2)
    height = units * 1.0
    top = font["hhea"].ascender * 0.78
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 {-top} {end:.0f} {height:.0f}" '
            f'role="img" aria-label="A2DATA">'
            f'<path d="{a2}" fill="{color_a2}"/>'
            f'<path d="{data}" fill="{color_data}"/></svg>')


def to_png(svg_path: pathlib.Path, png_path: pathlib.Path, width: int) -> None:
    """Растеризует SVG браузером: он уже есть в проекте для печати PDF."""
    sys.path.insert(0, str(ROOT))
    from a2pdf import core

    svg = svg_path.read_text(encoding="utf-8")
    html = (f'<!doctype html><meta charset="utf-8">'
            f'<style>@page{{size:{width}px {width // 3}px;margin:0}}'
            f'body{{margin:0}}svg{{width:{width}px;display:block}}</style>'
            f'{svg}')
    core.TMP.mkdir(parents=True, exist_ok=True)
    html_path = core.TMP / "logo.html"
    pdf_path = core.TMP / "logo.pdf"
    html_path.write_text(html, encoding="utf-8")
    try:
        core.print_pdf(html_path, pdf_path, core.find_chrome(), 3000)
        import pymupdf

        with pymupdf.open(pdf_path) as doc:
            page = doc[0]
            pixmap = page.get_pixmap(dpi=300, alpha=True)
            pixmap.save(png_path)
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    variants = {
        "logo-color.svg": (NAVY, BLUE),      # на светлом фоне
        "logo-white.svg": (WHITE, BLUE),     # на синем и на фото
    }
    for filename, (a2, data) in variants.items():
        path = OUT / filename
        path.write_text(build_svg(a2, data), encoding="utf-8")
        to_png(path, path.with_suffix(".png"), width=1200)
        print(f"{path.name} и {path.with_suffix('.png').name}")


if __name__ == "__main__":
    main()
