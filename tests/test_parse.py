"""Разбор markdown: что из разметки во что превращается."""
import pytest

from a2pdf import brands, core


def kinds(blocks):
    return [b[0] for b in blocks]


def test_headings_and_paragraph():
    blocks = core.parse("# Раз\n\nтекст\n\n## Два\n")
    assert kinds(blocks) == ["h1", "p", "h2"]
    assert blocks[1][1] == "текст"


def test_paragraph_joins_wrapped_lines():
    blocks = core.parse("первая\nвторая\n")
    assert blocks == [("p", "первая вторая")]


def test_lists():
    blocks = core.parse("- раз\n- два\n\n1. один\n2. два\n")
    assert kinds(blocks) == ["ul", "ol"]
    assert blocks[0][1] == ["раз", "два"]
    assert blocks[1][1] == ["один", "два"]


def test_list_item_continuation():
    blocks = core.parse("- начало\n  продолжение\n")
    assert blocks[0][1] == ["начало продолжение"]


def test_table_drops_separator_row():
    blocks = core.parse("| a | b |\n| --- | --- |\n| 1 | 2 |\n")
    kind, head, body = blocks[0]
    assert kind == "table"
    assert head == ["a", "b"]
    assert body == [["1", "2"]]


def test_code_and_mermaid():
    md = "```python\nx = 1\n```\n\n```mermaid\nflowchart LR\n  A --> B\n```\n"
    blocks = core.parse(md)
    assert kinds(blocks) == ["code", "mermaid"]
    assert blocks[0][1] == "python"
    assert "flowchart" in blocks[1][1]


def test_mermaid_can_be_dropped():
    md = "```mermaid\nflowchart LR\n```\n"
    assert core.parse(md, keep_mermaid=False) == []


def test_quote_and_rule_and_image():
    blocks = core.parse("> важно\n\n---\n\n![](pic.png)\n")
    assert kinds(blocks) == ["note", "hr", "image"]
    assert blocks[2][1] == "pic.png"


def test_front_matter():
    front, body = core.split_front_matter("---\ntitle: Отчёт\n---\n\n# Раз\n")
    assert front["title"] == "Отчёт"
    assert body.startswith("# Раз")


def test_front_matter_absent():
    front, body = core.split_front_matter("# Раз\n")
    assert front == {}
    assert body.startswith("# Раз")


def test_inline_strips_links_and_images():
    assert core.inline("[текст](http://x)") == "текст"
    assert core.inline("![](pic.png)") == ""
    assert "<code>x</code>" in core.inline("`x`")
    assert "<strong>x</strong>" in core.inline("**x**")


def test_inline_escapes_html():
    assert "<script>" not in core.inline("<script>alert(1)</script>")


def test_unclosed_fence_does_not_hang():
    blocks = core.parse("```python\nx = 1\n")
    assert kinds(blocks) == ["code"]


def test_table_with_ragged_rows_renders():
    blocks = core.parse("| a | b | c |\n| --- | --- | --- |\n| 1 |\n")
    html = core.render(blocks, brands.get("a2data"))
    assert "<table" in html


@pytest.mark.parametrize("value, atomic", [
    ("8683040", True), ("Ботаныч", True), ("два слова", False),
    ("a" * 30, False)])
def test_atomic_cells(value, atomic):
    assert (core.ATOMIC.match(value) is not None) is atomic
