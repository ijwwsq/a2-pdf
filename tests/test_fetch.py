"""Чтение страницы по ссылке — сеть подменяем."""
import pytest

from a2pdf import fetch as fetch_module
from a2pdf.fetch import FetchError, fetch

PAGE = """<html><head><title> Заголовок  страницы </title></head>
<body><article>
<h1>Отчёт</h1>
<p>Первый абзац, достаточно длинный, чтобы страницу сочли содержательной.</p>
<p>Второй абзац с продолжением мысли и дополнительными подробностями.</p>
</article></body></html>"""


@pytest.fixture
def page(monkeypatch):
    def serve(markup):
        monkeypatch.setattr(fetch_module, "http_get", lambda url, timeout=45: markup)
    return serve


def test_html_page_gives_blocks_and_title(page):
    page(PAGE)
    blocks, front = fetch("https://example.com/otchet")
    assert front["title"] == "Заголовок страницы"
    assert [b[0] for b in blocks][:2] == ["h1", "p"]


def test_markdown_link_is_parsed_as_markdown(page):
    page("---\ntitle: Из файла\n---\n\n# Раз\n\nтекст\n")
    blocks, front = fetch("https://example.com/doc.md")
    assert front["title"] == "Из файла"
    assert [b[0] for b in blocks] == ["h1", "p"]


def test_empty_page_is_reported(page):
    page("<html><body><div>ничего</div></body></html>")
    with pytest.raises(FetchError) as exc:
        fetch("https://example.com/pusto")
    assert "скриптами" in str(exc.value)


def test_scheme_is_added_when_missing(page, monkeypatch):
    seen = []
    monkeypatch.setattr(fetch_module, "http_get",
                        lambda url, timeout=45: seen.append(url) or PAGE)
    fetch("example.com/otchet")
    assert seen[0].startswith("https://")


def test_http_error_becomes_readable_message(monkeypatch):
    """Ошибку сети пользователь видит текстом, а не трассировкой."""
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", boom)
    with pytest.raises(FetchError) as exc:
        fetch("https://example.com/net")
    assert "404" in str(exc.value)


def test_broken_connection_becomes_readable_message(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("соединение разорвано")

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", boom)
    with pytest.raises(FetchError) as exc:
        fetch("https://example.com/net")
    assert "Не удалось открыть ссылку" in str(exc.value)


def test_title_of_page_without_title_is_absent(page):
    page(PAGE.replace("<title> Заголовок  страницы </title>", ""))
    _, front = fetch("https://example.com/x")
    assert "title" not in front
