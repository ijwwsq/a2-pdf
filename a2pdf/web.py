"""HTTP-сервис: принимает .md или .docx, отдаёт PDF в оформлении A2DATA.

    uvicorn a2pdf.web:app --host 0.0.0.0 --port 8000

Эндпоинты:
    GET  /            веб-форма
    POST /convert     multipart: file + поля обложки -> application/pdf
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

from . import core
from .docx_reader import docx_to_blocks

log = logging.getLogger("a2pdf")

MAX_BYTES = int(os.environ.get("A2PDF_MAX_UPLOAD", 20 * 1024 * 1024))
WORKERS = int(os.environ.get("A2PDF_WORKERS", 2))
TIMEOUT = int(os.environ.get("A2PDF_TIMEOUT", 120))
ALLOWED = {".md", ".markdown", ".docx"}

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
    return JSONResponse({"status": "ok", "chrome": getattr(app.state, "chrome", None)})


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


def _convert(data: bytes, filename: str, overrides: dict, chrome: str) -> pathlib.Path:
    stem = _safe_stem(filename)
    out_path = OUT_DIR / f"{uuid.uuid4().hex}.pdf"
    suffix = pathlib.Path(filename).suffix.lower()

    if suffix == ".docx":
        blocks, front = docx_to_blocks(data)
        if not blocks:
            raise ValueError("В документе не нашлось текста")
        front.setdefault("title", stem)
        front.update(overrides)
        core.render_pdf(blocks, front, out_path, chrome=chrome, name=stem)
    else:
        text = data.decode("utf-8-sig", errors="replace")
        if not text.strip():
            raise ValueError("Файл пустой")
        core.build_markdown(text, out_path, overrides=overrides,
                            chrome=chrome, name=stem)
    return out_path


@app.post("/convert")
async def convert(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    subtitle: str | None = Form(None),
    kicker: str | None = Form(None),
    index: str | None = Form(None),
    header: str | None = Form(None),
    footer: str | None = Form(None),
    confidential: str | None = Form(None),
    meta: str | None = Form(None),
    cover: str | None = Form(None),
    numbered: str | None = Form(None),
):
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415, f"Поддерживаются {', '.join(sorted(ALLOWED))}")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")

    overrides = _overrides(title=title, subtitle=subtitle, kicker=kicker,
                           index=index, header=header, footer=footer,
                           confidential=confidential, meta=meta)
    if cover in ("0", "false", "off"):
        overrides["cover"] = "false"
    if numbered in ("0", "false", "off"):
        overrides["numbered"] = "false"

    loop = asyncio.get_running_loop()
    async with _slots:
        try:
            out_path = await asyncio.wait_for(
                loop.run_in_executor(_pool, _convert, data, file.filename or "document",
                                     overrides, app.state.chrome),
                timeout=TIMEOUT)
        except asyncio.TimeoutError:
            raise HTTPException(504, "Сборка заняла слишком много времени")
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        except Exception:
            log.exception("не удалось собрать %s", file.filename)
            raise HTTPException(500, "Не удалось собрать PDF")

    name = f"{_safe_stem(file.filename or 'document')}.pdf"
    return FileResponse(
        out_path, media_type="application/pdf", filename=name,
        background=BackgroundTask(out_path.unlink, missing_ok=True))
