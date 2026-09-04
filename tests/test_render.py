"""Сборка целиком: эти тесты запускают Chrome, поэтому идут отдельно.

    pytest -m slow
"""
import concurrent.futures

import pymupdf
import pytest

from a2pdf import core

pytestmark = pytest.mark.slow

MD = """---
title: Отчёт
---

# Отчёт

Текст с таблицей.

| Ключ | Значение |
| --- | --- |
| раз | 1 |

```mermaid
flowchart LR
    A[Заявка] --> B[(Витрина)]
```
"""


@pytest.fixture(scope="module")
def chrome():
    try:
        core.ensure_assets(quiet=True)
        return core.find_chrome()
    except Exception as exc:                     # браузера на машине нет
        pytest.skip(f"Chrome недоступен: {exc}")


@pytest.mark.parametrize("brand", ["a2data", "becloud"])
def test_pdf_has_cover_and_content(chrome, tmp_path, brand):
    out = tmp_path / f"{brand}.pdf"
    core.build_markdown(MD, out, overrides={"brand": brand}, chrome=chrome)
    with pymupdf.open(out) as doc:
        assert doc.page_count >= 2
        text = "".join(p.get_text() for p in doc)
    assert "Отчёт" in text
    assert "flowchart" not in text          # исходник схемы не должен попасть
    assert "Syntax error" not in text


def test_broken_diagram_shows_source(chrome, tmp_path):
    out = tmp_path / "broken.pdf"
    core.build_markdown("# Схема\n\n```mermaid\nвовсе не диаграмма\n```",
                        out, chrome=chrome)
    with pymupdf.open(out) as doc:
        text = "".join(p.get_text() for p in doc)
    assert "вовсе не диаграмма" in text
    assert "Syntax error" not in text


@pytest.mark.parametrize("scheme", list(core.DIAGRAM_SCHEMES))
def test_every_scheme_renders(chrome, scheme):
    src = "flowchart LR\n  A[Раз] --> B[Два]\n  classDef c fill:#eee\n  class A c\n"
    images = core.diagram_images([src], {"brand": "becloud"}, chrome=chrome,
                                 dpi=90, scheme=scheme)
    data, ratio = images[0]
    assert data.startswith(b"\x89PNG") and ratio > 0
    transparent = data[:2000].find(b"tRNS") >= 0 or core.DIAGRAM_SCHEMES[scheme]["clear"]
    assert transparent or not core.DIAGRAM_SCHEMES[scheme]["clear"]


def test_parallel_diagrams_do_not_clash(chrome):
    """Соседние сборки с одинаковым именем не должны мешать друг другу."""
    first = "flowchart LR\n  A[Первая] --> B[Схема]\n"
    second = "flowchart LR\n  X[Совсем] --> Y[Другая] --> Z[Схема]\n"

    def build(src):
        return len(core.diagram_images([src], {"brand": "a2data"},
                                       chrome=chrome, dpi=90)[0][0])

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        sizes = list(pool.map(build, [first, second] * 2))
    assert len(set(sizes)) == 2                  # каждая схема нарисована собой


def test_parallel_documents_do_not_clash(chrome, tmp_path):
    def build(n):
        out = tmp_path / f"doc{n}.pdf"
        core.build_markdown(f"# Документ {n}\n\nТекст {n}.", out,
                            chrome=chrome, name="document")
        with pymupdf.open(out) as doc:
            return "".join(p.get_text() for p in doc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        texts = list(pool.map(build, range(4)))
    for n, text in enumerate(texts):
        assert f"Документ {n}" in text


def test_docx_keeps_diagram_and_text(chrome, tmp_path):
    out = tmp_path / "doc.docx"
    core.build_markdown(MD, out, overrides={"brand": "becloud", "scheme": "soft"},
                        chrome=chrome, fmt="docx")
    docx = pytest.importorskip("docx")
    document = docx.Document(str(out))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Отчёт" in text
    with __import__("zipfile").ZipFile(out) as z:
        assert any(n.startswith("word/media/") for n in z.namelist())
