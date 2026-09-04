"""HTTP-сервис: файл, текст или ссылка на входе — PDF или Word на выходе.

    uvicorn a2pdf.web:app --host 0.0.0.0 --port 8000

Эндпоинты:
    GET  /            форма
    GET  /login       вход, если он включён
    POST /convert     multipart: file | text | url + поля оформления
    GET  /brands      организации, /fonts — наборы шрифтов, /covers — фоны
    GET  /healthz     состояние сервиса
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import ipaddress
import logging
import os
import pathlib
import re
import socket
import tempfile
import time
import urllib.parse
import uuid
from collections import deque

from fastapi import (Cookie, Depends, FastAPI, File, Form, HTTPException,
                     Request, Response, UploadFile)
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from starlette.background import BackgroundTask

from . import auth, brands, core, notion
from .docx_reader import docx_to_blocks
from .fetch import FetchError, fetch

log = logging.getLogger("a2pdf")

MAX_BYTES = int(os.environ.get("A2PDF_MAX_UPLOAD", 20 * 1024 * 1024))
WORKERS = int(os.environ.get("A2PDF_WORKERS", 2))
TIMEOUT = int(os.environ.get("A2PDF_TIMEOUT", 180))
RATE_LIMIT = int(os.environ.get("A2PDF_RATE_LIMIT", 60))   # запросов с адреса в минуту
ALLOWED = {".md", ".markdown", ".docx"}
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
MIME = {"pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document",
        "png": "image/png"}
COVERS = core.ASSETS / "covers"          # встроенные фоны обложки
PNG_DPI = int(os.environ.get("A2PDF_PNG_DPI", 220))

STATIC = pathlib.Path(__file__).resolve().parent / "static"
AUTH = auth.Config()
OUT_DIR = pathlib.Path(os.environ.get("A2PDF_OUT") or tempfile.gettempdir()) / "a2pdf"


@contextlib.asynccontextmanager
async def lifespan(application: FastAPI):
    # пул и счётчик мест создаём на запуск: закрытый пул не оживить,
    # а приложение может подниматься в процессе не один раз
    application.state.pool = concurrent.futures.ThreadPoolExecutor(
        max_workers=WORKERS)
    application.state.slots = asyncio.Semaphore(WORKERS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    core.ensure_assets(quiet=True)
    application.state.chrome = core.find_chrome()
    log.info("chrome: %s, воркеров: %s", application.state.chrome, WORKERS)
    if not AUTH.enabled:
        log.warning("Вход отключён (A2PDF_AUTH=off): сервис открыт всем, "
                    "кто до него дотянется")
    elif not AUTH.configured:
        log.warning("Учётная запись не настроена: сервис отвечает только "
                    "с локальной машины. Задайте A2PDF_PASSWORD_HASH "
                    "(python -m a2pdf.auth)")
    elif not AUTH.secret_from_env:
        log.warning("A2PDF_SECRET не задан: сессии слетят при перезапуске")
    for stale in OUT_DIR.glob("*"):  # мусор от прошлого запуска
        stale.unlink(missing_ok=True)
    yield
    application.state.pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="A2DATA PDF", version=__import__("a2pdf").__version__,
              docs_url="/api", redoc_url=None, lifespan=lifespan)
_hits: dict[str, deque] = {}


def _rate_ok(client: str) -> bool:
    """Простое ограничение частоты: RATE_LIMIT запросов с адреса в минуту."""
    now = time.monotonic()
    hits = _hits.setdefault(client, deque())
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= RATE_LIMIT:
        return False
    hits.append(now)
    if len(_hits) > 5000:  # не копим адреса бесконечно
        for key in [k for k, v in _hits.items() if not v]:
            _hits.pop(key, None)
    return True


def _check_url(raw: str) -> str:
    """Пускаем только http(s) на публичные адреса — сервис не должен ходить
    во внутреннюю сеть по чужой ссылке."""
    url = raw if "//" in raw else "https://" + raw
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ссылка должна начинаться с http или https")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("В ссылке нет адреса")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError("Адрес не найден")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            raise ValueError("Ссылки на внутренние адреса не принимаются")
    return url


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _secure(request: Request) -> bool:
    """Кука уходит только по https, если сервис за ним и стоит."""
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    return proto == "https"


def current_user(request: Request,
                 session: str | None = Cookie(default=None, alias=auth.COOKIE)
                 ) -> str:
    """Пускает по действующей сессии; без учётки — только с локальной машины."""
    if not AUTH.enabled:
        return "anonymous"
    if not AUTH.configured:
        if auth.is_local(_client(request)):
            return "local"
        raise HTTPException(503, "Сервис не настроен: не задана учётная запись")
    user = auth.validate(AUTH, session)
    if not user:
        raise HTTPException(401, "Нужно войти")
    return user


def _same_origin(request: Request) -> bool:
    """Простая защита от запросов с чужих страниц."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer", "")
    host = request.headers.get("host", "")
    if origin:
        return origin.split("//")[-1] == host
    if referer:
        return referer.split("//")[-1].split("/")[0] == host
    return True     # запросы без Origin: curl и подобное


@app.get("/brands-public")
def brands_public() -> JSONResponse:
    """Названия брендов для страницы входа: логотипы и ничего больше."""
    return JSONResponse({"brands": [b.logo for b in brands.BRANDS.values()]})


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request,
               session: str | None = Cookie(default=None, alias=auth.COOKIE)):
    if not AUTH.enabled:
        return RedirectResponse("/", status_code=303)
    if AUTH.configured and auth.validate(AUTH, session):
        return RedirectResponse("/", status_code=303)
    page = (STATIC / "login.html").read_text(encoding="utf-8")
    return HTMLResponse(page.replace("{{error}}", ""))


@app.post("/login")
def login(request: Request, response: Response,
          username: str = Form(...), password: str = Form(...)):
    if not _same_origin(request):
        raise HTTPException(400, "Запрос пришёл со стороннего адреса")
    client = _client(request)
    if not auth.attempt_allowed(client):
        raise HTTPException(429, "Слишком много попыток, подождите пять минут")
    if not auth.check(AUTH, username, password):
        auth.note_failure(client)
        log.warning("неудачный вход с %s", client)
        page = (STATIC / "login.html").read_text(encoding="utf-8")
        return HTMLResponse(
            page.replace("{{error}}",
                         '<div class="error">Неверный логин или пароль</div>'),
            status_code=401)
    auth.reset_attempts(client)
    value, max_age = auth.issue(AUTH, AUTH.user)
    redirect = RedirectResponse("/", status_code=303)
    redirect.set_cookie(auth.COOKIE, value, max_age=max_age, httponly=True,
                        samesite="lax", secure=_secure(request), path="/")
    log.info("вход: %s с %s", AUTH.user, client)
    return redirect


@app.post("/logout")
def logout(request: Request):
    redirect = RedirectResponse("/login", status_code=303)
    redirect.delete_cookie(auth.COOKIE, path="/")
    return redirect


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": app.version,
                         "chrome": getattr(app.state, "chrome", None),
                         "auth": AUTH.enabled,
                         "notion_token": bool(os.environ.get("NOTION_TOKEN")),
                         "workers": WORKERS})


@app.get("/brands")
def brand_list(user: str = Depends(current_user)) -> JSONResponse:
    """Организации, для которых сервис умеет верстать."""
    return JSONResponse({"brands": [
        {"key": brand.key, "name": brand.name, "site": brand.site,
         "colors": {"brand": brand.color("brand"),
                    "accent": brand.color("accent"),
                    "mark": brand.color("mark")}}
        for brand in brands.BRANDS.values()], "default": brands.DEFAULT})


@app.get("/fonts")
def font_sets(user: str = Depends(current_user)) -> JSONResponse:
    """Наборы шрифтов, которыми можно набрать документ."""
    return JSONResponse({"fonts": [
        {"key": f.key, "title": f.title, "body": f.body, "display": f.display}
        for f in brands.FONT_SETS.values()]})


@app.get("/schemes")
def diagram_schemes(brand: str | None = None,
                    user: str = Depends(current_user)) -> JSONResponse:
    """Шаблоны оформления для схем mermaid вместе с цветами для миниатюр."""
    picked = brands.get(brand)
    return JSONResponse({"schemes": [
        {"key": key, "title": preset["title"], "note": preset["note"],
         "preview": core.scheme_style(key, picked)["preview"]}
        for key, preset in core.DIAGRAM_SCHEMES.items()]})


@app.get("/covers")
def covers(user: str = Depends(current_user)) -> JSONResponse:
    """Список встроенных фонов обложки."""
    names = sorted(p.stem for p in COVERS.glob("*.jpg")) if COVERS.is_dir() else []
    return JSONResponse({"covers": names})


@app.get("/covers/{name}.jpg")
def cover_image(name: str, user: str = Depends(current_user)) -> FileResponse:
    path = COVERS / f"{pathlib.Path(name).stem}.jpg"
    if not path.is_file():
        raise HTTPException(404, "Такого фона нет")
    return FileResponse(path, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/logo/{name}")
def logo(name: str) -> FileResponse:
    """Логотип бренда: вектор, если он есть в брендбуке, иначе картинка."""
    stem = pathlib.Path(name).stem
    for suffix, media in ((".svg", "image/svg+xml"), (".png", "image/png")):
        path = core.ASSETS / "logo" / f"{stem}{suffix}"
        if path.is_file():
            return FileResponse(path, media_type=media,
                                headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(404, "Нет такого логотипа")


@app.get("/fonts.css")
def fonts(brand: str | None = None) -> FileResponse:
    """Те же шрифты, что уходят в документ, — без внешних CDN."""
    theme = brands.get(brand)
    return FileResponse(core.fonts_css_path(theme.key), media_type="text/css",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/", response_class=HTMLResponse)
def index(request: Request,
          session: str | None = Cookie(default=None, alias=auth.COOKIE)):
    if AUTH.enabled:
        if AUTH.configured and not auth.validate(AUTH, session):
            return RedirectResponse("/login", status_code=303)
        if not AUTH.configured and not auth.is_local(_client(request)):
            raise HTTPException(503,
                                "Сервис не настроен: не задана учётная запись")
    page = (STATIC / "index.html").read_text(encoding="utf-8")
    if not AUTH.enabled:
        page = page.replace('<form method="post" action="/logout">',
                            '<form method="post" action="/logout" hidden>')
    return HTMLResponse(page)


def _text(value: str) -> str:
    """Starlette отдаёт текстовые части multipart в latin-1 — возвращаем UTF-8."""
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _safe_stem(name: str) -> str:
    stem = pathlib.Path(_text(name)).stem
    stem = re.sub(r"[^\w .()\[\]-]+", "_", stem, flags=re.UNICODE).strip()
    stem = stem[:80].strip("_. ")
    return stem or "document"


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


def _blocks_of(source: dict, overrides: dict) -> tuple[list[tuple], dict, str]:
    """Блоки, настройки обложки и имя файла для любого источника."""
    kind = source["kind"]
    if kind == "file" and source["suffix"] == ".docx":
        blocks, front = docx_to_blocks(source["data"])
        if not blocks:
            raise ValueError("В документе не нашлось текста")
        front.setdefault("title", source["stem"])
        front.update(overrides)
        return blocks, front, source["stem"]

    if kind in ("file", "text"):
        text = (core.decode_text(source["data"])
                if kind == "file" else source["text"])
        if not text.strip():
            raise ValueError("Пустой текст")
        blocks, front = core.markdown_blocks(text, overrides)
        return blocks, front, source["stem"]

    url = source["url"]
    blocks, front = notion.load(url) if notion.is_notion(url) else fetch(url)
    front.update(overrides)
    return blocks, front, _safe_stem(str(front.get("title") or "document"))


def _discard(job) -> None:
    """Удаляет файл сборки, которую уже никто не ждёт."""
    try:
        out_path, _ = job.result()
    except Exception:
        return
    pathlib.Path(out_path).unlink(missing_ok=True)


def _convert(source: dict, overrides: dict, chrome: str,
             fmt: str = "pdf") -> tuple[pathlib.Path, str]:
    """Собирает документ и возвращает путь и предлагаемое имя файла."""
    blocks, front, stem = _blocks_of(source, overrides)
    out_path = OUT_DIR / f"{uuid.uuid4().hex}.{fmt}"

    if fmt == "png":
        sources = [b[1] for b in blocks if b[0] == "mermaid"]
        if not sources:
            raise ValueError("В тексте нет диаграммы mermaid")
        image, _ = core.diagram_images(sources[:1], front, chrome=chrome,
                                       dpi=PNG_DPI,
                                       scheme=front.get("scheme"))[0]
        out_path.write_bytes(image)
        return out_path, _safe_stem(str(front.get("title") or stem))

    core.render_document(blocks, front, out_path, fmt=fmt, chrome=chrome,
                         name=stem)
    return out_path, stem


def _format_of(requested: str | None) -> str:
    """Название формата из формы приводим к одному из трёх наших."""
    value = (requested or "").lower()
    if value in ("docx", "word"):
        return "docx"
    if value in ("png", "image"):
        return "png"
    return "pdf"


async def _read_source(file: UploadFile | None, text: str | None,
                       url: str | None) -> dict:
    """Файл, текст или ссылка — приводим к общему виду и проверяем пределы."""
    if file is not None and file.filename:
        suffix = pathlib.Path(file.filename).suffix.lower()
        if suffix not in ALLOWED:
            raise HTTPException(415, f"Поддерживаются {', '.join(sorted(ALLOWED))}")
        data = await file.read()
        if not data:
            raise HTTPException(400, "Пустой файл")
        if len(data) > MAX_BYTES:
            raise HTTPException(413, f"Файл больше {MAX_BYTES // 1024 // 1024} МБ")
        return {"kind": "file", "data": data, "suffix": suffix,
                "stem": _safe_stem(file.filename)}

    if text and text.strip():
        body = _text(text)
        if len(body.encode()) > MAX_BYTES:
            raise HTTPException(413, "Слишком много текста")
        return {"kind": "text", "text": body, "stem": "document"}

    if url and url.strip():
        try:
            return {"kind": "url", "url": _check_url(_text(url).strip())}
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    raise HTTPException(400, "Нужен файл, текст или ссылка")


def _look(fields: dict, style: str | None, brand: str | None, font: str | None,
          scheme: str | None, background: str | None, cover: str | None,
          numbered: str | None) -> dict:
    """Настройки оформления. Всё незнакомое отбрасываем: подпись обложки
    приходит от пользователя, а название бренда или схемы — нет."""
    overrides = _overrides(**fields)
    if style in ("light", "dark"):
        overrides["style"] = style
    overrides["brand"] = brands.get(brand).key
    if font and font in brands.FONT_SETS:
        overrides["font"] = font
    if scheme and scheme in core.DIAGRAM_SCHEMES:
        overrides["scheme"] = scheme
    if cover in ("0", "false", "off"):
        overrides["cover"] = "false"
    if numbered in ("0", "false", "off"):
        overrides["numbered"] = "false"
    if background:
        builtin = COVERS / f"{pathlib.Path(background).stem}.jpg"
        if builtin.is_file():
            overrides["photo"] = str(builtin)
    return overrides


async def _save_photo(photo: UploadFile | None) -> pathlib.Path | None:
    """Своё фото обложки кладём во временный файл — его читает сборка."""
    if photo is None or not photo.filename:
        return None
    suffix = pathlib.Path(photo.filename).suffix.lower()
    if suffix not in PHOTO_TYPES:
        raise HTTPException(415, "Фото должно быть jpg, png или webp")
    blob = await photo.read()
    if len(blob) > MAX_BYTES:
        raise HTTPException(413, "Фото слишком большое")
    path = OUT_DIR / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(blob)
    return path


@app.post("/convert")
async def convert(
    request: Request,
    user: str = Depends(current_user),
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
    brand: str | None = Form(None),
    font: str | None = Form(None),
    scheme: str | None = Form(None),
    format: str | None = Form(None),
    background: str | None = Form(None),
    cover: str | None = Form(None),
    numbered: str | None = Form(None),
):
    fmt = _format_of(format)
    if not _rate_ok(_client(request)):
        raise HTTPException(429, "Слишком много запросов, попробуйте через минуту")

    source = await _read_source(file, text, url)
    overrides = _look(
        {"title": title, "subtitle": subtitle, "kicker": kicker, "index": index,
         "header": header, "footer": footer, "confidential": confidential,
         "meta": meta},
        style, brand, font, scheme, background, cover, numbered)

    photo_path = await _save_photo(photo)
    if photo_path:
        overrides["photo"] = str(photo_path)

    started = time.monotonic()
    loop = asyncio.get_running_loop()
    async with app.state.slots:
        job = loop.run_in_executor(app.state.pool, _convert, source, overrides,
                                   app.state.chrome, fmt)
        try:
            out_path, stem = await asyncio.wait_for(asyncio.shield(job),
                                                    timeout=TIMEOUT)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # поток в пуле не остановить, поэтому убираем за ним результат сами:
            # иначе брошенные сборки копятся на диске
            job.add_done_callback(_discard)
            raise HTTPException(504, "Сборка заняла слишком много времени")
        except (ValueError, FetchError, notion.NotionError) as exc:
            raise HTTPException(400, str(exc))
        except Exception:
            log.exception("не удалось собрать документ (%s)", source["kind"])
            raise HTTPException(500, "Не удалось собрать PDF")
        finally:
            if photo_path:
                photo_path.unlink(missing_ok=True)

    log.info("%s: %s -> %s.%s, %.1f c, %d KB", user, source["kind"], stem, fmt,
             time.monotonic() - started, out_path.stat().st_size // 1024)
    return FileResponse(
        out_path, media_type=MIME[fmt], filename=f"{stem}.{fmt}",
        background=BackgroundTask(out_path.unlink, missing_ok=True))
