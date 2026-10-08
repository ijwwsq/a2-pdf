"""Загрузка документа по ссылке: обычная веб-страница или raw markdown.

Никаких браузеров: страница берётся обычным HTTP-запросом и разбирается
как HTML. Страницы Notion читает модуль notion — через его API.
"""
from __future__ import annotations

import html
import http.client
import ipaddress
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


def public_ip(ip: str) -> bool:
    """Адрес из интернета, а не из внутренней сети, петли или служебных
    диапазонов. IPv4 внутри IPv6 (::ffff:10.0.0.1) проверяем как IPv4."""
    addr = ipaddress.ip_address(ip.split("%")[0])
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


def _check_peer(sock) -> None:
    """Проверяем, куда реально подключились: так не проходят ни редирект
    на внутренний адрес, ни подмена DNS между проверкой и запросом."""
    ip = sock.getpeername()[0]
    if not public_ip(ip):
        sock.close()
        raise FetchError("Ссылки на внутренние адреса не принимаются")


class _HTTP(http.client.HTTPConnection):
    def connect(self):
        super().connect()
        _check_peer(self.sock)


class _HTTPS(http.client.HTTPSConnection):
    def connect(self):
        super().connect()
        _check_peer(self.sock)


class _HTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_HTTP, req)


class _HTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_HTTPS, req, context=self._context)


# ponytail: прокси из окружения не используем — до внутреннего прокси проверка
# адреса не пропустила бы; понадобится прокси — проверять адрес на его стороне
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                     _HTTPHandler, _HTTPSHandler)


def _inflate(raw: bytes, encoding: str, limit: int) -> bytes:
    """Распаковка с потолком: сжатая «бомба» не раздует память."""
    if encoding not in ("gzip", "deflate"):
        return raw
    wbits = 16 + zlib.MAX_WBITS if encoding == "gzip" else -zlib.MAX_WBITS
    inflater = zlib.decompressobj(wbits)
    out = inflater.decompress(raw, limit)
    if inflater.unconsumed_tail:
        raise FetchError("Страница слишком большая")
    return out


def get_bytes(url: str, timeout: int = 45, limit: int = MAX_BYTES,
              accept: str = "*/*") -> tuple[bytes, str, str]:
    """Тело ответа, тип содержимого и кодировка — только с публичных адресов."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": accept,
        "Accept-Language": "ru,en;q=0.8", "Accept-Encoding": "gzip, deflate"})
    try:
        with OPENER.open(req, timeout=timeout) as resp:
            raw = resp.read(limit + 1)
            if len(raw) > limit:
                raise FetchError("Страница слишком большая")
            raw = _inflate(raw, (resp.headers.get("Content-Encoding") or "").lower(),
                           limit)
            return (raw, resp.headers.get_content_type(),
                    resp.headers.get_content_charset() or "utf-8")
    except urllib.error.HTTPError as exc:
        raise FetchError(f"Страница ответила {exc.code}")
    except FetchError:
        raise
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, FetchError):
            raise exc.reason
        raise FetchError(f"Не удалось открыть ссылку: {exc.reason}")
    except Exception as exc:
        raise FetchError(f"Не удалось открыть ссылку: {exc}")


def http_get(url: str, timeout: int = 45) -> str:
    raw, _, charset = get_bytes(
        url, timeout,
        accept="text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8")
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:                      # сервер назвал несуществующую кодировку
        return raw.decode("utf-8", errors="replace")


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
    blocks = [("image", urllib.parse.urljoin(url, b[1])) if b[0] == "image" else b
              for b in html_to_blocks(_content(markup))]
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
