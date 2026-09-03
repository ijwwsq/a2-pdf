"""HTML в блоки документа: общий кусок для .docx (через mammoth) и веб-страниц.

Разбирается только то, что осмысленно переносить в PDF: заголовки, абзацы,
списки, таблицы, код, цитаты и картинки. Оформление источника отбрасывается —
документ пересобирается по брендбуку.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

INLINE = {"strong": ("**", "**"), "b": ("**", "**"),
          "em": ("*", "*"), "i": ("*", "*"),
          "code": ("`", "`"), "kbd": ("`", "`")}
HEADINGS = {"h1": "h1", "h2": "h2", "h3": "h3",
            "h4": "h4", "h5": "h4", "h6": "h4"}
SKIP = {"script", "style", "noscript", "svg", "head", "nav", "aside",
        "iframe", "form", "button", "select", "template"}
BLOCK_END = {"p", "div", "section", "article", "figcaption"}
# у этих тегов нет закрывающего — иначе счётчик пропуска никогда не сойдётся
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


class HtmlBlocks(HTMLParser):
    """Собирает блоки в том же формате, что и парсер markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple] = []
        self._text: list[str] = []
        self._skip_depth = 0
        self._pre = False
        self._list: list[str] | None = None
        self._list_kind = "ul"
        self._row: list[str] | None = None
        self._table: list[list[str]] | None = None
        self._heading: str | None = None

    def _take(self) -> str:
        raw = "".join(self._text)
        self._text = []
        return raw if self._pre else re.sub(r"\s+", " ", raw).strip()

    def _emit(self, kind: str) -> None:
        text = self._take()
        if text:
            self.blocks.append((kind, text))

    def handle_starttag(self, tag, attrs):
        if self._skip_depth or tag in SKIP:
            if tag not in VOID:
                self._skip_depth += 1
            return
        attrs = dict(attrs)
        if tag in INLINE:
            self._text.append(INLINE[tag][0])
        elif tag in HEADINGS:
            self._take()
            self._heading = HEADINGS[tag]
        elif tag == "img":
            src = attrs.get("src", "")
            if src and not src.startswith("data:image/svg"):
                self.blocks.append(("image", src))
        elif tag == "br":
            self._text.append(" ")
        elif tag == "hr":
            self.blocks.append(("hr",))
        elif tag == "pre":
            self._take()
            self._pre = True
        elif tag in ("ul", "ol"):
            self._list = []
            self._list_kind = "ol" if tag == "ol" else "ul"
        elif tag == "table":
            self._table = []
        elif tag == "tr":
            self._row = []

    def handle_endtag(self, tag):
        if self._skip_depth:
            if tag not in VOID:
                self._skip_depth -= 1
            return
        if tag in INLINE:
            self._text.append(INLINE[tag][1])
        elif tag in HEADINGS:
            self._emit(self._heading or "h2")
            self._heading = None
        elif tag == "pre":
            text = self._take().strip("\n")
            self._pre = False
            if text:
                self.blocks.append(("code", "", text))
        elif tag == "blockquote":
            self._emit("note")
        elif tag == "li":
            text = self._take()
            if text:
                if self._list is None:
                    self._list, self._list_kind = [], "ul"
                self._list.append(text)
        elif tag in ("ul", "ol"):
            if self._list:
                self.blocks.append((self._list_kind, self._list))
            self._list = None
        elif tag in ("td", "th"):
            if self._row is not None:
                self._row.append(self._take())
        elif tag == "tr":
            if self._table is not None and any(c for c in self._row or []):
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table:
                head, *body = self._table
                self.blocks.append(("table", head, body))
            self._table = None
        elif tag in BLOCK_END and self._list is None and self._table is None:
            self._emit("p")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._pre or data.strip() or self._text:
            self._text.append(data)


def html_to_blocks(markup: str) -> list[tuple]:
    reader = HtmlBlocks()
    reader.feed(markup)
    reader.close()
    reader._emit("p")
    return reader.blocks


class _Subtree(HTMLParser):
    """Вырезает первое поддерево, подходящее под tag или класс."""

    def __init__(self, tag: str | None, css_class: str | None) -> None:
        super().__init__(convert_charrefs=False)
        self.tag, self.css_class = tag, css_class
        self.out: list[str] = []
        self._depth = 0
        self.found = False

    def _matches(self, tag: str, attrs: dict) -> bool:
        if self.tag and tag != self.tag:
            return False
        if self.css_class:
            classes = (attrs.get("class") or "").split()
            return self.css_class in classes
        return True

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if self._depth == 0 and not self.found and self._matches(tag, attrs_d):
            self.found = True
            self._depth = 1
            return
        if self._depth:
            if tag not in VOID:
                self._depth += 1
            self.out.append(self.get_starttag_text() or f"<{tag}>")

    def handle_startendtag(self, tag, attrs):
        if self._depth:
            self.out.append(self.get_starttag_text() or f"<{tag}/>")

    def handle_endtag(self, tag):
        if not self._depth:
            return
        if tag in VOID:
            return
        self._depth -= 1
        if self._depth:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self._depth:
            self.out.append(data)

    def handle_entityref(self, name):
        if self._depth:
            self.out.append(f"&{name};")

    def handle_charref(self, name):
        if self._depth:
            self.out.append(f"&#{name};")


def extract(markup: str, tag: str | None = None,
            css_class: str | None = None) -> str:
    """Возвращает содержимое первого подходящего элемента или пустую строку."""
    parser = _Subtree(tag, css_class)
    parser.feed(markup)
    parser.close()
    return "".join(parser.out) if parser.found else ""
