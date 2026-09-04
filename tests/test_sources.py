"""Бренды, шрифты и разбор входных форматов."""
import io

import pytest

from a2pdf import brands, core, notion
from a2pdf.docx_reader import docx_to_blocks
from a2pdf.html_reader import html_to_blocks


def test_known_and_unknown_brands():
    assert brands.get("becloud").key == "becloud"
    assert brands.get("нет такого").key == brands.get(None).key


@pytest.mark.parametrize("key", ["a2data", "becloud"])
def test_brand_has_every_color_role(key):
    brand = brands.get(key)
    for role in ("brand", "brand_dark", "brand_50", "brand_100", "accent",
                 "accent_dark", "accent_50", "accent_100", "mark", "mark_dark",
                 "mark_50"):
        assert brand.colors[role].startswith("#")
    for role in ("n0", "n50", "n200", "n400", "n500", "n700"):
        assert brand.neutrals[role].startswith("#")


@pytest.mark.parametrize("key", ["a2data", "becloud"])
def test_tokens_cover_used_variables(key):
    brand = brands.get(key)
    css = brands.tokens(brand, brand.fonts)
    for name in ("--brand", "--brand-dark", "--brand-50", "--accent", "--n50"):
        assert f"{name}:" in css


def test_fonts_for_falls_back():
    brand = brands.get("a2data")
    assert brands.fonts_for(brand, "нет такого").key == brand.fonts.key
    assert brands.fonts_for(brand, "manrope").key == "manrope"


@pytest.mark.parametrize("url, yes", [
    ("https://www.notion.so/page", True),
    ("https://team.notion.site/page", True),
    ("https://app.notion.com/p/x", True),
    ("https://notion.so.evil.com/x", False),
    ("https://example.com/notion", False)])
def test_notion_detection(url, yes):
    assert notion.is_notion(url) is yes


def test_html_reader_basic():
    blocks = html_to_blocks(
        "<h1>Раз</h1><p>текст</p><ul><li>пункт</li></ul>"
        "<table><tr><th>a</th></tr><tr><td>1</td></tr></table>")
    kinds = [b[0] for b in blocks]
    assert "h1" in kinds and "p" in kinds and "ul" in kinds and "table" in kinds


def test_html_reader_drops_scripts():
    blocks = html_to_blocks("<p>текст</p><script>alert(1)</script>")
    assert not any("alert" in str(b) for b in blocks)


def test_docx_round_trip():
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Заголовок", level=1)
    document.add_paragraph("Абзац с текстом")
    buffer = io.BytesIO()
    document.save(buffer)
    blocks, front = docx_to_blocks(buffer.getvalue())
    assert front["title"] == "Заголовок"
    assert any(b[0] == "p" for b in blocks)


def test_docx_broken_file_raises():
    with pytest.raises(Exception):
        docx_to_blocks("не документ".encode("utf-8"))


def test_embed_image_missing_file():
    assert core.embed_image("нет-такого-файла.png") == ""
    assert core.embed_image("https://x/y.png") == "https://x/y.png"
    assert core.embed_image("data:image/png;base64,AA") == "data:image/png;base64,AA"


def test_cp1251_file_is_decoded():
    text = "# Квартальный отчёт\n\nВыручка выросла."
    assert core.decode_text(text.encode("cp1251")) == text


def test_utf8_file_is_decoded():
    text = "# Отчёт с эмодзи 🚀"
    assert core.decode_text(text.encode("utf-8")) == text
    assert core.decode_text(text.encode("utf-8-sig")) == text


def test_binary_never_raises():
    assert isinstance(core.decode_text(bytes(range(256))), str)


def test_broken_docx_gives_clear_error():
    from a2pdf.docx_reader import DocxError
    with pytest.raises(DocxError):
        docx_to_blocks("не документ".encode("utf-8"))
    assert issubclass(DocxError, ValueError)   # web превращает такое в 400


@pytest.mark.parametrize("url, page", [
    ("https://www.notion.so/Otchet-1234567890abcdef1234567890abcdef",
     "12345678-90ab-cdef-1234-567890abcdef"),
    ("https://team.notion.site/12345678-90ab-cdef-1234-567890abcdef",
     "12345678-90ab-cdef-1234-567890abcdef")])
def test_notion_page_id(url, page):
    assert notion.page_id(url) == page


def test_notion_page_id_requires_identifier():
    with pytest.raises(notion.NotionError):
        notion.page_id("https://www.notion.so/prosto-stranica")


@pytest.mark.parametrize("markup", [
    "", "   ", "<p>текст<div><span>ещё", "<table></table>",
    "<ul><li>раз<ul><li>вложенный</li></ul></li></ul>",
    "<!-- скрыто --><p>видно</p>", "<div>" * 200 + "текст" + "</div>" * 200])
def test_html_reader_survives_broken_markup(markup):
    assert isinstance(html_to_blocks(markup), list)


def test_html_reader_decodes_entities():
    blocks = html_to_blocks("<p>&laquo;кавычки&raquo; &amp; &#1090;&#1077;&#1082;&#1089;&#1090;</p>")
    text = " ".join(str(b[1]) for b in blocks)
    assert "«кавычки»" in text and "текст" in text and "&amp;" not in text


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp1251", "utf-16",
                                      "utf-32"])
def test_text_encodings_round_trip(encoding):
    """Блокнот и Word сохраняют с меткой кодировки — по ней и определяем."""
    text = "# Квартальный отчёт"
    assert core.decode_text(text.encode(encoding)) == text
