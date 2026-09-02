"""Чтение .docx: mammoth превращает документ в HTML, дальше работает общий
HTML-разборщик — так docx и markdown идут по одному конвейеру.

Поддерживаются заголовки, жирный и курсив, списки, таблицы, цитаты
и картинки (mammoth отдаёт их как data-URI).
"""
from __future__ import annotations

import io

import mammoth

from .html_reader import html_to_blocks


def docx_to_blocks(data: bytes) -> tuple[list[tuple], dict]:
    """Возвращает блоки документа и настройки обложки, выведенные из текста."""
    markup = mammoth.convert_to_html(io.BytesIO(data)).value
    blocks = html_to_blocks(markup)
    front: dict = {}
    for block in blocks:
        if block[0] == "h1":
            front["title"] = str(block[1])
            break
    return blocks, front


def messages(data: bytes) -> list[str]:
    """Замечания конвертера — например, о неподдерживаемых стилях."""
    return [m.message for m in mammoth.convert_to_html(io.BytesIO(data)).messages]
