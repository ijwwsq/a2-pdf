"""Выноски, подсветка кода, оглавление, цвета графиков и конструктор схем."""
import os

import pytest

os.environ.setdefault("A2PDF_AUTH", "off")

from fastapi.testclient import TestClient  # noqa: E402

from a2pdf import brands, core, diagrams, web  # noqa: E402


def test_callouts_parsed_and_rendered():
    blocks = core.parse("> [!WARNING]\n> Не трогать прод\n\n> просто цитата")
    assert blocks == [("callout", "warning", "Не трогать прод"),
                      ("note", "просто цитата")]
    out = core.render(blocks, brands.get(None))
    assert "co-warning" in out and "Внимание" in out


def test_unknown_callout_stays_quote():
    assert core.parse("> [!WHATEVER] текст")[0][0] == "note"


def test_code_highlight_roles():
    tokens = core.code_tokens("python", "def f(x):\n    return 'a'  # c\n")
    roles = {role for role, _ in tokens}
    assert {"kw", "fn", "str", "com"} <= roles
    assert "".join(v for _, v in tokens) == "def f(x):\n    return 'a'  # c\n"
    assert core.code_tokens("", "x") is None
    assert core.code_tokens("нет-такого", "x") is None
    html = core.render([("code", "python", "x = '<b>'")], brands.get(None))
    assert 't-str' in html and "&lt;b&gt;" in html


def test_headings_follow_numbering_marks():
    blocks = core.parse("## Раз\n### Под\n## **Два**\n<!--NUMBERING:off-->\n## Три")
    assert core.headings(blocks) == [(1, "01", "Раз"), (2, "", "Под"),
                                     (1, "02", "Два"), (1, "", "Три")]


def test_toc_auto_from_three_sections():
    two = [(1, "01", "a", 0), (1, "02", "b", 1)]
    three = two + [(1, "03", "c", 2)]
    assert not core.want_toc({}, two)
    assert core.want_toc({}, three)
    assert core.want_toc({"toc": "true"}, two)
    assert not core.want_toc({"toc": "off"}, three)


def _luma(color: str) -> float:
    r, g, b = (int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return .2126 * r + .7152 * g + .0722 * b


@pytest.mark.parametrize("brand_key", ["a2data", "becloud"])
@pytest.mark.parametrize("scheme", ["outline", "soft", "solid", "clear"])
def test_chart_series_visible_on_white(brand_key, scheme):
    """Сектора и столбцы не бледнеют до незаметности на светлой подложке."""
    brand = brands.get(brand_key)
    theme = diagrams.mermaid_theme(brand, None, core.scheme_style(scheme, brand))
    for i in range(1, 13):
        assert _luma(theme[f"pie{i}"]) < .75, (i, theme[f"pie{i}"])
    assert theme["xyChart"]["plotColorPalette"].count(",") >= 5


def test_templates_cover_every_type_and_have_snippets():
    heads = {t["source"].split()[0] for t in diagrams.TEMPLATES.values()}
    assert len(heads) == len(diagrams.TEMPLATES) >= 30
    for t in diagrams.TEMPLATES.values():
        assert t["group"] and t["title"] and t["snippets"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(core, "find_chrome", lambda: "chrome")
    with TestClient(web.app) as c:
        yield c


def test_builder_page_and_assets(client):
    page = client.get("/builder")
    assert page.status_code == 200 and "Конструктор схем" in page.text
    assert client.get("/mermaid.js").status_code == 200
    items = client.get("/diagram/templates").json()["templates"]
    assert {i["key"] for i in items} == set(diagrams.TEMPLATES)


def test_diagram_theme_repaints_and_themes(client):
    src = "flowchart LR\n  A --> B\n  classDef x fill:#123456,stroke:#000,color:#000"
    data = client.post("/diagram/theme", json={
        "source": src, "brand": "becloud", "scheme": "dark"}).json()
    assert "#123456" not in data["source"]
    assert data["scheme"] == "dark" and data["brand"] == "becloud"
    assert data["config"]["themeVariables"]["pie1"] and "--brand:" in data["tokens"]
    assert data["config"]["railroad"]["terminalFill"]
    assert ".dg-mermaid" in data["css"]


def test_watermark_and_toc_reach_overrides(client, monkeypatch):
    seen = {}

    def fake_convert(source, overrides, chrome, fmt="pdf"):
        seen.update(overrides)
        out = web.OUT_DIR / "stub.pdf"
        out.write_bytes(b"%PDF-1.4")
        return out, "document"

    monkeypatch.setattr(web, "_convert", fake_convert)
    client.post("/convert", data={"text": "# a", "watermark": "ЧЕРНОВИК",
                                  "toc": "0"})
    assert seen["watermark"] == "ЧЕРНОВИК" and seen["toc"] == "false"


def test_init_directive_cannot_override_brand_theme():
    src = ('%%{init: {"theme": "forest", "themeVariables": {"primaryColor": "#f00"},'
           ' "flowchart": {"curve": "linear"}}}%%\nflowchart LR\n  A --> B')
    out = diagrams.theme_diagram(src, brands.get(None))
    assert "forest" not in out and "#f00" not in out
    assert '"curve": "linear"' in out


def test_sankey_cyrillic_labels_encoded():
    out = diagrams.theme_diagram("sankey-beta\n\nБюджет,Dev,10\n", brands.get(None))
    assert "Бюджет" not in out.splitlines()[2] and out.splitlines()[2].startswith("lbl0q,Dev")
    assert diagrams.LABELS_MARK in out


def test_flow_assets_served(client):
    assert client.get("/static/flow/flow.js").status_code == 200
    assert client.get("/static/flow/flow.css").status_code == 200
    assert client.get("/static/flow/../index.html").status_code == 404


@pytest.mark.parametrize("ip,ok", [("8.8.8.8", True), ("10.0.0.1", False),
                                   ("127.0.0.1", False), ("169.254.169.254", False),
                                   ("100.64.0.1", False), ("::ffff:10.0.0.1", False),
                                   ("::1", False), ("2a00:1450:4001::1", True)])
def test_public_ip(ip, ok):
    from a2pdf.fetch import public_ip
    assert public_ip(ip) is ok


def test_redirect_to_internal_address_is_refused():
    """Соединение с внутренним адресом рвётся после подключения — так не
    проходят ни редирект, ни подмена DNS."""
    import socket
    from a2pdf.fetch import FetchError, _check_peer
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    client = socket.create_connection(server.getsockname())
    with pytest.raises(FetchError):
        _check_peer(client)
    server.close()


def test_user_images_never_read_local_files(monkeypatch):
    calls = []
    monkeypatch.setattr(web, "get_bytes", lambda url, **kw: calls.append(url) or
                        (b"\\x89PNG", "image/png", ""))
    blocks = [("image", "/etc/passwd"), ("image", "https://example.com/a.png"),
              ("image", "data:image/png;base64,AAAA"), ("p", "текст")]
    front = {"photo": "/etc/shadow"}
    out = web._safe_media(blocks, front, {})
    assert [b[0] for b in out] == ["image", "image", "p"]
    assert out[0][1].startswith("data:image/png;base64,")
    assert front["photo"] == "" and calls == ["https://example.com/a.png"]


def test_form_photo_is_kept(monkeypatch):
    front = {"photo": "/srv/covers/city.jpg"}
    web._safe_media([], front, {"photo": "/srv/covers/city.jpg"})
    assert front["photo"] == "/srv/covers/city.jpg"


def test_inline_italic_links_and_code():
    out = core.inline('*курсив*, **жирный**, `a*b*c`, [сайт](https://a2data.ai/x?a=1&b=2), '
                      '[локальный](file.md), 2 * 3 * 4')
    assert "<em>курсив</em>" in out and "<strong>жирный</strong>" in out
    assert "<code>a*b*c</code>" in out                    # в коде разметки нет
    assert '<a href="https://a2data.ai/x?a=1&amp;b=2">сайт</a>' in out
    assert "локальный" in out and "file.md" not in out
    assert "2 * 3 * 4" in out


def test_link_cannot_break_out_of_attribute():
    out = core.inline('[x](https://a.b/"onmouseover="alert(1))')
    assert "<a " not in out          # кавычка в адресе — ссылка не создаётся


def test_deep_headings_become_h4():
    assert core.parse("##### Глубоко\n###### Ещё")[0] == ("h4", "Глубоко")


def test_docx_links_parts_and_numbering(tmp_path, monkeypatch):
    docx = pytest.importorskip("docx")
    from a2pdf import docx_writer
    monkeypatch.setattr(core, "ensure_assets", lambda quiet=True: None)
    blocks = core.parse("## Раз\n\nСм. [сайт](https://a2data.ai) и *курсив*\n\n"
                        "<!--PART:Часть 2|Разбор-->\n\n<!--NUMBERING:off-->\n\n## Два")
    out = docx_writer.write_docx(blocks, {"title": "Т"}, tmp_path / "a.docx",
                                 chrome="chrome")
    doc = docx.Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "[сайт]" not in text and "*курсив*" not in text
    assert "ЧАСТЬ 2" in text and "Разбор" in text
    assert "01" in text and "02" not in text                # нумерация выключена
    assert any(r.reltype.endswith("/hyperlink") for r in doc.part.rels.values())


def test_cli_reads_cp1251_and_keeps_docx_suffix(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(core, "find_chrome", lambda: "chrome")
    monkeypatch.setattr(core, "build_any", lambda f, out, **kw: seen.append((f, out, kw["fmt"])))
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_bytes("# Отчёт".encode("cp1251"))
    b.write_text("# Два", encoding="utf-8")
    core.main([str(a), str(b), "--docx", "-o", str(tmp_path)])
    assert [o.name for _, o, _ in seen] == ["a.docx", "b.docx"]
    blocks, _ = core.markdown_blocks(core.decode_text(a.read_bytes()))
    assert blocks == [("h1", "Отчёт")]


def test_rate_limiter_forgets_old_clients(monkeypatch):
    import collections
    monkeypatch.setattr(web, "_hits", {f"10.0.{i // 256}.{i % 256}":
                                       collections.deque([0.0]) for i in range(5001)})
    monkeypatch.setattr(web.time, "monotonic", lambda: 1000.0)
    assert web._rate_ok("1.2.3.4")
    assert list(web._hits) == ["1.2.3.4"]


def test_favicon(client):
    assert client.get("/favicon.ico").headers["content-type"] == "image/png"


def test_links_survive_html_and_notion():
    from a2pdf import html_reader, notion
    blocks = html_reader.html_to_blocks(
        '<p>См. <a href="https://a2data.ai">сайт</a> и <a href="/rel">якорь</a></p>')
    assert blocks == [("p", "См. [сайт](https://a2data.ai) и якорь")]
    assert notion._rich_v3([["сайт", [["a", "https://a2data.ai"]]]]) == \
        "[сайт](https://a2data.ai)"
    assert notion._rich_v1([{"plain_text": "сайт", "href": "https://a2data.ai"}]) == \
        "[сайт](https://a2data.ai)"
