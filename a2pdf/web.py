"""HTTP-сервис: файл, текст или ссылка на входе — PDF в оформлении A2DATA на выходе.

    uvicorn a2pdf.web:app --host 0.0.0.0 --port 8000

Эндпоинты:
    GET  /            веб-форма
    POST /convert     multipart: file | text | url + поля обложки -> application/pdf
    GET  /healthz     проверка живости
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import os
import pathlib
import re
import tempfile
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from . import core, notion
from .docx_reader import docx_to_blocks
from .fetch import FetchError, fetch

log = logging.getLogger("a2pdf")

MAX_BYTES = int(os.environ.get("A2PDF_MAX_UPLOAD", 20 * 1024 * 1024))
WORKERS = int(os.environ.get("A2PDF_WORKERS", 2))
TIMEOUT = int(os.environ.get("A2PDF_TIMEOUT", 180))
ALLOWED = {".md", ".markdown", ".docx"}
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}

STATIC = pathlib.Path(__file__).resolve().parent / "static"
OUT_DIR = pathlib.Path(os.environ.get("A2PDF_OUT") or tempfile.gettempdir()) / "a2pdf"

app = FastAPI(title="A2DATA PDF", docs_url="/api", redoc_url=None)
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS)
_slots = asyncio.Semaphore(WORKERS)


@app.on_event("startup")
def _warmup() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    core.ensure_assets(quiet=True)
    app.state.chrome = core.find_chrome()
    log.info("chrome: %s, воркеров: %s", app.state.chrome, WORKERS)


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "chrome": getattr(app.state, "chrome", None),
                         "notion_token": bool(os.environ.get("NOTION_TOKEN"))})


@app.get("/fonts.css")
def fonts() -> FileResponse:
    """Те же Inter и JetBrains Mono, что уходят в PDF, — без внешних CDN."""
    return FileResponse(core.ASSETS / "fonts.css", media_type="text/css",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))


def _text(value: str) -> str:
    """Starlette отдаёт текстовые части multipart в latin-1 — возвращаем UTF-8."""
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _safe_stem(name: str) -> str:
    stem = pathlib.Path(_text(name)).stem
    stem = re.sub(r"[^\w .()\[\]-]+", "_", stem, flags=re.UNICODE).strip()
    return stem[:80] or "document"


def _overrides(**fields: str | None) -> dict:
    out = {k: _text(v).strip() for k, v in fields.items() if v and v.strip()}
    meta_raw = out.pop("meta", "")
    if meta_raw:
        meta = {}
        for line in re.split(r"[\n;]+", meta_raw):
            key, sep, value = line.partition("=")
            if sep and key.strip():
                meta[key.strip()] = value.strip()
        if meta:
            out["meta"] = meta
    return out


def _convert(source: dict, overrides: dict, chrome: str) -> tuple[pathlib.Path, str]:
    """Собирает PDF и возвращает путь и предлагаемое имя файла."""
    out_path = OUT_DIR / f"{uuid.uuid4().hex}.pdf"
    kind = source["kind"]

    if kind == "file" and source["suffix"] == ".docx":
        blocks, front = docx_to_blocks(source["data"])
        if not blocks:
            raise ValueError("В документе не нашлось текста")
        front.setdefault("title", source["stem"])
        front.update(overrides)
        core.render_pdf(blocks, front, out_path, chrome=chrome, name=source["stem"])
        return out_path, source["stem"]

    if kind in ("file", "text"):
        text = (source["data"].decode("utf-8-sig", errors="replace")
                if kind == "file" else source["text"])
        if not text.strip():
            raise ValueError("Пустой текст")
        core.build_markdown(text, out_path, overrides=overrides, chrome=chrome,
                            name=source["stem"])
        return out_path, source["stem"]

    url = source["url"]
    if notion.is_notion(url):
        blocks, front = notion.load(url)
    else:
        blocks, front = fetch(url)
    front.update(overrides)
    stem = _safe_stem(str(front.get("title") or "document"))
    core.render_pdf(blocks, front, out_path, chrome=chrome, name=stem)
    return out_path, stem


@app.post("/convert")
async def convert(
    file: UploadFile | None = File(None),
    photo: UploadFile | None = File(None),
    text: str | None = Form(None),
    url: str | None = Form(None),
    title: str | None = Form(None),
    subtitle: str | None = Form(None),
    kicker: str | None = Form(None),
    index: str | None = Form(None),
    header: str | None = Form(None),
    footer: str | None = Form(None),
    confidential: str | None = Form(None),
    meta: str | None = Form(None),
    style: str | None = Form(None),
    cover: str | None = Form(None),
    numbered: str | None = Form(None),
):
    source: dict
    if file is not None and file.filename:
        suffix = pathlib.Path(file.filename).suffix.lower()
        if suffix not in ALLOWED:
            raise HTTPException(415, f"Поддерживаются {', '.join(sorted(ALLOWED))}")
        data = await file.read()
        if not data:
            raise HTTPException(400, "Пустой файл")
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")
        source = {"kind": "file", "data": data, "suffix": suffix,
                  "stem": _safe_stem(file.filename)}
    elif text and text.strip():
        body = _text(text)
        if len(body.encode()) > MAX_BYTES:
            raise HTTPException(413, "Слишком много текста")
        source = {"kind": "text", "text": body, "stem": "document"}
    elif url and url.strip():
        source = {"kind": "url", "url": _text(url).strip()}
    else:
        raise HTTPException(400, "Нужен файл, текст или ссылка")

    overrides = _overrides(title=title, subtitle=subtitle, kicker=kicker,
                           index=index, header=header, footer=footer,
                           confidential=confidential, meta=meta)
    if style in ("light", "dark"):
        overrides["style"] = style
    if cover in ("0", "false", "off"):
        overrides["cover"] = "false"
    if numbered in ("0", "false", "off"):
        overrides["numbered"] = "false"

    photo_path: pathlib.Path | None = None
    if photo is not None and photo.filename:
        if pathlib.Path(photo.filename).suffix.lower() not in PHOTO_TYPES:
            raise HTTPException(415, "Фото должно быть jpg, png или webp")
        blob = await photo.read()
        if len(blob) > MAX_BYTES:
            raise HTTPException(413, "Фото слишком большое")
        photo_path = OUT_DIR / f"{uuid.uuid4().hex}{pathlib.Path(photo.filename).suffix.lower()}"
        photo_path.write_bytes(blob)
        overrides["photo"] = str(photo_path)

    loop = asyncio.get_running_loop()
    async with _slots:
        try:
            out_path, stem = await asyncio.wait_for(
                loop.run_in_executor(_pool, _convert, source, overrides,
                                     app.state.chrome),
                timeout=TIMEOUT)
        except asyncio.TimeoutError:
            raise HTTPException(504, "Сборка заняла слишком много времени")
        except (ValueError, FetchError, notion.NotionError) as exc:
            raise HTTPException(400, str(exc))
        except Exception:
            log.exception("не удалось собрать документ (%s)", source["kind"])
            raise HTTPException(500, "Не удалось собрать PDF")
        finally:
            if photo_path:
                photo_path.unlink(missing_ok=True)

    return FileResponse(
        out_path, media_type="application/pdf", filename=f"{stem}.pdf",
        background=BackgroundTask(out_path.unlink, missing_ok=True))
