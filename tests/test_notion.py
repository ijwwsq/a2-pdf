"""Разбор ответов Notion — на образцах, без обращения к сети."""
import pytest

from a2pdf import notion


def title(text: str, marks=None) -> list:
    return [[text, marks]] if marks else [[text]]


def block(kind: str, text: str = "", **extra) -> dict:
    node = {"type": kind, "properties": {"title": title(text)} if text else {}}
    node.update(extra)
    return node


def walk(records: dict) -> list[tuple]:
    blocks: list[tuple] = []
    notion._walk_public("page", records, blocks, set())
    return blocks


def test_page_becomes_document_with_heading():
    records = {
        "page": block("page", "Отчёт", content=["a", "b"]),
        "a": block("header", "Раздел"),
        "b": block("text", "Абзац"),
    }
    assert walk(records) == [("h1", "Отчёт"), ("h2", "Раздел"), ("p", "Абзац")]


def test_lists_are_grouped_until_kind_changes():
    records = {
        "page": block("page", "Стр", content=["a", "b", "c", "d"]),
        "a": block("bulleted_list", "раз"),
        "b": block("bulleted_list", "два"),
        "c": block("numbered_list", "первый"),
        "d": block("text", "после"),
    }
    kinds = [b[0] for b in walk(records)]
    assert kinds == ["h1", "ul", "ol", "p"]
    ul = next(b for b in walk(records) if b[0] == "ul")
    assert ul[1] == ["раз", "два"]


def test_marks_become_markdown():
    records = {
        "page": block("page", "Стр", content=["a"]),
        "a": {"type": "text", "properties": {
            "title": [["жирный", [["b"]]], [" и "], ["курсив", [["i"]]]]}},
    }
    assert walk(records)[1] == ("p", "**жирный** и *курсив*")


def test_service_marks_are_dropped():
    records = {
        "page": block("page", "Стр", content=["a"]),
        "a": {"type": "text", "properties": {"title": [["‣"], ["видимый текст"]]}},
    }
    assert walk(records)[1] == ("p", "видимый текст")


@pytest.mark.parametrize("language, text, kind", [
    ("mermaid", "flowchart LR\n A-->B", "mermaid"),
    ("", "flowchart TD\n A-->B", "mermaid"),      # язык не указан, но это схема
    ("", "sequenceDiagram\n A->>B: привет", "mermaid"),
    ("python", "print(1)", "code"),
    ("", "просто текст", "code")])
def test_code_blocks_and_diagrams(language, text, kind):
    assert notion._code_block(language, text)[0] == kind


def test_table_uses_declared_column_order():
    records = {
        "page": block("page", "Стр", content=["t"]),
        "t": {"type": "table", "content": ["r1", "r2"],
              "format": {"table_block_column_order": ["c2", "c1"]}},
        "r1": {"type": "table_row",
               "properties": {"c1": title("Б"), "c2": title("А")}},
        "r2": {"type": "table_row",
               "properties": {"c1": title("2"), "c2": title("1")}},
    }
    kind, head, body = walk(records)[1]
    assert kind == "table" and head == ["А", "Б"] and body == [["1", "2"]]


def test_quote_becomes_note_and_divider_survives():
    records = {
        "page": block("page", "Стр", content=["q", "d"]),
        "q": block("quote", "важно"),
        "d": block("divider"),
    }
    kinds = [b[0] for b in walk(records)]
    assert "note" in kinds and "hr" in kinds


def test_cycles_do_not_hang():
    records = {
        "page": block("page", "Стр", content=["a"]),
        "a": block("toggle", "узел", content=["page"]),
    }
    assert walk(records)                      # не зависаем и что-то возвращаем


def test_missing_children_are_skipped():
    records = {"page": block("page", "Стр", content=["нет-такого"])}
    assert walk(records) == [("h1", "Стр")]


def test_image_url_is_proxied_for_private_files():
    direct = notion._image_url("id", "https://example.com/pic.png")
    assert direct == "https://example.com/pic.png"
    proxied = notion._image_url("id", "https://s3.amazonaws.com/secure/pic.png")
    assert proxied.startswith("https://www.notion.so/image/")
    assert notion._image_url("id", "") == ""


def test_official_rich_text():
    items = [{"plain_text": "жирный", "annotations": {"bold": True}},
             {"plain_text": " и "},
             {"plain_text": "код", "annotations": {"code": True}}]
    assert notion._rich_v1(items) == "**жирный** и `код`"
    assert notion._rich_v1([]) == ""
    assert notion._rich_v1(None) == ""
