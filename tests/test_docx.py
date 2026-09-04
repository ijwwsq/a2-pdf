"""Набор Word-документа: все виды блоков без запуска браузера."""
import zipfile

import pytest

from a2pdf import docx_writer

docx = pytest.importorskip("docx")

BLOCKS = [
    ("h1", "Заголовок"),
    ("h2", "Раздел"),
    ("h3", "Подраздел"),
    ("p", "Абзац с **жирным** и `кодом`."),
    ("ul", ["раз", "два"]),
    ("ol", ["первый", "второй"]),
    ("code", "python", "print(1)"),
    ("note", "Важная мысль."),
    ("cap", "Подпись к рисунку"),
    ("hr",),
    ("table", ["Ключ", "Значение"], [["раз", "1"], ["два", "2"]]),
    ("image", "нет-такого-файла.png"),
]


@pytest.fixture
def built(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_writer.core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(docx_writer.core, "find_chrome", lambda: "chrome")
    out = tmp_path / "doc.docx"
    docx_writer.write_docx(BLOCKS, {"brand": "becloud", "title": "Отчёт"}, out)
    return out


def test_every_block_kind_survives(built):
    document = docx.Document(str(built))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Раздел" in text and "Подраздел" in text
    assert "print(1)" in text and "Важная мысль." in text
    assert "Подпись к рисунку" in text
    assert "**" not in text and "`" not in text     # разметка не должна утечь
    assert len(document.tables) >= 1


def test_numbering_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_writer.core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(docx_writer.core, "find_chrome", lambda: "chrome")
    out = tmp_path / "plain.docx"
    docx_writer.write_docx([("h2", "Раздел")], {"numbered": "false"}, out)
    text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
    assert "01" not in text


def test_unknown_block_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_writer.core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(docx_writer.core, "find_chrome", lambda: "chrome")
    out = tmp_path / "x.docx"
    docx_writer.write_docx([("невиданный", "что-то"), ("p", "текст")], {}, out)
    assert "текст" in "\n".join(p.text for p in docx.Document(str(out)).paragraphs)


def test_document_properties_and_logo(built):
    document = docx.Document(str(built))
    assert document.core_properties.title == "Отчёт"
    with zipfile.ZipFile(built) as z:
        assert any(n.startswith("word/media/") for n in z.namelist())
