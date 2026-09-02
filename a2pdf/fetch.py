"""Загрузка документа по ссылке: Notion, обычная веб-страница или raw markdown.

Страница открывается тем же headless-браузером, что печатает PDF, поэтому
работают и SPA вроде Notion — важно лишь, чтобы страница была доступна
без входа (в Notion: Share → Publish to web).
"""
from __future__ import annotations

import html
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from . import core
from .html_reader import extract, html_to_blocks

_UA_CACHE: dict[str, str] = {}


def browser_ua(chrome: str = "") -> str:
    """UA с реальной версией браузера: Notion отказывается работать со старым."""
    if chrome in _UA_CACHE:
        return _UA_CACHE[chrome]
    major = "131"
    if chrome:
        try:
            out = subprocess.run([chrome, "--version"], capture_output=True,
                                 text=True, timeout=20).stdout
            found = re.search(r"(\d+)\.\d+", out or "")
            major = found.group(1) if found else major
        except Exception:
            pass
    platform = ("Windows NT 10.0; Win64; x64" if sys.platform == "win32"
                else "X11; Linux x86_64")
    ua = (f"Mozilla/5.0 ({platform}) AppleWebKit/537.36 (KHTML, like Gecko) "
          f"Chrome/{major}.0.0.0 Safari/537.36")
    _UA_CACHE[chrome] = ua
    return ua
RAW_SUFFIXES = (".md", ".markdown", ".txt")
LOGIN_MARKERS = ("Log in", "Войти", "Sign in to continue",
                 "This content is not publicly available")


class FetchError(RuntimeError):
    """Страницу не удалось прочитать."""


def is_notion(url: str) -> bool:
    return "notion.so" in url or "notion.site" in url


def dump_dom(url: str, chrome: str, wait_ms: int = 20000) -> str:
    """Открывает страницу в headless-браузере и возвращает готовый DOM."""
    core.TMP.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="chrome-fetch-", dir=core.TMP)
    try:
        result = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={profile}", "--dump-dom",
             f"--virtual-time-budget={wait_ms}",
             f"--user-agent={browser_ua(chrome)}", url],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=wait_ms // 1000 + 45)
    except subprocess.TimeoutExpired:
        raise FetchError("Страница не успела загрузиться")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not result.stdout or len(result.stdout) < 200:
        raise FetchError("Страница не отдала содержимое")
    return result.stdout


def _title(markup: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", markup, re.S | re.I)
    if not m:
        return ""
    title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    # Notion добавляет к заголовку хвосты вида «| Notion»
    return re.sub(r"\s*[|·—-]\s*Notion\s*$", "", title)


def _content(markup: str) -> str:
    for tag, css in ((None, "notion-page-content"), ("article", None),
                     ("main", None), (None, "markdown-body"), ("body", None)):
        part = extract(markup, tag=tag, css_class=css)
        if part and len(part) > 300:
            return part
    return markup


def fetch_markdown(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": browser_ua()})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch(url: str, chrome: str | None = None) -> tuple[list[tuple], dict]:
    """Возвращает блоки документа и настройки обложки, выведенные из страницы."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url

    if pathlib.PurePosixPath(urllib.parse.urlparse(url).path).suffix.lower() \
            in RAW_SUFFIXES:
        text = fetch_markdown(url)
        front, body = core.split_front_matter(text)
        return core.parse(body), front

    markup = dump_dom(url, chrome or core.find_chrome())
    blocks = html_to_blocks(_content(markup))
    text_len = sum(len(b[1]) for b in blocks if b[0] in ("p", "h1", "h2", "h3"))

    if text_len < 80:
        head = re.sub(r"<[^>]+>", " ", markup)[:2000]
        if any(marker in head for marker in LOGIN_MARKERS) or is_notion(url):
            raise FetchError(
                "Страница недоступна без входа. В Notion откройте доступ: "
                "Share → Publish to web")
        raise FetchError("На странице не нашлось текста")

    front: dict = {}
    title = _title(markup)
    if title:
        front["title"] = title
    return blocks, front
