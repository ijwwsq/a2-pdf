"""Чтение .docx: mammoth превращает документ в HTML, дальше HTML разбирается
в те же блоки, что и markdown, — так docx и md идут по одному конвейеру.

Поддерживаются заголовки, абзацы, жирный и курсив, моноширинный текст,
списки, таблицы, цитаты и картинки (встраиваются как data-URI).
"""
from __future__ import annotations

import html
import io
import re
from html.parser import HTMLParser

import mammoth

INLINE_TAGS = {"strong": ("**", "**"), "b": ("**", "**"),
               "em": ("*", "*"), "i": ("*", "*"),
               "code": ("`", "`")}
HEADINGS = {"h1": "h1", "h2": "h2", "h3": "h3", "h4": "h4",
            "h5": "h4", "h6": "h4"}


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple] = []
        self._text: list[str] = []
        self._stack: list[str] = []
        self._list: list[str] | None = None
        self._list_kind = "ul"
        self._row: list[str] | None = None
        self._table: list[list[str]] | None = None

    # --- вспомогательное ---------------------------------------------------
    def _flush_text(self) -> str:
        text = re.sub(r"\s+", " ", "".join(self._text)).strip()
        self._text = []
        return text

    def _emit(self, kind: str) -> None:
        text = self._flush_text()
        if text:
            self.blocks.append((kind, text))

    # --- разбор ------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in INLINE_TAGS:
            self._text.append(INLINE_TAGS[tag][0])
        elif tag == "img":
            src = attrs.get("src", "")
            if src:
                self.blocks.append(("image", src))
        elif tag == "br":
            self._text.append(" ")
        elif tag in ("ul", "ol"):
            self._list = []
            self._list_kind = "ol" if tag == "ol" else "ul"
        elif tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []
        self._stack.append(tag)

    def handle_endtag(self, tag):
        if self._stack and tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

        if tag in INLINE_TAGS:
            self._text.append(INLINE_TAGS[tag][1])
        elif tag in HEADINGS:
            self._emit(HEADINGS[tag])
        elif tag == "p":
            if self._list is None and self._table is None:
                self._emit("p")
        elif tag == "blockquote":
            self._emit("note")
        elif tag == "pre":
            text = self._flush_text()
            if text:
                self.blocks.append(("code", "", text))
        elif tag == "li":
            text = self._flush_text()
            if text and self._list is not None:
                self._list.append(text)
        elif tag in ("ul", "ol"):
            if self._list:
                self.blocks.append((self._list_kind, self._list))
            self._list = None
        elif tag in ("td", "th"):
            if self._row is not None:
                self._row.append(self._flush_text())
        elif tag == "tr":
            if self._table is not None and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table:
                head, *body = self._table
                self.blocks.append(("table", head, body))
            self._table = None

    def handle_data(self, data):
        if data.strip() or self._text:
            self._text.append(data)


def docx_to_blocks(data: bytes) -> tuple[list[tuple], dict]:
    """Возвращает блоки документа и настройки обложки, выведенные из текста."""
    result = mammoth.convert_to_html(io.BytesIO(data))
    reader = _Reader()
    reader.feed(result.value)
    reader.close()
    blocks = reader.blocks

    front: dict = {}
    for kind, *rest in blocks:
        if kind == "h1":
            front["title"] = html.unescape(str(rest[0]))
            break
    return blocks, front


def messages(data: bytes) -> list[str]:
    """Замечания конвертера — например, о неподдерживаемых стилях."""
    return [m.message for m in mammoth.convert_to_html(io.BytesIO(data)).messages]
