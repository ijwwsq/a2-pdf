"""Импорт страниц Notion.

Два пути:

* с токеном интеграции (`NOTION_TOKEN`) — официальный API, работает и с
  закрытыми страницами, которыми поделились с интеграцией;
* без токена — публичный эндпоинт Notion, который используют опубликованные
  страницы (Share → Publish to web).

Блоки Notion превращаются в те же блоки документа, что markdown и docx.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API_PUBLIC = "https://www.notion.so/api/v3/loadPageChunk"
API_OFFICIAL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

HEADINGS_V3 = {"header": "h2", "sub_header": "h3", "sub_sub_header": "h4"}
HEADINGS_V1 = {"heading_1": "h2", "heading_2": "h3", "heading_3": "h4"}
LIST_V3 = {"bulleted_list": "ul", "numbered_list": "ol", "to_do": "ul"}
LIST_V1 = {"bulleted_list_item": "ul", "numbered_list_item": "ol", "to_do": "ul"}
CONTAINERS = {"column_list", "column", "toggle", "callout", "quote",
              "synced_block", "template"}


class NotionError(RuntimeError):
    """Страницу не удалось прочитать."""


def is_notion(url: str) -> bool:
    """notion.so, notion.site, app.notion.com — всё это страницы Notion."""
    host = urllib.parse.urlparse(url if "//" in url else "//" + url).netloc.lower()
    host = host.split("@")[-1].split(":")[0]
    return (host == "notion.so" or host.endswith((".notion.so", ".notion.site",
                                                  ".notion.com"))
            or host in ("notion.site", "notion.com"))


def page_id(url: str) -> str:
    """Достаёт идентификатор страницы из ссылки и приводит его к UUID."""
    parsed = urllib.parse.urlparse(url if "//" in url else "//" + url)
    candidates = re.findall(r"[0-9a-fA-F]{32}", parsed.path + parsed.query)
    if not candidates:
        found = re.search(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", parsed.path)
        if not found:
            raise NotionError("В ссылке нет идентификатора страницы Notion")
        return found.group(0)
    raw = candidates[-1].lower()
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def _post(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json", "User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **headers})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


# --------------------------------------------------------------------------- #
# Текст
# --------------------------------------------------------------------------- #

def _rich_v3(title: list | None) -> str:
    """[[текст, [[формат]]], …] -> строка с markdown-разметкой."""
    if not title:
        return ""
    out = []
    for part in title:
        text = part[0] if part else ""
        if text in ("‣", "⁣"):  # служебные вставки Notion
            continue
        for fmt in (part[1] if len(part) > 1 and part[1] else []):
            kind = fmt[0]
            if kind == "b":
                text = f"**{text}**"
            elif kind == "i":
                text = f"*{text}*"
            elif kind == "c":
                text = f"`{text}`"
        out.append(text)
    return "".join(out).strip()


def _rich_v1(items: list | None) -> str:
    if not items:
        return ""
    out = []
    for item in items:
        text = item.get("plain_text", "")
        ann = item.get("annotations", {})
        if ann.get("code"):
            text = f"`{text}`"
        if ann.get("bold"):
            text = f"**{text}**"
        if ann.get("italic"):
            text = f"*{text}*"
        out.append(text)
    return "".join(out).strip()


def _image_url(block_id: str, source: str) -> str:
    """Картинки Notion отдаются через прокси с подписью."""
    if not source:
        return ""
    if source.startswith("http") and "amazonaws.com" not in source:
        return source
    quoted = urllib.parse.quote(source, safe="")
    return (f"https://www.notion.so/image/{quoted}"
            f"?table=block&id={block_id}&cache=v2")


# --------------------------------------------------------------------------- #
# Публичный эндпоинт
# --------------------------------------------------------------------------- #

def _load_public(pid: str) -> dict:
    records: dict = {}
    cursor = {"stack": []}
    for _ in range(20):  # страховка от бесконечной прокрутки
        try:
            chunk = _post(API_PUBLIC, {"pageId": pid, "limit": 100,
                                       "cursor": cursor, "chunkNumber": 0,
                                       "verticalColumns": False})
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise NotionError(
                    "Страница закрыта. Откройте доступ в Notion "
                    "(Share → Publish to web) или задайте NOTION_TOKEN")
            raise NotionError(f"Notion ответил {exc.code}")
        for key, record in chunk.get("recordMap", {}).get("block", {}).items():
            value = record.get("value") or {}
            records[key] = value.get("value", value)
        cursor = chunk.get("cursor") or {"stack": []}
        if not cursor.get("stack"):
            break
    if not records:
        raise NotionError("Notion не вернул содержимое страницы")
    return records


def _walk_public(pid: str, records: dict, blocks: list, seen: set,
                 depth: int = 0) -> None:
    if depth > 6 or pid in seen:
        return
    seen.add(pid)
    node = records.get(pid)
    if not node:
        return

    kind = node.get("type")
    text = _rich_v3(node.get("properties", {}).get("title"))
    pending_list: list[str] = []
    list_kind = "ul"

    def flush() -> None:
        nonlocal pending_list
        if pending_list:
            blocks.append((list_kind, pending_list))
            pending_list = []

    for child_id in node.get("content", []):
        child = records.get(child_id)
        if not child:
            continue
        child_kind = child.get("type")
        child_text = _rich_v3(child.get("properties", {}).get("title"))

        if child_kind in LIST_V3:
            if LIST_V3[child_kind] != list_kind:
                flush()
                list_kind = LIST_V3[child_kind]
            if child_text:
                pending_list.append(child_text)
            _walk_public(child_id, records, blocks, seen, depth + 1)
            continue
        flush()

        if child_kind in HEADINGS_V3:
            if child_text:
                blocks.append((HEADINGS_V3[child_kind], child_text))
        elif child_kind == "text":
            if child_text:
                blocks.append(("p", child_text))
        elif child_kind == "code":
            if child_text:
                blocks.append(("code", "", child_text))
        elif child_kind == "divider":
            blocks.append(("hr",))
        elif child_kind == "image":
            src = (child.get("format", {}).get("display_source")
                   or _rich_v3(child.get("properties", {}).get("source")))
            url = _image_url(child_id, src)
            if url:
                blocks.append(("image", url))
        elif child_kind in ("quote", "callout"):
            if child_text:
                blocks.append(("note", child_text))
            _walk_public(child_id, records, blocks, seen, depth + 1)
        elif child_kind in CONTAINERS:
            if child_text:
                blocks.append(("p", child_text))
            _walk_public(child_id, records, blocks, seen, depth + 1)
        elif child_kind == "table":
            rows = []
            for row_id in child.get("content", []):
                row = records.get(row_id) or {}
                props = row.get("properties", {})
                order = (child.get("format", {})
                         .get("table_block_column_order") or sorted(props))
                rows.append([_rich_v3(props.get(col)) for col in order])
            if rows:
                head, *body = rows
                blocks.append(("table", head, body))
        elif child_kind in ("page", "collection_view_page"):
            if child_text:
                blocks.append(("p", child_text))
        else:
            if child_text:
                blocks.append(("p", child_text))
            if child.get("content"):
                _walk_public(child_id, records, blocks, seen, depth + 1)
    flush()

    if depth == 0 and kind == "page" and text:
        blocks.insert(0, ("h1", text))


# --------------------------------------------------------------------------- #
# Официальный API
# --------------------------------------------------------------------------- #

def _walk_official(block_id: str, token: str, blocks: list, depth: int = 0) -> None:
    if depth > 6:
        return
    headers = {"Authorization": f"Bearer {token}",
               "Notion-Version": NOTION_VERSION}
    cursor = None
    pending: list[str] = []
    list_kind = "ul"

    def flush() -> None:
        nonlocal pending
        if pending:
            blocks.append((list_kind, pending))
            pending = []

    while True:
        url = f"{API_OFFICIAL}/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        try:
            data = _get(url, headers)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise NotionError("Интеграция не имеет доступа к странице: "
                                  "в Notion нажмите Share и добавьте её")
            if exc.code == 404:
                raise NotionError("Страница не найдена")
            raise NotionError(f"Notion ответил {exc.code}")

        for block in data.get("results", []):
            kind = block.get("type", "")
            payload = block.get(kind, {}) or {}
            text = _rich_v1(payload.get("rich_text"))

            if kind in LIST_V1:
                if LIST_V1[kind] != list_kind:
                    flush()
                    list_kind = LIST_V1[kind]
                if text:
                    pending.append(text)
                continue
            flush()

            if kind in HEADINGS_V1:
                if text:
                    blocks.append((HEADINGS_V1[kind], text))
            elif kind == "paragraph":
                if text:
                    blocks.append(("p", text))
            elif kind == "code":
                if text:
                    blocks.append(("code", payload.get("language", ""), text))
            elif kind == "divider":
                blocks.append(("hr",))
            elif kind in ("quote", "callout"):
                if text:
                    blocks.append(("note", text))
            elif kind == "image":
                src = (payload.get("external", {}).get("url")
                       or payload.get("file", {}).get("url", ""))
                if src:
                    blocks.append(("image", src))
            elif kind == "table":
                rows = []
                table = _get(f"{API_OFFICIAL}/blocks/{block['id']}/children"
                             "?page_size=100", headers)
                for row in table.get("results", []):
                    cells = row.get("table_row", {}).get("cells", [])
                    rows.append([_rich_v1(cell) for cell in cells])
                if rows:
                    head, *body = rows
                    blocks.append(("table", head, body))
                continue
            elif text:
                blocks.append(("p", text))

            if block.get("has_children") and kind not in ("table",):
                _walk_official(block["id"], token, blocks, depth + 1)

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    flush()


def _title_official(pid: str, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}",
               "Notion-Version": NOTION_VERSION}
    try:
        page = _get(f"{API_OFFICIAL}/pages/{pid}", headers)
    except urllib.error.HTTPError:
        return ""
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            return _rich_v1(prop.get("title"))
    return ""


# --------------------------------------------------------------------------- #
# Точка входа
# --------------------------------------------------------------------------- #

def load(url: str, token: str | None = None) -> tuple[list[tuple], dict]:
    """Возвращает блоки страницы и настройки обложки."""
    pid = page_id(url)
    token = token or os.environ.get("NOTION_TOKEN", "").strip()
    blocks: list[tuple] = []

    if token:
        _walk_official(pid, token, blocks)
        title = _title_official(pid, token)
    else:
        records = _load_public(pid)
        _walk_public(pid, records, blocks, set())
        title = ""
        if blocks and blocks[0][0] == "h1":
            title = str(blocks[0][1])

    if not blocks:
        raise NotionError("Страница пустая или её содержимое недоступно")

    front: dict = {}
    if title:
        front["title"] = re.sub(r"[*`]", "", title)
    return blocks, front
