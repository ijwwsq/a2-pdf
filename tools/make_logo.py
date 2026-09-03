"""Готовит логотипы брендов как графику.

Буквы вордмарка переводятся в кривые из фирменного шрифта, поэтому логотип
выглядит одинаково везде и не зависит от установленных в системе шрифтов.
На выходе — SVG (для веба и PDF) и PNG (для Word).

    python tools/make_logo.py
"""
from __future__ import annotations

import pathlib
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from a2pdf import brands  # noqa: E402

ASSETS = ROOT / "a2pdf" / "assets"
OUT = ASSETS / "logo"
FONTS = ASSETS / "fonts"

# чем набирать вордмарк каждого бренда и как делить его на две части
WORDMARKS = {
    "a2data":  {"font": "Inter-ExtraBold.ttf", "parts": ("A2", "DATA"),
                "tracking": -0.045},
    "becloud": {"font": "Oswald-SemiBold.ttf", "parts": ("BeCloud", ".AI"),
                "tracking": 0.0},
}


def word_path(font: TTFont, text: str, cursor: float,
              tracking: float) -> tuple[str, float]:
    """SVG-путь слова и позиция, где заканчивается набор."""
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    units = font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    for char in text:
        name = cmap.get(ord(char))
        if not name:
            continue
        glyph = glyphs[name]
        glyph.draw(TransformPen(pen, (1, 0, 0, -1, cursor, 0)))
        cursor += glyph.width + tracking * units
    return pen.getCommands(), cursor


def build_svg(spec: dict, first: str, second: str) -> str:
    font = TTFont(FONTS / spec["font"] if (FONTS / spec["font"]).is_file()
                  else ASSETS / spec["font"])
    units = font["head"].unitsPerEm
    head, cursor = word_path(font, spec["parts"][0], 0, spec["tracking"])
    tail, end = word_path(font, spec["parts"][1], cursor, spec["tracking"])
    top = font["hhea"].ascender * 0.78
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 {-top:.0f} {end:.0f} {units:.0f}" role="img">'
            f'<path d="{head}" fill="{first}"/>'
            f'<path d="{tail}" fill="{second}"/></svg>')


def to_png(svg_path: pathlib.Path, png_path: pathlib.Path, width: int) -> None:
    """Растеризует SVG браузером — он уже есть в проекте для печати PDF."""
    from a2pdf import core
    import pymupdf

    svg = svg_path.read_text(encoding="utf-8")
    html = (f'<!doctype html><meta charset="utf-8">'
            f'<style>@page{{size:{width}px {width // 3}px;margin:0}}'
            f'body{{margin:0}}svg{{width:{width}px;display:block}}</style>{svg}')
    core.TMP.mkdir(parents=True, exist_ok=True)
    html_path = core.TMP / "logo.html"
    pdf_path = core.TMP / "logo.pdf"
    html_path.write_text(html, encoding="utf-8")
    try:
        core.print_pdf(html_path, pdf_path, core.find_chrome(), 3000)
        with pymupdf.open(pdf_path) as doc:
            doc[0].get_pixmap(dpi=300, alpha=True).save(png_path)
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for brand in brands.BRANDS.values():
        spec = WORDMARKS.get(brand.logo)
        if not spec:
            continue
        variants = {
            f"{brand.logo}-color.svg": (brand.color("brand"),
                                        brand.color("accent")),
            f"{brand.logo}-white.svg": ("#FFFFFF", brand.color("accent")),
        }
        for filename, (first, second) in variants.items():
            path = OUT / filename
            path.write_text(build_svg(spec, first, second), encoding="utf-8")
            to_png(path, path.with_suffix(".png"), width=1200)
            print(path.name)


if __name__ == "__main__":
    main()
