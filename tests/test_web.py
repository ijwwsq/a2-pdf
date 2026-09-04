"""Проверки HTTP-слоя без запуска браузера: сборку подменяем заглушкой."""
import os
import pathlib

import pytest

os.environ.setdefault("A2PDF_AUTH", "off")

from fastapi.testclient import TestClient  # noqa: E402

from a2pdf import core, web  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    """Клиент, где документ не собирается, а подменяется файлом-заглушкой."""
    calls = []

    def fake_convert(source, overrides, chrome, fmt="pdf"):
        calls.append({"source": source, "overrides": overrides, "fmt": fmt})
        out = tmp_path / f"out.{fmt}"
        out.write_bytes(b"%PDF-1.4 stub" if fmt == "pdf" else b"stub")
        return out, "document"

    monkeypatch.setattr(web, "_convert", fake_convert)
    monkeypatch.setattr(core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(core, "find_chrome", lambda: "chrome")
    with TestClient(web.app) as c:
        c.calls = calls
        yield c


def test_form_and_health(client):
    assert client.get("/").status_code == 200
    body = client.get("/healthz").json()
    assert body["auth"] is False


def test_brands_and_fonts_and_schemes(client):
    brands = client.get("/brands").json()["brands"]
    assert {b["key"] for b in brands} == {"a2data", "becloud"}
    assert client.get("/fonts").json()["fonts"]
    schemes = client.get("/schemes?brand=becloud").json()["schemes"]
    assert [s["key"] for s in schemes] == list(core.DIAGRAM_SCHEMES)
    assert all(s["preview"]["fill"] for s in schemes)


def test_schemes_unknown_brand_falls_back(client):
    assert client.get("/schemes?brand=нет").status_code == 200


def test_convert_requires_source(client):
    assert client.post("/convert", data={}).status_code == 400


def test_convert_text(client):
    r = client.post("/convert", data={"text": "# Раз"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert client.calls[-1]["source"]["kind"] == "text"


def test_convert_keeps_cyrillic(client):
    client.post("/convert", data={"text": "# Отчёт", "title": "Квартал"})
    call = client.calls[-1]
    assert call["source"]["text"] == "# Отчёт"
    assert call["overrides"]["title"] == "Квартал"


@pytest.mark.parametrize("requested, fmt", [
    ("word", "docx"), ("docx", "docx"), ("image", "png"), ("png", "png"),
    ("pdf", "pdf"), ("", "pdf"), ("чтотото", "pdf")])
def test_format_choice(client, requested, fmt):
    client.post("/convert", data={"text": "# Раз", "format": requested})
    assert client.calls[-1]["fmt"] == fmt


def test_rejects_foreign_extension(client):
    r = client.post("/convert", files={"file": ("a.exe", b"x", "application/exe")})
    assert r.status_code == 415


def test_rejects_empty_file(client):
    r = client.post("/convert", files={"file": ("a.md", b"", "text/markdown")})
    assert r.status_code == 400


def test_rejects_huge_file(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BYTES", 10)
    r = client.post("/convert", files={"file": ("a.md", b"x" * 100, "text/markdown")})
    assert r.status_code == 413


def test_rejects_huge_text(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BYTES", 10)
    assert client.post("/convert", data={"text": "x" * 100}).status_code == 413


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://localhost/x", "http://169.254.169.254/meta",
    "file:///etc/passwd", "ftp://example.com/x"])
def test_blocks_internal_and_foreign_schemes(client, url):
    r = client.post("/convert", data={"url": url})
    assert r.status_code == 400


def test_overrides_are_filtered(client):
    client.post("/convert", data={
        "text": "# Раз", "brand": "нет-такого", "font": "нет", "scheme": "нет",
        "style": "полосатый", "meta": "Клиент=ООО;Срок=10"})
    over = client.calls[-1]["overrides"]
    assert over["brand"] == "a2data"      # неизвестный бренд — запасной
    assert "font" not in over and "scheme" not in over and "style" not in over
    assert over["meta"] == {"Клиент": "ООО", "Срок": "10"}


def test_known_options_pass_through(client):
    client.post("/convert", data={
        "text": "# Раз", "brand": "becloud", "font": "manrope",
        "scheme": "dark", "style": "light", "cover": "0", "numbered": "0"})
    over = client.calls[-1]["overrides"]
    assert over["brand"] == "becloud" and over["font"] == "manrope"
    assert over["scheme"] == "dark" and over["style"] == "light"
    assert over["cover"] == "false" and over["numbered"] == "false"


def test_background_path_cannot_escape(client):
    client.post("/convert", data={"text": "# Раз",
                                  "background": "../../../../etc/passwd"})
    assert "photo" not in client.calls[-1]["overrides"]


def test_builtin_background_accepted(client):
    covers = sorted(web.COVERS.glob("*.jpg"))
    if not covers:
        pytest.skip("фоны не скачаны")
    client.post("/convert", data={"text": "# Раз", "background": covers[0].stem})
    assert client.calls[-1]["overrides"]["photo"].endswith(covers[0].name)


def test_photo_type_checked(client):
    r = client.post("/convert", data={"text": "# Раз"},
                    files={"photo": ("a.gif", b"x", "image/gif")})
    assert r.status_code == 415


def test_filename_is_sanitised():
    assert web._safe_stem("../../тайна.md") == "тайна"
    assert web._safe_stem("a" * 200).__len__() <= 80
    assert web._safe_stem("???") == "document"


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(web, "RATE_LIMIT", 3)
    web._hits.clear()
    codes = [client.post("/convert", data={"text": "# Раз"}).status_code
             for _ in range(5)]
    assert 429 in codes
    web._hits.clear()


def test_error_from_builder_becomes_400(client, monkeypatch):
    def boom(*a, **kw):
        raise ValueError("В тексте нет диаграммы mermaid")

    monkeypatch.setattr(web, "_convert", boom)
    r = client.post("/convert", data={"text": "# Раз", "format": "png"})
    assert r.status_code == 400
    assert "mermaid" in r.json()["detail"]


def test_unexpected_error_becomes_500(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("chrome умер")

    monkeypatch.setattr(web, "_convert", boom)
    assert client.post("/convert", data={"text": "# Раз"}).status_code == 500


def test_output_file_removed_after_download(client):
    r = client.post("/convert", data={"text": "# Раз"})
    assert r.status_code == 200
    leftovers = list(web.OUT_DIR.glob("*"))
    assert leftovers == []


def test_logo_and_cover_names_are_checked(client):
    assert client.get("/logo/../../secret").status_code in (400, 404)
    assert client.get("/covers/nope.jpg").status_code == 404


def test_static_login_page_served(client):
    assert client.get("/login").status_code in (200, 404)


def test_timeout_removes_abandoned_build(client, monkeypatch, tmp_path):
    """Сборку, которую никто не дождался, нельзя оставлять на диске."""
    import time as _time

    leftover = tmp_path / "brosheno.pdf"

    def slow(source, overrides, chrome, fmt="pdf"):
        _time.sleep(0.4)
        leftover.write_bytes(b"%PDF stub")
        return leftover, "document"

    monkeypatch.setattr(web, "_convert", slow)
    monkeypatch.setattr(web, "TIMEOUT", 0.05)
    assert client.post("/convert", data={"text": "# Раз"}).status_code == 504
    _time.sleep(1.0)
    assert not leftover.exists()


def test_pool_survives_repeated_startup(monkeypatch, tmp_path):
    """Приложение поднимают в процессе не один раз — пул должен пережить."""
    def fake(source, overrides, chrome, fmt="pdf"):
        out = tmp_path / f"x.{fmt}"
        out.write_bytes(b"stub")
        return out, "document"

    monkeypatch.setattr(web, "_convert", fake)
    monkeypatch.setattr(core, "ensure_assets", lambda quiet=True: None)
    monkeypatch.setattr(core, "find_chrome", lambda: "chrome")
    for _ in range(2):
        with TestClient(web.app) as c:
            assert c.post("/convert", data={"text": "# Раз"}).status_code == 200
