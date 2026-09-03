"""Кладёт настоящий логотип бренда в assets/logo.

Логотип берётся из брендбука картинкой (PNG с прозрачностью), обрезается
по краю рисунка и сохраняется под именем, которое ждёт вёрстка.

    python tools/import_logo.py becloud путь/к/белой.png путь/к/цветной.png
"""
from __future__ import annotations

import pathlib
import sys

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "a2pdf" / "assets" / "logo"


def trim(source: pathlib.Path, target: pathlib.Path, padding: int = 4) -> None:
    """Обрезает прозрачные поля, чтобы логотип занимал всю картинку."""
    pixmap = pymupdf.Pixmap(str(source))
    if not pixmap.alpha:
        pixmap.save(target)
        return
    width, height, n = pixmap.width, pixmap.height, pixmap.n
    data = pixmap.samples
    left, right, top, bottom = width, 0, height, 0
    for y in range(height):
        row = y * width * n
        for x in range(width):
            if data[row + x * n + n - 1] > 8:      # альфа-канал
                left, right = min(left, x), max(right, x)
                top, bottom = min(top, y), max(bottom, y)
    if right <= left or bottom <= top:
        pixmap.save(target)
        return
    box = pymupdf.IRect(max(0, left - padding), max(0, top - padding),
                        min(width, right + padding + 1),
                        min(height, bottom + padding + 1))
    pixmap.set_origin(0, 0)
    cropped = pymupdf.Pixmap(pixmap, pixmap.width, pixmap.height, box)
    cropped.save(target)


def main(argv: list[str]) -> None:
    if len(argv) != 4:
        raise SystemExit(__doc__)
    brand, white, color = argv[1], pathlib.Path(argv[2]), pathlib.Path(argv[3])
    OUT.mkdir(parents=True, exist_ok=True)
    for source, tone in ((white, "white"), (color, "color")):
        target = OUT / f"{brand}-{tone}.png"
        trim(source, target)
        print(f"{target.name}: {pymupdf.Pixmap(str(target)).width}px")
    for tone in ("white", "color"):
        svg = OUT / f"{brand}-{tone}.svg"
        svg.unlink(missing_ok=True)    # растровый логотип заменяет рисованный


if __name__ == "__main__":
    main(sys.argv)
