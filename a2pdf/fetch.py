"""Загрузка документа по ссылке: обычная веб-страница или raw markdown.

Никаких браузеров: страница берётся обычным HTTP-запросом и разбирается
как HTML. Страницы Notion читает модуль notion — через его API.
"""
from __future__ import annotations

import gzip
import html
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import core
from .html_reader import extract, html_to_blocks

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")
RAW_SUFFIXES = (".md", ".markdown", ".txt")
MAX_BYTES = 8 * 1024 * 1024


class FetchError(RuntimeError):
    """Страницу не удалось прочитать."""


def http_get(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.8",
        "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_BYTES)
            encoding = (resp.headers.get("Content-Encoding") or "").lower()
            if encoding == "gzip":
                raw = gzip.decompress(raw)
            elif encoding == "deflate":
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            charset = resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        raise FetchError(f"Страница ответила {exc.code}")
    except FetchError:
        raise
    except Exception as exc:
        raise FetchError(f"Не удалось открыть ссылку: {exc}")
    return raw.decode(charset, errors="replace")


def _title(markup: str) -> str:
    found = re.search(r"<title[^>]*>(.*?)</title>", markup, re.S | re.I)
    if not found:
        return ""
    return html.unescape(re.sub(r"\s+", " ", found.group(1))).strip()


def _content(markup: str) -> str:
    for tag, css in ((None, "markdown-body"), (None, "mw-parser-output"),
                     (None, "entry-content"), (None, "post-content"),
                     ("article", None), ("main", None), ("body", None)):
        part = extract(markup, tag=tag, css_class=css)
        if part and len(part) > 300:
            return part
    return markup


def fetch(url: str) -> tuple[list[tuple], dict]:
    """Возвращает блоки документа и настройки обложки, выведенные из страницы."""
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url

    path = urllib.parse.urlparse(url).path
    if pathlib.PurePosixPath(path).suffix.lower() in RAW_SUFFIXES:
        front, body = core.split_front_matter(http_get(url))
        return core.parse(body), front

    markup = http_get(url)
    blocks = html_to_blocks(_content(markup))
    text_len = sum(len(b[1]) for b in blocks if b[0] in ("p", "h1", "h2", "h3"))
    if text_len < 80:
        raise FetchError(
            "На странице не нашлось текста: скорее всего он подгружается "
            "скриптами. Сохраните её в .md или .docx и загрузите файлом")

    front: dict = {}
    title = _title(markup)
    if title:
        front["title"] = title
    return blocks, front
