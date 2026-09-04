"""Разбор markdown и сборка документа: HTML со стилями бренда печатается
браузером в PDF, страницы склеиваются и получают колонтитулы.

    python -m a2pdf документ.md
    python -m a2pdf документ.md --brand becloud --docx

Оформление приходит из brands.py: цвета, шрифты, логотип. Шрифты встраиваются
в файл, диаграммы mermaid рисуются в палитре бренда.

Обложка и колонтитулы настраиваются front matter в начале md-файла:

    ---
    title: Rate Limiter
    subtitle: Ограничение частоты запросов
    kicker: Тестовое задание
    index: "01"
    brand: a2data
    font: inter
    confidential: Не для кандидатов
    header: Тестовое задание · Rate Limiter
    footer: Python Backend Developer · a2data.ai
    style: dark
    photo: cover.jpg
    numbered: true
    meta:
      Роль: Python Backend
      Таймбокс: 4 часа
    ---

Разметка внутри текста:

    <!--PART:Часть 2|Разбор для проверяющего-->   разделитель между частями
    <!--CAP:Пояснение под схемой-->               подпись к диаграмме
    <!--NUMBERING:off-->                          выключить нумерацию разделов
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import html
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid

import pymupdf

from . import brands
from .diagrams import (DEFAULT_SCHEME, DIAGRAM_SCHEMES, mermaid_init,
                       scheme_css, scheme_style, theme_diagram, tint)

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = pathlib.Path(os.environ.get("A2PDF_ASSETS") or HERE / "assets")
TMP = pathlib.Path(os.environ.get("A2PDF_TMP") or HERE / ".build")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
GOOGLE_FONTS = "https://fonts.googleapis.com/css2?family={query}&display=swap"
INTER_ZIP = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
FONT_SUBSETS = ("latin", "latin-ext", "cyrillic")

CHROME_CANDIDATES = [
    os.environ.get("A2PDF_CHROME", ""),
    "/usr/bin/chromium-browser", "/usr/bin/google-chrome-stable",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

SITE = "a2data.ai"
COMPANY = "A2DATA"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def fonts_css_path(font_key: str = brands.INTER.key) -> pathlib.Path:
    return ASSETS / f"fonts-{font_key}.css"


def ensure_assets(quiet: bool = False) -> None:
    """Скачивает шрифты каждого бренда и mermaid при первом запуске."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    say = (lambda *a: None) if quiet else print

    for fonts in brands.FONT_SETS.values():
        css = fonts_css_path(fonts.key)
        if css.exists():
            continue
        say(f"Скачиваю набор шрифтов «{fonts.title}»…")
        raw = _get(GOOGLE_FONTS.format(query=fonts.query)).decode("utf-8")
        faces, seen = [], set()
        for subset, block in re.findall(
                r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*\{[^}]+\})", raw):
            if subset not in FONT_SUBSETS:
                continue
            m = re.search(r"url\((https://[^)]+\.woff2)\)", block)
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            data = base64.b64encode(_get(m.group(1))).decode("ascii")
            # заменяем только сам url(...): format(...) в правиле уже есть,
            # второй такой же делает src невалидным и шрифт молча подменяется
            block = block.replace(
                m.group(0), 'url("data:font/woff2;base64,' + data + '")')
            # один вариативный файл на все веса — объявляем диапазон
            faces.append(re.sub(r"font-weight:\s*\d+;", "font-weight: 100 900;", block))
        css.write_text("\n".join(faces), encoding="utf-8")

    ttf = ASSETS / "Inter-Regular.ttf"
    if not ttf.exists():
        say("Скачиваю Inter для колонтитулов…")
        import io
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(_get(INTER_ZIP)))
        for src, dst in (("extras/ttf/Inter-Regular.ttf", "Inter-Regular.ttf"),
                         ("extras/ttf/Inter-ExtraBold.ttf", "Inter-ExtraBold.ttf")):
            (ASSETS / dst).write_bytes(z.read(src))

    mjs = ASSETS / "mermaid.min.js"
    if not mjs.exists():
        say("Скачиваю mermaid…")
        mjs.write_bytes(_get(MERMAID_JS))


BOMS = ((b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"))


def decode_text(data: bytes) -> str:
    """Текст файла в строку. Кодировку берём по метке в начале файла,
    иначе пробуем UTF-8 и cp1251: русские .md с Windows часто приходят
    в ней, а «replace» превратил бы их в квадраты."""
    for mark, encoding in BOMS:
        if data.startswith(mark):
            return data[len(mark):].decode(encoding, errors="replace")
    for encoding in ("utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def split_front_matter(md: str) -> tuple[dict, str]:
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end == -1:
        return {}, md
    head, body = md[3:end], md[end + 4:]
    meta: dict = {}
    current_key = None
    for line in head.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith((" ", "\t")) and current_key:
            k, _, v = line.strip().partition(":")
            meta.setdefault(current_key, {})[k.strip()] = v.strip().strip("\"'")
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip().strip("\"'")
        current_key = key
        if value:
            meta[key] = value
        else:
            meta[key] = {}
    return meta, body.lstrip("\n")


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    return text


def parse(md: str, keep_mermaid: bool = True) -> list[tuple]:
    """Markdown → список блоков. Поддерживается нужное подмножество разметки."""
    lines = md.split("\n")
    blocks: list[tuple] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        m = re.match(r"<!--CAP:(.+?)-->", stripped)
        if m:
            blocks.append(("cap", m.group(1).strip()))
            i += 1
            continue

        m = re.match(r"<!--NUMBERING:(on|off)-->", stripped)
        if m:
            blocks.append(("numbering", m.group(1) == "on"))
            i += 1
            continue

        m = re.match(r"<!--PART:([^|]+)\|([^-]+)-->", stripped)
        if m:
            blocks.append(("part", m.group(1).strip(), m.group(2).strip()))
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            if lang == "mermaid":
                if keep_mermaid:
                    blocks.append(("mermaid", "\n".join(buf)))
            else:
                blocks.append(("code", lang, "\n".join(buf)))
            continue

        if stripped.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append(("note", " ".join(buf)))
            continue

        m = re.match(r"^!\[[^\]]*\]\(([^)\s]+)\)$", stripped)
        if m:
            blocks.append(("image", m.group(1)))
            i += 1
            continue

        head = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if head:
            blocks.append((f"h{len(head.group(1))}", head.group(2)))
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
            blocks.append(("hr",))
            i += 1
            continue

        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in
                             lines[i].strip().strip("|").split("|")])
                i += 1
            body = [r for r in rows[1:]
                    if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
            blocks.append(("table", rows[0], body))
            continue

        if re.match(r"^[-*+] ", stripped) or re.match(r"^\d+[.)] ", stripped):
            ordered = bool(re.match(r"^\d+[.)] ", stripped))
            marker = r"^\d+[.)] " if ordered else r"^[-*+] "
            items: list[str] = []
            while i < len(lines):
                cur, s = lines[i], lines[i].strip()
                if not s:
                    nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    if re.match(marker, nxt):  # тот же тип списка — продолжаем
                        i += 1
                        continue
                    break
                if re.match(marker, s):
                    items.append(re.sub(r"^([-*+]|\d+[.)])\s+", "", s))
                elif cur.startswith(("  ", "\t")) and items:
                    items[-1] += " " + s
                else:
                    break
                i += 1
            blocks.append(("ol" if ordered else "ul", items))
            continue

        buf = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(#{1,4} |```|\||[-*+] |\d+[.)] |> |<!--|-{3,}$)", lines[i].strip()):
            buf.append(lines[i].strip())
            i += 1
        blocks.append(("p", " ".join(buf)))
    return blocks


META_STRIP = re.compile(r"^\*\*([^*]+):\*\*\s*(.+?)\s*·\s*\*\*([^*]+):\*\*\s*(.+)$")


def embed_image(src: str) -> str:
    """Локальный файл превращаем в data-URI, остальное отдаём как есть."""
    if src.startswith(("data:", "http://", "https://")):
        return src
    path = pathlib.Path(src)
    if not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


ATOMIC = re.compile(r"^[\w.,%+/()\u2212-]{1,24}$", re.UNICODE)


def _cell(text: str) -> str:
    """Короткое значение без пробелов не переносим: иначе id рвётся пополам."""
    value = inline(text)
    stripped = str(text).strip()
    if stripped and " " not in stripped and ATOMIC.match(stripped):
        return f'<span class="nb">{value}</span>'
    return value


def _table_class(columns: int) -> str:
    """Чем больше колонок, тем мельче набор — иначе колонки не помещаются."""
    if columns >= 8:
        return " class=\"xwide\""
    if columns >= 6:
        return " class=\"wide\""
    return ""


def render(blocks: list[tuple], brand: brands.Brand, numbered: bool = True,
           drop_h1: bool = True, scheme: str | None = None) -> str:
    out: list[str] = []
    n = 0
    for b in blocks:
        kind = b[0]
        if kind == "h1":
            if drop_h1:
                continue
            out.append(f'<div class="h2-wrap"><h2>{inline(b[1])}</h2></div>')
        elif kind == "h2":
            n += 1
            eye = f'<span class="eyebrow">{n:02d}</span>' if numbered else ""
            out.append(f'<div class="h2-wrap">{eye}<h2>{inline(b[1])}</h2></div>')
        elif kind in ("h3", "h4"):
            out.append(f"<h3>{inline(b[1])}</h3>")
        elif kind == "p":
            m = META_STRIP.match(b[1])
            if m:
                out.append('<div class="strip">'
                           f'<span><i>{html.escape(m.group(1))}</i>'
                           f'{html.escape(m.group(2))}</span>'
                           f'<span><i>{html.escape(m.group(3))}</i>'
                           f'{html.escape(m.group(4))}</span></div>')
            else:
                out.append(f"<p>{inline(b[1])}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in b[1]) + "</ul>")
        elif kind == "ol":
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in b[1]) + "</ol>")
        elif kind == "code":
            out.append(f'<pre class="code"><code>{html.escape(b[2])}</code></pre>')
        elif kind == "mermaid":
            style = scheme_style(scheme, brand)
            source = html.escape(theme_diagram(b[1], brand, style))
            out.append(f'<div class="dg dg-mermaid sch-{style["key"]}">'
                       f'<pre class="mermaid" data-source="{source}">'
                       f"{source}</pre></div>")
        elif kind == "note":
            out.append(f'<div class="note"><p>{inline(b[1])}</p></div>')
        elif kind == "table":
            head = "".join(f"<th>{inline(c)}</th>" for c in b[1])
            body = "".join("<tr>" + "".join(f"<td>{_cell(c)}</td>" for c in row)
                           + "</tr>" for row in b[2])
            out.append(f"<table{_table_class(len(b[1]))}>"
                       f"<thead><tr>{head}</tr></thead>"
                       f"<tbody>{body}</tbody></table>")
        elif kind == "image":
            src = embed_image(b[1])
            if src:
                out.append(f'<figure class="fig"><img src="{src}" alt=""></figure>')
        elif kind == "cap":
            out.append(f'<div class="fig-cap">{inline(b[1])}</div>')
        elif kind == "part":
            out.append(f'<div class="part"><div class="lbl">{html.escape(b[1])}</div>'
                       f'<div class="ttl">{html.escape(b[2])}</div></div>')
        elif kind == "numbering":
            numbered = b[1]
        elif kind == "hr":
            out.append('<div class="rule"></div>')
    return "\n".join(out)


BASE = """
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:var(--font);color:var(--n700);font-variant-numeric:tabular-nums}
"""

COVER_CSS = BASE + """
@page{size:A4;margin:0}
body{width:210mm;height:296.5mm;overflow:hidden}
.cover{position:relative;width:210mm;height:296.5mm;padding:26mm 24mm 22mm;
       display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;
       background:var(--brand);color:#fff;
       --line:rgba(255,255,255,.20); --muted:var(--muted-on-dark); --strong:#fff}
/* мягкое свечение в углу, чтобы синий не был плоским */
.cover::after{content:"";position:absolute;top:-80mm;right:-60mm;width:200mm;height:200mm;
  border-radius:50%;background:var(--cover-glow)}

/* обложка с фотографией: дуотон — осветлённый ч/б снимок под синим слоем */
.cover.photo::after{display:none}

/* светлый вариант */
.cover.light{background:var(--n0);color:var(--brand);
       --line:var(--n200); --muted:var(--n500); --strong:var(--brand)}
.cover.light::after{display:none}

.cover>*{position:relative;z-index:1}
/* фоновые слои должны остаться абсолютными, поэтому селекторы точнее */
.cover>.bg,.cover>.tint{position:absolute;inset:0;display:none;z-index:0}
.cover.photo>.bg{display:block;background-image:var(--photo);background-size:cover;
  background-position:center;filter:grayscale(1) brightness(1.45) contrast(.95)}
.cover.photo>.tint{display:block;mix-blend-mode:multiply;background:var(--cover-tint)}
.cover>.mark{position:absolute;left:24mm;top:26mm;width:18mm;height:1mm;
  background:var(--mark);z-index:2}

.top{display:flex;justify-content:space-between;align-items:baseline;padding-top:8mm}
.wordmark{width:var(--logo-width);line-height:0}
.wordmark svg,.wordmark img{width:100%;height:auto;display:block}
.top .role{font-family:var(--mono);font-size:7.4pt;letter-spacing:2px;
           text-transform:uppercase;color:var(--muted)}

.mid{padding-bottom:6mm}
.kick{font-family:var(--mono);font-size:8pt;letter-spacing:2.4px;text-transform:uppercase;
      color:var(--accent);margin-bottom:8mm;display:flex;gap:3mm}
.kick .num{color:var(--muted)}
h1{font-family:var(--display);font-size:34pt;font-weight:var(--display-weight);
   letter-spacing:var(--display-tracking);line-height:1.08;max-width:152mm;
   color:var(--strong);overflow-wrap:anywhere}
.sub{font-size:12pt;line-height:1.5;color:var(--muted);margin-top:7mm;max-width:122mm;
     font-weight:400}
.chip{display:inline-block;border:.25mm solid var(--mark);color:var(--mark);
      font-size:7.4pt;font-weight:600;letter-spacing:1.4px;text-transform:uppercase;
      padding:1.6mm 3.4mm;border-radius:1mm;margin-bottom:7mm}
.cover.light .chip{color:var(--amber-700)}

.bottom{border-top:.25mm solid var(--line);padding-top:6mm}
.spec{display:grid;gap:6mm}
.spec .k{font-size:7pt;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}
.spec .v{font-family:var(--mono);font-size:9.2pt;color:var(--strong);margin-top:1.4mm;
         white-space:nowrap}
.foot{display:flex;justify-content:space-between;margin-top:8mm;font-family:var(--mono);
      font-size:7.6pt;letter-spacing:.5px;color:var(--muted)}
.foot .site{color:var(--strong)}
"""

BODY_CSS = BASE + """
@page{size:A4;margin:24mm 17mm 22mm}
body{font-size:10.2pt;line-height:1.55}
.h2-wrap{display:flex;align-items:baseline;gap:3.5mm;margin:10mm 0 4mm;
         padding-top:3.5mm;border-top:.25mm solid var(--n200);break-after:avoid}
.h2-wrap:first-child{margin-top:0;padding-top:0;border-top:0}
.eyebrow{font-family:var(--mono);font-size:8pt;font-weight:700;color:var(--accent);
         letter-spacing:.5px}
h2{font-family:var(--display);font-size:15pt;font-weight:var(--display-weight);
   color:var(--brand);letter-spacing:var(--display-tracking);line-height:1.2}
h3{font-size:10.6pt;font-weight:600;color:var(--n900);margin:5mm 0 2mm;
   break-after:avoid;break-inside:avoid}
p{margin:0 0 3mm;orphans:2;widows:2}
strong{color:var(--n900);font-weight:600}
code,pre.code code{font-variant-ligatures:none;font-feature-settings:"liga" 0,"calt" 0}
code{font-family:var(--mono);font-size:8.6pt;background:var(--brand-50);color:var(--brand);
     padding:.3mm 1.2mm;border-radius:.8mm;border:.2mm solid var(--brand-100)}
ul,ol{margin:0 0 4mm;padding:0;list-style:none}
li{position:relative;padding-left:8mm;margin-bottom:1.6mm;break-inside:avoid}
ul>li::before{content:"";position:absolute;left:2.5mm;top:2.1mm;width:1.3mm;height:1.3mm;
              background:var(--accent);border-radius:.3mm}
ol{counter-reset:ol}
ol>li{counter-increment:ol}
ol>li::before{content:counter(ol,decimal-leading-zero);position:absolute;left:0;top:.6mm;
              font-family:var(--mono);font-size:7.6pt;font-weight:700;color:var(--accent-dark)}
.rule{height:.25mm;background:var(--n200);margin:8mm 0}
.strip{display:flex;gap:9mm;border-top:.5mm solid var(--brand);
       border-bottom:.25mm solid var(--n200);padding:2.5mm 0;margin:0 0 6mm}
.strip span{font-size:9pt;color:var(--n900)}
.strip i{display:block;font-style:normal;font-size:7pt;letter-spacing:1.4px;
         text-transform:uppercase;color:var(--n400);margin-bottom:.8mm}
pre.code{background:var(--n50);border:.25mm solid var(--n200);
         border-left:.9mm solid var(--accent);border-radius:2mm;padding:4.5mm 5.5mm;
         margin:0 0 4.5mm;break-inside:auto}
pre.code code{font-family:var(--mono);font-size:8.4pt;line-height:1.55;background:none;
              border:0;padding:0;color:var(--n900);white-space:pre-wrap;
              word-break:break-word}
table{width:100%;border-collapse:collapse;margin:0 0 4mm;font-size:9pt}
thead{display:table-header-group}   /* шапка повторяется на каждой странице */
tr{break-inside:avoid}
th{background:var(--brand);color:#fff;text-align:left;font-weight:600;padding:3mm 3.2mm;
   font-size:8.4pt;letter-spacing:.2px;vertical-align:bottom}
th strong,th code,th a{color:#fff;background:none;border:0}
/* перенос только там, где слово шире колонки: иначе рвутся слова и числа */
td,th{overflow-wrap:break-word;word-break:normal;hyphens:none}
td{padding:2.8mm 3.2mm;border-bottom:.25mm solid var(--n100);vertical-align:top;
   line-height:1.45}
.nb{white-space:nowrap}                 /* id, суммы, проценты — целиком */
table.wide{font-size:8pt}
table.wide th{padding:2.4mm 2.4mm;font-size:7.6pt}
table.wide td{padding:2.2mm 2.4mm}
table.xwide{font-size:7.4pt}
table.xwide th{padding:2mm 2mm;font-size:7pt;letter-spacing:0}
table.xwide td{padding:1.9mm 2mm;line-height:1.35}
tbody tr:nth-child(even) td{background:var(--n50)}
.note{border-left:.9mm solid var(--mark);background:var(--mark-50);padding:4mm 5.5mm;
      margin:0 0 4.5mm;border-radius:0 2mm 2mm 0;break-inside:avoid}
.note p{margin:0;font-size:9.4pt}
.dg{border:.25mm solid var(--n200);border-radius:2mm;background:var(--n0);padding:6mm;
    margin:0 0 5mm;break-inside:avoid}
.dg-mermaid{text-align:center;padding:4mm}
.broken-diagram{text-align:left;color:var(--n700)}
.dg.sch-soft{background:var(--n50)}
.dg.sch-dark{background:var(--brand-dark);border-color:var(--brand-dark)}
.dg.sch-clear{background:none;border:0}
.dg-mermaid svg{max-width:100%;max-height:198mm;width:auto;height:auto}
.fig{margin:0 0 5mm;text-align:center;break-inside:avoid}
.fig img{max-width:100%;max-height:150mm;border-radius:1.4mm}
.fig-cap{margin:-3.5mm 0 5mm;text-align:center;font-size:8.4pt;font-style:italic;
         color:var(--n500);break-before:avoid;break-inside:avoid}
.dg-row{margin-bottom:3mm}
.dg-row:last-of-type{margin-bottom:0}
.dg-lab{font-size:7.4pt;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;
        color:var(--n400);margin-bottom:2mm}
.dg-chain{display:flex;align-items:center;flex-wrap:wrap;gap:2mm}
.dg-node{display:inline-block;padding:2mm 3.2mm;border-radius:1.4mm;font-size:8.6pt;
         font-weight:500;border:.25mm solid var(--n200);background:#fff;color:var(--n900)}
.dg-node.dg-a{background:var(--brand);border-color:var(--brand);color:#fff;font-weight:600}
.dg-node.dg-s{background:var(--accent-50);border-color:#BFE3FF;color:var(--accent-dark);
              font-weight:600}
.dg-arrow{color:var(--n400);font-size:10pt;line-height:1}
.dg-fan{display:inline-flex;flex-direction:column;gap:1.2mm}
.dg-fan span{padding:1.4mm 3.2mm;border:.25mm solid var(--n200);border-radius:1.4mm;
             background:#fff;font-size:8.4pt;color:var(--n900)}
.dg-cap{font-size:8.2pt;color:var(--n500);margin-top:3.5mm;padding-top:2.5mm;
        border-top:.25mm dashed var(--n200)}
.dg-steps{display:flex;flex-direction:column;gap:1.6mm}
.dg-step{display:flex;align-items:baseline;gap:3mm;font-size:8.8pt}
.dg-num{flex:none;font-family:var(--mono);font-size:7.4pt;font-weight:700;
        color:var(--accent-dark)}
.dg-actor{flex:none;width:26mm;font-weight:600;color:var(--brand)}
.dg-act{color:var(--n700)}
.dg-act code{font-size:8pt}
.part{margin:11mm 0 6mm;padding-top:4mm;border-top:.5mm solid var(--brand);
      break-after:avoid;break-inside:avoid;display:flex;align-items:baseline;gap:4mm}
.part .lbl{font-family:var(--mono);font-size:7.6pt;font-weight:700;letter-spacing:1.4px;
           text-transform:uppercase;color:var(--mark)}
.part .ttl{font-size:13pt;font-weight:700;color:var(--brand);letter-spacing:-.3px}
"""



COVER_TPL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<style>{fonts}</style><style>{css}</style></head><body>
<div class="cover {style}"{cover_style}>
  <div class="bg"></div>
  <div class="tint"></div>
  <div class="mark"></div>
  <div class="top">
    <div class="wordmark">{logo}</div>
    <div class="role">{role}</div>
  </div>
  <div class="mid">
    {chip}
    {kicker}
    <h1>{title_text}</h1>
    {subtitle}
  </div>
  <div class="bottom">
    <div class="spec" style="grid-template-columns:repeat({cols},1fr)">{spec}</div>
    <div class="foot"><span>{foot_left}</span><span class="site">{site}</span></div>
  </div>
</div></body></html>
"""

BODY_TPL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<style>{fonts}</style><style>{css}</style></head><body>
{content}
{mermaid}
</body></html>
"""

MM = 72 / 25.4
NAVY = (0x0B / 255, 0x26 / 255, 0x60 / 255)
BLUE = (0x1F / 255, 0xA8 / 255, 0xFC / 255)
GRAY = (0x9C / 255, 0xA3 / 255, 0xAF / 255)
LINE = (0xE1 / 255, 0xE4 / 255, 0xEA / 255)


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if path and pathlib.Path(path).exists():
            return path
    sys.exit("Не найден Chrome или Edge — они нужны для печати PDF.")


def print_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path, chrome: str,
              wait_ms: int) -> None:
    """Печатает HTML в PDF. Каждому запуску нужен свой профиль: иначе Chrome
    передаёт работу уже запущенному инстансу и молча ничего не печатает."""
    url = "file:///" + str(html_path).replace("\\", "/")
    TMP.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="chrome-", dir=TMP)
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             f"--user-data-dir={profile}",
             "--no-pdf-header-footer", "--print-to-pdf-no-header",
             f"--print-to-pdf={pdf_path}", f"--virtual-time-budget={wait_ms}",
             "--allow-file-access-from-files", url],
            check=True, capture_output=True, timeout=max(60, wait_ms // 1000 + 45))
        if not pdf_path.exists():
            raise RuntimeError("Chrome не создал PDF")
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def stamp(doc: pymupdf.Document, header_right: str, footer_left: str,
          skip_first: bool, brand: brands.Brand | None = None) -> None:
    """Рисует колонтитулы: логотип бренда, название и номера страниц."""
    brand = brand or brands.get(None)
    reg = pymupdf.Font(fontfile=str(ASSETS / "Inter-Regular.ttf"))
    bold = pymupdf.Font(fontfile=str(ASSETS / "Inter-ExtraBold.ttf"))
    main = _rgb(brand.color("brand"))
    accent = _rgb(brand.color("accent"))
    total = doc.page_count
    for idx, page in enumerate(doc, start=1):
        if skip_first and idx == 1:
            continue
        w, h = page.rect.width, page.rect.height
        left, right = 17 * MM, w - 17 * MM
        top_y, bot_y = 13 * MM, h - 11.5 * MM

        navy_tw, blue_tw, gray_tw = (pymupdf.TextWriter(page.rect) for _ in range(3))
        logo = LOGO_DIR / f"{brand.logo}-color.png"
        if logo.is_file():
            page.insert_image(pymupdf.Rect(left, top_y - 6.6, left + 26.5,
                                           top_y + 1.4),
                              filename=str(logo), keep_proportion=True)
        else:
            navy_tw.append((left, top_y), brand.name, font=bold, fontsize=8)
        if header_right:
            gray_tw.append((right - reg.text_length(header_right, 7.5), top_y),
                           header_right, font=reg, fontsize=7.5)
        if footer_left:
            gray_tw.append((left, bot_y), footer_left, font=reg, fontsize=7.5)
        num = f"{idx:02d} / {total:02d}"
        navy_tw.append((right - reg.text_length(num, 7.5), bot_y), num,
                       font=reg, fontsize=7.5)

        page.draw_line(pymupdf.Point(left, 15.5 * MM),
                       pymupdf.Point(right, 15.5 * MM), color=LINE, width=0.5)
        page.draw_line(pymupdf.Point(left, h - 15.5 * MM),
                       pymupdf.Point(right, h - 15.5 * MM), color=LINE, width=0.5)
        navy_tw.write_text(page, color=main)
        blue_tw.write_text(page, color=accent)
        gray_tw.write_text(page, color=GRAY)


def save(doc: pymupdf.Document, pdf_path: pathlib.Path) -> pathlib.Path:
    try:
        doc.save(pdf_path, garbage=4, deflate=True)
    except Exception:  # файл открыт в просмотрщике
        pdf_path = pdf_path.with_suffix(".new.pdf")
        doc.save(pdf_path, garbage=4, deflate=True)
        print(f"  файл занят другим приложением, сохранил как {pdf_path.name}")
    return pdf_path


def _cover_class(front: dict) -> str:
    brand = brands.get(front.get("brand"))
    classes = []
    if str(front.get("style", brand.cover_style)).lower() == "light":
        classes.append("light")
    if front.get("photo"):
        classes.append("photo")
    return " ".join(classes)


def _cover_bg(front: dict) -> str:
    """Фото на обложке: локальный файл встраиваем, ссылку оставляем как есть."""
    photo = str(front.get("photo") or "").strip()
    if not photo:
        return ""
    src = embed_image(photo)
    return f' style="--photo:url({src})"' if src else ""


LOGO_DIR = ASSETS / "logo"


def logo_svg(brand: brands.Brand, on_dark: bool) -> str:
    """Логотип из брендбука: вектор, если он есть, иначе картинка."""
    tone = "white" if on_dark else "color"
    vector = LOGO_DIR / f"{brand.logo}-{tone}.svg"
    if vector.is_file():
        return vector.read_text(encoding="utf-8")
    raster = LOGO_DIR / f"{brand.logo}-{tone}.png"
    if raster.is_file():
        data = base64.b64encode(raster.read_bytes()).decode("ascii")
        return f'<img src="data:image/png;base64,{data}" alt="">'
    return ""


def cover_html(front: dict) -> str:
    """HTML обложки: используется и для PDF, и для картинки в .docx."""
    ensure_assets(quiet=True)
    brand = brands.get(front.get("brand"))
    fonts = brands.fonts_for(brand, front.get("font"))
    fonts_css = fonts_css_path(fonts.key).read_text(encoding="utf-8")
    meta_items = list((front.get("meta") or {}).items())
    spec = "".join(f'<div><div class="k">{html.escape(str(k))}</div>'
                   f'<div class="v">{html.escape(str(v))}</div></div>'
                   for k, v in meta_items)
    return COVER_TPL.format(
        title=html.escape(str(front.get("title", ""))), fonts=fonts_css,
        css=(brands.tokens(brand, fonts)
             + f":root{{--logo-width:{brand.logo_width_mm}mm}}" + COVER_CSS),
        role=html.escape(str(front.get("role", brand.tagline))),
        chip=(f'<div class="chip">{html.escape(str(front["confidential"]))}</div>'
              if front.get("confidential") else ""),
        logo=logo_svg(brand, str(front.get("style", brand.cover_style)).lower()
                      != "light" or bool(front.get("photo"))),
        kicker=_kicker(front), style=_cover_class(front),
        cover_style=_cover_bg(front),
        title_text=html.escape(str(front.get("title", ""))),
        subtitle=(f'<div class="sub">{html.escape(str(front["subtitle"]))}</div>'
                  if front.get("subtitle") else ""),
        cols=max(1, len(meta_items)) if meta_items else 1, spec=spec,
        foot_left=html.escape(str(front.get("place", brand.place))),
        site=brand.site)


def _kicker(front: dict) -> str:
    """Строка над заголовком: номер документа и надпись."""
    parts = []
    if front.get("index"):
        parts.append(f'<span class="num">{html.escape(str(front["index"]))}</span>')
    if front.get("kicker"):
        parts.append(f'<span>{html.escape(str(front["kicker"]))}</span>')
    return f'<div class="kick">{"".join(parts)}</div>' if parts else ""


def render_pdf(blocks: list[tuple], front: dict, out_path: pathlib.Path,
               chrome: str | None = None, name: str = "document") -> pathlib.Path:
    """Собирает PDF из уже разобранных блоков и словаря настроек обложки."""
    ensure_assets(quiet=True)
    chrome = chrome or find_chrome()
    TMP.mkdir(parents=True, exist_ok=True)

    if not front.get("title"):
        h1 = next((b[1] for b in blocks if b[0] == "h1"), name)
        front["title"] = re.sub(r"^Задание\s+\d+\.\s*", "", h1)

    numbered = str(front.get("numbered", "true")).lower() not in ("false", "0", "no")
    has_mermaid = any(b[0] == "mermaid" for b in blocks)
    brand = brands.get(front.get("brand"))
    fonts = brands.fonts_for(brand, front.get("font"))
    fonts_css = fonts_css_path(fonts.key).read_text(encoding="utf-8")
    scheme = front.get("scheme")
    doc_style = scheme_style(scheme, brand)
    content = render(blocks, brand, numbered=numbered, scheme=scheme)

    mermaid_tag = ""
    if has_mermaid:
        lib = (ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
        mermaid_tag = (f"<style>{scheme_css(doc_style)}</style>"
                       f"<script>{lib}</script>"
                       f"<script type=\"module\">"
                       f"{mermaid_init(brand, fonts, doc_style)}"
                       "</script>")

    # имя должно быть уникальным на процесс и поток: соседняя сборка
    # с тем же названием иначе перетрёт временные файлы
    stem = re.sub(r"[^\w.-]+", "_", name)[:50] + f"-{uuid.uuid4().hex[:12]}"
    body_html = TMP / f"{stem}-body.html"
    body_html.write_text(BODY_TPL.format(
        title=html.escape(str(front["title"])), fonts=fonts_css,
        css=brands.tokens(brand, fonts) + BODY_CSS,
        content=content, mermaid=mermaid_tag), encoding="utf-8")
    body_pdf = TMP / f"{stem}-body.pdf"
    print_pdf(body_html, body_pdf, chrome, 15000 if has_mermaid else 5000)

    with_cover = str(front.get("cover", "true")).lower() not in ("false", "0", "no")
    doc = pymupdf.open()
    if with_cover:
        cover_path = TMP / f"{stem}-cover.html"
        cover_path.write_text(cover_html(front), encoding="utf-8")
        cover_pdf = TMP / f"{stem}-cover.pdf"
        print_pdf(cover_path, cover_pdf, chrome, 3000)
        doc.insert_pdf(pymupdf.open(cover_pdf))
    doc.insert_pdf(pymupdf.open(body_pdf))

    stamp(doc, str(front.get("header", front["title"])),
          str(front.get("footer", "")), skip_first=with_cover, brand=brand)
    doc.set_metadata({"title": str(front["title"]), "author": brand.name,
                      "subject": str(front.get("subtitle", "")),
                      "creator": brand.name})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = save(doc, out_path)
    doc.close()
    for tmp in TMP.glob(f"{stem}-*"):  # промежуточные html/pdf не нужны
        tmp.unlink(missing_ok=True)
    return result


def diagram_html(sources: list[str], brand: brands.Brand, fonts: brands.Fonts,
                 scheme: str | None = None) -> str:
    """Страница с диаграммами: по одной на лист, в цветах бренда."""
    style = scheme_style(scheme, brand)
    fonts_css = fonts_css_path(fonts.key).read_text(encoding="utf-8")
    lib = (ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
    body = "".join(
        '<div class="page"><div class="dg dg-mermaid">'
        f'<pre class="mermaid" data-source="{html.escape(theme_diagram(src, brand, style))}">'
        f'{html.escape(theme_diagram(src, brand, style))}'
        "</pre></div></div>" for src in sources)
    return ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f"<style>{fonts_css}</style>"
            f"<style>{brands.tokens(brand, fonts)}{BODY_CSS}"
            "@page{size:A4;margin:8mm}"
            "body{background:none}"
            ".page{break-after:page;display:flex;align-items:center;"
            "justify-content:center;height:281mm}"
            ".dg{border:0;margin:0;padding:6mm;width:100%;"
            f'{style["backdrop"]}'
            "}"
            ".dg-mermaid svg{max-height:275mm}"
            f"{scheme_css(style)}"
            f"</style></head><body>{body}"
            f"<script>{lib}</script>"
            '<script type="module">'
            f'{mermaid_init(brand, fonts, style)}</script>'
            "</body></html>")


def content_box(page) -> pymupdf.Rect:
    """Прямоугольник вокруг нарисованного — чтобы не тащить поля страницы."""
    box = pymupdf.Rect()
    for drawing in page.get_drawings():
        box |= drawing["rect"]
    for word in page.get_text("words"):
        box |= pymupdf.Rect(word[:4])
    if box.is_empty or box.is_infinite:
        return page.rect
    box += (-6, -6, 6, 6)
    return box & page.rect


def diagram_images(sources: list[str], front: dict, chrome: str | None = None,
                   dpi: int = 150, name: str = "diagram",
                   scheme: str | None = None) -> list[tuple[bytes, float]]:
    """Картинки диаграмм и соотношение сторон каждой."""
    if not sources:
        return []
    ensure_assets(quiet=True)
    chrome = chrome or find_chrome()
    brand = brands.get(front.get("brand"))
    fonts = brands.fonts_for(brand, front.get("font"))
    TMP.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", name)[:40] + f"-{uuid.uuid4().hex[:12]}"
    html_path = TMP / f"{stem}-dg.html"
    pdf_path = TMP / f"{stem}-dg.pdf"
    key = scheme if scheme is not None else front.get("scheme")
    preset = scheme_style(key, brand)
    html_path.write_text(diagram_html(sources, brand, fonts, key),
                         encoding="utf-8")
    try:
        print_pdf(html_path, pdf_path, chrome, 15000)
        images = []
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                pixmap = page.get_pixmap(dpi=dpi, clip=content_box(page),
                                         alpha=preset["clear"])
                images.append((pixmap.tobytes("png"),
                               pixmap.height / max(pixmap.width, 1)))
        return images
    finally:
        html_path.unlink(missing_ok=True)
        pdf_path.unlink(missing_ok=True)


def render_document(blocks: list[tuple], front: dict, out_path: pathlib.Path,
                    fmt: str = "pdf", chrome: str | None = None,
                    name: str = "document") -> pathlib.Path:
    """Собирает документ в нужном формате: pdf или docx."""
    if fmt == "docx":
        from .docx_writer import write_docx  # python-docx нужен только здесь

        return write_docx(blocks, front, out_path, chrome=chrome, name=name)
    return render_pdf(blocks, front, out_path, chrome=chrome, name=name)


def markdown_blocks(text: str, overrides: dict | None = None,
                    append_texts: list[str] | None = None
                    ) -> tuple[list[tuple], dict]:
    """Блоки и настройки обложки из markdown-строки с учётом front matter."""
    front, body = split_front_matter(text)
    front.update({k: v for k, v in (overrides or {}).items() if v is not None})
    keep_mm = str(front.get("mermaid", "true")).lower() not in (
        "false", "0", "off", "no")
    blocks = parse(body, keep_mermaid=keep_mm)
    for extra in append_texts or []:
        _, extra_body = split_front_matter(extra)
        blocks += parse(extra_body, keep_mermaid=keep_mm)
    return blocks, front


def build_markdown(text: str, out_path: pathlib.Path, overrides: dict | None = None,
                   append_texts: list[str] | None = None,
                   chrome: str | None = None, name: str = "document",
                   fmt: str = "pdf") -> pathlib.Path:
    """Собирает документ из markdown-строки (front matter учитывается)."""
    blocks, front = markdown_blocks(text, overrides, append_texts)
    return render_document(blocks, front, out_path, fmt=fmt, chrome=chrome,
                           name=name)


def build(md_path: pathlib.Path, out_path: pathlib.Path | None = None,
          overrides: dict | None = None,
          append: list[pathlib.Path] | None = None,
          chrome: str | None = None, quiet: bool = False,
          fmt: str = "pdf") -> pathlib.Path:
    """Собирает документ из markdown-файла и возвращает путь к результату."""
    ensure_assets(quiet=quiet)
    out_path = out_path or md_path.with_suffix(".docx" if fmt == "docx" else ".pdf")
    result = build_markdown(
        md_path.read_text(encoding="utf-8"), out_path, overrides=overrides,
        append_texts=[p.read_text(encoding="utf-8") for p in (append or [])],
        chrome=chrome, name=md_path.stem, fmt=fmt)
    if not quiet:
        _report(result)
    return result


def build_any(path: pathlib.Path, out_path: pathlib.Path | None = None,
              overrides: dict | None = None,
              append: list[pathlib.Path] | None = None,
              chrome: str | None = None, quiet: bool = False,
              fmt: str = "pdf") -> pathlib.Path:
    """Собирает документ из .md или .docx в формате pdf или docx."""
    suffix = ".docx" if fmt == "docx" else ".pdf"
    if out_path is None:
        out_path = path.with_name(path.stem + suffix)
        if out_path == path:  # docx -> docx: не затираем исходник
            out_path = path.with_name(path.stem + "-a2data" + suffix)
    if path.suffix.lower() != ".docx":
        return build(path, out_path, overrides=overrides, append=append,
                     chrome=chrome, quiet=quiet, fmt=fmt)

    from .docx_reader import docx_to_blocks  # mammoth нужен только для docx

    ensure_assets(quiet=quiet)
    blocks, front = docx_to_blocks(path.read_bytes())
    if not blocks:
        raise ValueError(f"{path.name}: в документе не нашлось текста")
    front.setdefault("title", path.stem)
    front.update({k: v for k, v in (overrides or {}).items() if v is not None})
    for extra in append or []:
        extra_front, extra_md = split_front_matter(extra.read_text(encoding="utf-8"))
        blocks += parse(extra_md)
    result = render_document(blocks, front, out_path, fmt=fmt, chrome=chrome,
                             name=path.stem)
    if not quiet:
        _report(result)
    return result


def _report(path: pathlib.Path) -> None:
    size = path.stat().st_size // 1024
    if path.suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            print(f"{path}  —  {doc.page_count} стр., {size} KB")
    else:
        print(f"{path}  —  {size} KB")


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # консоль может не знать «—» и «…»
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        prog="a2pdf",
        description="Markdown и Word в PDF в оформлении A2DATA")
    ap.add_argument("files", nargs="+", type=pathlib.Path,
                    help="файлы .md или .docx")
    ap.add_argument("-o", "--out", type=pathlib.Path,
                    help="имя файла результата (для одного входного файла) "
                         "или папка (для нескольких)")
    ap.add_argument("--title"), ap.add_argument("--subtitle")
    ap.add_argument("--kicker", help="надпись над заголовком на обложке")
    ap.add_argument("--index", help="крупная цифра на обложке, например 01")
    ap.add_argument("--footer", help="левый нижний колонтитул")
    ap.add_argument("--header", help="правый верхний колонтитул")
    ap.add_argument("--confidential", nargs="?", const="Конфиденциально",
                    help="янтарная плашка на обложке")
    ap.add_argument("--meta", action="append", default=[], metavar="КЛЮЧ=ЗНАЧЕНИЕ",
                    help="поле таблицы на обложке, можно повторять")
    ap.add_argument("--no-cover", action="store_true", help="без обложки")
    ap.add_argument("--no-numbers", action="store_true",
                    help="не нумеровать разделы")
    ap.add_argument("--append", action="append", default=[], type=pathlib.Path,
                    help="дописать в конец ещё один md")
    ap.add_argument("--brand", choices=sorted(brands.BRANDS),
                    help="организация: чьё оформление применять")
    ap.add_argument("--font", choices=sorted(brands.FONT_SETS),
                    help="набор шрифтов; по умолчанию — из брендбука")
    ap.add_argument("--docx", action="store_true",
                    help="собрать .docx вместо PDF")
    ap.add_argument("--photo", help="фото на обложку: путь к файлу или ссылка")
    ap.add_argument("--style", choices=("dark", "light"),
                    help="цвет обложки: синяя (dark) или светлая")
    ap.add_argument("--no-mermaid", action="store_true",
                    help="не рисовать диаграммы mermaid")
    args = ap.parse_args(argv)

    overrides: dict = {}
    for name in ("title", "subtitle", "kicker", "index", "footer", "header",
                 "photo", "style", "brand", "font"):
        if getattr(args, name):
            overrides[name] = getattr(args, name)
    if args.confidential:
        overrides["confidential"] = args.confidential
    if args.no_cover:
        overrides["cover"] = "false"
    if args.no_numbers:
        overrides["numbered"] = "false"
    if args.no_mermaid:
        overrides["mermaid"] = "false"
    if args.meta:
        overrides["meta"] = dict(kv.split("=", 1) for kv in args.meta)

    chrome = find_chrome()

    fmt = "docx" if args.docx else "pdf"
    files = [f for f in args.files
             if f.suffix.lower() in (".md", ".markdown", ".docx")]
    if not files:
        sys.exit("Не передано ни одного файла .md или .docx")
    for f in files:
        out = None
        if args.out:
            out = args.out / f.with_suffix(".pdf").name if (
                len(files) > 1 or args.out.is_dir()) else args.out
        build_any(f, out, overrides=overrides, append=args.append,
                  chrome=chrome, fmt=fmt)


if __name__ == "__main__":
    main()
