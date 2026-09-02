"""a2pdf — markdown в PDF в фирменном оформлении A2DATA.

    python tools/a2pdf.py документ.md
    python tools/a2pdf.py документ.md -o готовый.pdf --confidential
    python tools/a2pdf.py папка/*.md

Оформление берётся из брендбука: navy #0B2660, blue #1FA8FC, amber #FF9F1C,
Inter + JetBrains Mono. Шрифты встраиваются в PDF, диаграммы mermaid рисуются
в брендовой теме.

Обложка и колонтитулы настраиваются front matter в начале md-файла:

    ---
    title: Rate Limiter                  # по умолчанию — первый H1
    subtitle: Ограничение частоты запросов
    kicker: Тестовое задание             # надпись над заголовком
    index: "01"                          # крупная цифра на обложке
    confidential: Не для кандидатов      # янтарная плашка
    footer: Python Backend Developer     # левый нижний колонтитул
    header: Тестовое задание · 01        # правый верхний колонтитул
    numbered: true                       # нумеровать разделы H2
    meta:
      Роль: Python Backend
      Таймбокс: 4 часа
    ---

Дополнительная разметка внутри md:

    <!--PART:Часть 2|Разбор для проверяющего-->   разделитель между частями
    <!--CAP:Пояснение под схемой-->                подпись к диаграмме
    <!--NUMBERING:off-->                          выключить нумерацию разделов

Зависимости: Python 3.12+, pymupdf, установленный Chrome или Edge.
Ассеты (шрифты, mermaid) скачиваются один раз в tools/assets/.
"""
from __future__ import annotations

import argparse
import base64
import mimetypes
import os
import html
import pathlib
import re
import subprocess
import sys
import urllib.request

import pymupdf

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = pathlib.Path(os.environ.get("A2PDF_ASSETS") or HERE / "assets")
TMP = pathlib.Path(os.environ.get("A2PDF_TMP") or HERE / ".build")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
GOOGLE_FONTS = ("https://fonts.googleapis.com/css2?"
                "family=Inter:wght@400;500;600;700;800"
                "&family=JetBrains+Mono:wght@400;500&display=swap")
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

# --------------------------------------------------------------------------- #
# Ассеты
# --------------------------------------------------------------------------- #


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def ensure_assets(quiet: bool = False) -> None:
    """Скачивает шрифты и mermaid при первом запуске."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    say = (lambda *a: None) if quiet else print

    css = ASSETS / "fonts.css"
    if not css.exists():
        say("Скачиваю шрифты Inter и JetBrains Mono…")
        raw = _get(GOOGLE_FONTS).decode("utf-8")
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
            block = block.replace(
                m.group(0), f"url(data:font/woff2;base64,{data}) format('woff2')")
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


# --------------------------------------------------------------------------- #
# Front matter и разбор markdown
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Рендер блоков в HTML
# --------------------------------------------------------------------------- #

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


def render(blocks: list[tuple], numbered: bool = True,
           drop_h1: bool = True) -> str:
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
            out.append('<div class="dg dg-mermaid"><pre class="mermaid">'
                       f'{html.escape(b[1])}</pre></div>')
        elif kind == "note":
            out.append(f'<div class="note"><p>{inline(b[1])}</p></div>')
        elif kind == "table":
            head = "".join(f"<th>{inline(c)}</th>" for c in b[1])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row)
                           + "</tr>" for row in b[2])
            out.append(f"<table><thead><tr>{head}</tr></thead>"
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


# --------------------------------------------------------------------------- #
# Стили
# --------------------------------------------------------------------------- #

TOKENS = """
:root{
  --navy:#0B2660; --navy-900:#06173B; --navy-50:#F2F5FA; --navy-100:#E3EAF4;
  --blue:#1FA8FC; --blue-700:#1289D5; --blue-50:#F1F8FF;
  --amber:#FF9F1C; --amber-50:#FFF8EC;
  --n0:#FFFFFF; --n50:#F7F8FA; --n100:#EFF1F4; --n200:#E1E4EA;
  --n400:#9CA3AF; --n500:#6B7280; --n700:#374151; --n900:#111722;
  --font:'Inter','Segoe UI',Arial,sans-serif;
  --mono:'JetBrains Mono','Cascadia Mono',Consolas,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font-family:var(--font);color:var(--n700);font-variant-numeric:tabular-nums}
"""

COVER_CSS = TOKENS + """
@page{size:A4;margin:0}
body{width:210mm;height:296.5mm;overflow:hidden}
.cover{position:relative;width:210mm;height:296.5mm;background:var(--navy);
       color:#fff;padding:22mm 20mm 18mm;display:flex;flex-direction:column;
       justify-content:space-between;overflow:hidden}
.cover::before{content:"";position:absolute;inset:0;
  background-image:linear-gradient(rgba(255,255,255,.05) .3mm,transparent .3mm),
                   linear-gradient(90deg,rgba(255,255,255,.05) .3mm,transparent .3mm);
  background-size:14mm 14mm;background-position:20mm 22mm}
.cover::after{content:"";position:absolute;top:-70mm;right:-70mm;width:190mm;
  height:190mm;border-radius:50%;
  background:radial-gradient(circle,rgba(31,168,252,.30) 0%,rgba(31,168,252,0) 65%)}
.cover>*{position:relative}
.edge{position:absolute;left:0;top:0;bottom:0;width:3mm;background:var(--amber);z-index:2}
.top{display:flex;justify-content:space-between;align-items:flex-start;
     padding-bottom:6mm;border-bottom:.25mm solid rgba(255,255,255,.14)}
.wordmark{font-size:20pt;font-weight:800;letter-spacing:-1px;line-height:1}
.wordmark i{font-style:normal;color:var(--blue)}
.top .role{font-family:var(--mono);font-size:7.6pt;letter-spacing:2.2px;
           text-transform:uppercase;color:#7E9AD0;text-align:right;padding-top:3mm}
.mid{position:relative;padding:6mm 0 10mm}
.idx{position:absolute;right:-6mm;bottom:-2mm;font-size:158pt;font-weight:800;
     line-height:.8;letter-spacing:-6px;color:transparent;
     -webkit-text-stroke:.45mm rgba(31,168,252,.38)}
.kick{display:flex;align-items:center;gap:4mm;margin-bottom:7mm}
.kick .bar{width:14mm;height:1mm;background:var(--amber)}
.kick .txt{font-family:var(--mono);font-size:8pt;letter-spacing:2.6px;
           text-transform:uppercase;color:var(--blue)}
h1{font-size:38pt;font-weight:700;letter-spacing:-1.8px;line-height:1.04;max-width:152mm}
.sub{font-size:12.5pt;line-height:1.5;color:#BFD0E8;margin-top:6mm;max-width:118mm}
.chip{display:inline-block;background:var(--amber);color:var(--navy);font-size:7.6pt;
      font-weight:700;letter-spacing:1.6px;text-transform:uppercase;padding:2mm 4mm;
      border-radius:1mm;margin-bottom:6mm}
.bars{display:flex;align-items:flex-end;gap:1.3mm;height:13mm;margin-bottom:9mm}
.bars i{display:block;width:1.8mm;background:rgba(31,168,252,.5);border-radius:.4mm}
.bars i.hi{background:var(--amber)}
.spec{display:grid;border-top:.25mm solid rgba(255,255,255,.22);padding-top:5mm}
.spec div{padding-left:5mm;border-left:.25mm solid rgba(255,255,255,.14)}
.spec div:first-child{padding-left:0;border-left:0}
.spec .k{font-size:7pt;letter-spacing:1.6px;text-transform:uppercase;color:#7E9AD0}
.spec .v{font-family:var(--mono);font-size:9.4pt;color:#fff;margin-top:1.5mm;
         white-space:nowrap}
.foot{display:flex;justify-content:space-between;align-items:center;margin-top:7mm;
      font-size:8pt;color:#7E9AD0;font-family:var(--mono);letter-spacing:.6px}
.foot .site{color:#fff}
"""

BODY_CSS = TOKENS + """
@page{size:A4;margin:24mm 17mm 22mm}
body{font-size:10.2pt;line-height:1.55}
.h2-wrap{display:flex;align-items:baseline;gap:3.5mm;margin:9mm 0 3mm;break-after:avoid}
.h2-wrap:first-child{margin-top:0}
.eyebrow{font-family:var(--mono);font-size:8pt;font-weight:700;color:var(--blue);
         letter-spacing:.5px}
h2{font-size:15.5pt;font-weight:700;color:var(--navy);letter-spacing:-.4px;line-height:1.2}
h3{font-size:10.6pt;font-weight:600;color:var(--n900);margin:5mm 0 2mm;break-after:avoid}
p{margin:0 0 3mm}
strong{color:var(--n900);font-weight:600}
code,pre.code code{font-variant-ligatures:none;font-feature-settings:"liga" 0,"calt" 0}
code{font-family:var(--mono);font-size:8.6pt;background:var(--navy-50);color:var(--navy);
     padding:.3mm 1.2mm;border-radius:.8mm;border:.2mm solid var(--navy-100)}
ul,ol{margin:0 0 4mm;padding:0;list-style:none}
li{position:relative;padding-left:8mm;margin-bottom:1.6mm;break-inside:avoid}
ul>li::before{content:"";position:absolute;left:2.5mm;top:2.1mm;width:1.3mm;height:1.3mm;
              background:var(--blue);border-radius:.3mm}
ol{counter-reset:ol}
ol>li{counter-increment:ol}
ol>li::before{content:counter(ol,decimal-leading-zero);position:absolute;left:0;top:.6mm;
              font-family:var(--mono);font-size:7.6pt;font-weight:700;color:var(--blue-700)}
.rule{height:.25mm;background:var(--n200);margin:8mm 0}
.strip{display:flex;gap:9mm;border-top:.5mm solid var(--navy);
       border-bottom:.25mm solid var(--n200);padding:2.5mm 0;margin:0 0 6mm}
.strip span{font-size:9pt;color:var(--n900)}
.strip i{display:block;font-style:normal;font-size:7pt;letter-spacing:1.4px;
         text-transform:uppercase;color:var(--n400);margin-bottom:.8mm}
pre.code{background:var(--n50);border:.25mm solid var(--n200);
         border-left:.9mm solid var(--blue);border-radius:1.4mm;padding:4mm 5mm;
         margin:0 0 4mm;break-inside:avoid}
pre.code code{font-family:var(--mono);font-size:8.4pt;line-height:1.55;background:none;
              border:0;padding:0;color:var(--n900);white-space:pre-wrap;
              word-break:break-word}
table{width:100%;border-collapse:collapse;margin:0 0 4mm;font-size:9pt;break-inside:avoid}
th{background:var(--navy);color:#fff;text-align:left;font-weight:600;padding:2.6mm 3mm;
   font-size:8.4pt}
td{padding:2.4mm 3mm;border-bottom:.25mm solid var(--n200);vertical-align:top}
tbody tr:nth-child(even) td{background:var(--n50)}
.note{border-left:.9mm solid var(--amber);background:var(--amber-50);padding:3.5mm 5mm;
      margin:0 0 4mm;border-radius:0 1.4mm 1.4mm 0;break-inside:avoid}
.note p{margin:0;font-size:9.4pt}
.dg{border:.25mm solid var(--n200);border-radius:1.6mm;background:var(--n50);padding:5mm;
    margin:0 0 5mm;break-inside:avoid}
.dg-mermaid{text-align:center;padding:4mm}
.dg-mermaid svg{max-width:100%;height:auto}
.fig{margin:0 0 5mm;text-align:center;break-inside:avoid}
.fig img{max-width:100%;max-height:150mm;border-radius:1.4mm}
.fig-cap{margin:-3mm 0 5mm;padding-left:1mm;font-size:8.4pt;color:var(--n500);
         break-before:avoid}
.dg-row{margin-bottom:3mm}
.dg-row:last-of-type{margin-bottom:0}
.dg-lab{font-size:7.4pt;font-weight:600;text-transform:uppercase;letter-spacing:1.2px;
        color:var(--n400);margin-bottom:2mm}
.dg-chain{display:flex;align-items:center;flex-wrap:wrap;gap:2mm}
.dg-node{display:inline-block;padding:2mm 3.2mm;border-radius:1.4mm;font-size:8.6pt;
         font-weight:500;border:.25mm solid var(--n200);background:#fff;color:var(--n900)}
.dg-node.dg-a{background:var(--navy);border-color:var(--navy);color:#fff;font-weight:600}
.dg-node.dg-s{background:var(--blue-50);border-color:#BFE3FF;color:var(--blue-700);
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
        color:var(--blue-700)}
.dg-actor{flex:none;width:26mm;font-weight:600;color:var(--navy)}
.dg-act{color:var(--n700)}
.dg-act code{font-size:8pt}
.part{margin:11mm 0 6mm;padding-top:4mm;border-top:.5mm solid var(--navy);
      break-after:avoid;break-inside:avoid;display:flex;align-items:baseline;gap:4mm}
.part .lbl{font-family:var(--mono);font-size:7.6pt;font-weight:700;letter-spacing:1.4px;
           text-transform:uppercase;color:var(--amber)}
.part .ttl{font-size:13pt;font-weight:700;color:var(--navy);letter-spacing:-.3px}
"""

MERMAID_INIT = """
mermaid.initialize({
  startOnLoad:false, theme:'base', securityLevel:'loose',
  flowchart:{curve:'basis',htmlLabels:true,useMaxWidth:true},
  sequence:{useMaxWidth:true,actorMargin:40,width:150},
  themeVariables:{
    fontFamily:"Inter, 'Segoe UI', sans-serif", fontSize:'13px',
    primaryColor:'#F1F8FF', primaryBorderColor:'#1FA8FC', primaryTextColor:'#0B2660',
    secondaryColor:'#F7F8FA', tertiaryColor:'#FFF8EC',
    lineColor:'#6B7280', textColor:'#374151',
    mainBkg:'#F1F8FF', nodeBorder:'#1FA8FC', clusterBkg:'#F7F8FA',
    clusterBorder:'#E1E4EA', edgeLabelBackground:'#FFFFFF',
    actorBkg:'#0B2660', actorBorder:'#0B2660', actorTextColor:'#FFFFFF',
    actorLineColor:'#9CA3AF', signalColor:'#374151', signalTextColor:'#374151',
    labelBoxBkgColor:'#FFF8EC', labelBoxBorderColor:'#FF9F1C',
    labelTextColor:'#0B2660', loopTextColor:'#374151',
    noteBkgColor:'#FFF8EC', noteBorderColor:'#FF9F1C', noteTextColor:'#0B2660',
    altBackground:'#F7F8FA'
  }
});
await mermaid.run();

"""

COVER_TPL = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{title}</title>
<style>{fonts}</style><style>{css}</style></head><body>
<div class="cover">
  <div class="edge"></div>
  <div class="top">
    <div class="wordmark">A2<i>DATA</i></div>
    <div class="role">{role}</div>
  </div>
  <div class="mid">
    {index}{chip}
    {kicker}
    <h1>{title_text}</h1>
    {subtitle}
  </div>
  <div class="bottom">
    <div class="bars">{bars}</div>
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

BAR_HEIGHTS = [22, 38, 30, 52, 44, 66, 48, 80, 58, 92, 70, 100, 62, 46, 74,
               54, 34, 60, 42, 28, 50, 36, 24, 44, 30, 20, 40, 26]


def bars_html() -> str:
    return "".join(f'<i class="{"hi" if i == 11 else ""}" style="height:{h}%"></i>'
                   for i, h in enumerate(BAR_HEIGHTS))


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #

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
    url = "file:///" + str(html_path).replace("\\", "/")
    subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer", "--print-to-pdf-no-header",
         f"--print-to-pdf={pdf_path}", f"--virtual-time-budget={wait_ms}",
         "--allow-file-access-from-files", url],
        check=True, capture_output=True)


def stamp(doc: pymupdf.Document, header_right: str, footer_left: str,
          skip_first: bool) -> None:
    reg = pymupdf.Font(fontfile=str(ASSETS / "Inter-Regular.ttf"))
    bold = pymupdf.Font(fontfile=str(ASSETS / "Inter-ExtraBold.ttf"))
    total = doc.page_count
    for idx, page in enumerate(doc, start=1):
        if skip_first and idx == 1:
            continue
        w, h = page.rect.width, page.rect.height
        left, right = 17 * MM, w - 17 * MM
        top_y, bot_y = 13 * MM, h - 11.5 * MM

        navy_tw, blue_tw, gray_tw = (pymupdf.TextWriter(page.rect) for _ in range(3))
        navy_tw.append((left, top_y), "A2", font=bold, fontsize=8)
        blue_tw.append((left + bold.text_length("A2", 8), top_y), "DATA",
                       font=bold, fontsize=8)
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
        navy_tw.write_text(page, color=NAVY)
        blue_tw.write_text(page, color=BLUE)
        gray_tw.write_text(page, color=GRAY)


def save(doc: pymupdf.Document, pdf_path: pathlib.Path) -> pathlib.Path:
    try:
        doc.save(pdf_path, garbage=4, deflate=True)
    except Exception:  # файл открыт в просмотрщике
        pdf_path = pdf_path.with_suffix(".new.pdf")
        doc.save(pdf_path, garbage=4, deflate=True)
        print(f"  файл занят другим приложением, сохранил как {pdf_path.name}")
    return pdf_path


# --------------------------------------------------------------------------- #
# Основная сборка
# --------------------------------------------------------------------------- #


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
    fonts_css = (ASSETS / "fonts.css").read_text(encoding="utf-8")
    content = render(blocks, numbered=numbered)

    mermaid_tag = ""
    if has_mermaid:
        lib = (ASSETS / "mermaid.min.js").read_text(encoding="utf-8")
        mermaid_tag = (f"<script>{lib}</script>"
                       f"<script type=\"module\">{MERMAID_INIT}</script>")

    stem = re.sub(r"[^\w.-]+", "_", name)[:50] + f"-{os.getpid()}-{id(blocks) & 0xffff:x}"
    body_html = TMP / f"{stem}-body.html"
    body_html.write_text(BODY_TPL.format(
        title=html.escape(str(front["title"])), fonts=fonts_css, css=BODY_CSS,
        content=content, mermaid=mermaid_tag), encoding="utf-8")
    body_pdf = TMP / f"{stem}-body.pdf"
    print_pdf(body_html, body_pdf, chrome, 15000 if has_mermaid else 5000)

    with_cover = str(front.get("cover", "true")).lower() not in ("false", "0", "no")
    doc = pymupdf.open()
    if with_cover:
        meta_items = list((front.get("meta") or {}).items())
        spec = "".join(f'<div><div class="k">{html.escape(str(k))}</div>'
                       f'<div class="v">{html.escape(str(v))}</div></div>'
                       for k, v in meta_items)
        cover_html = TMP / f"{stem}-cover.html"
        cover_html.write_text(COVER_TPL.format(
            title=html.escape(str(front["title"])), fonts=fonts_css, css=COVER_CSS,
            role=html.escape(str(front.get("role", COMPANY))),
            index=(f'<div class="idx">{html.escape(str(front["index"]))}</div>'
                   if front.get("index") else ""),
            chip=(f'<div class="chip">{html.escape(str(front["confidential"]))}</div>'
                  if front.get("confidential") else ""),
            kicker=(f'<div class="kick"><span class="bar"></span>'
                    f'<span class="txt">{html.escape(str(front["kicker"]))}</span></div>'
                    if front.get("kicker") else '<div class="kick">'
                    '<span class="bar"></span></div>'),
            title_text=html.escape(str(front["title"])),
            subtitle=(f'<div class="sub">{html.escape(str(front["subtitle"]))}</div>'
                      if front.get("subtitle") else ""),
            bars=bars_html(), cols=max(1, len(meta_items)) if meta_items else 1,
            spec=spec,
            foot_left=html.escape(str(front.get("place", "Almaty, Kazakhstan"))),
            site=SITE), encoding="utf-8")
        cover_pdf = TMP / f"{stem}-cover.pdf"
        print_pdf(cover_html, cover_pdf, chrome, 3000)
        doc.insert_pdf(pymupdf.open(cover_pdf))
    doc.insert_pdf(pymupdf.open(body_pdf))

    stamp(doc, str(front.get("header", front["title"])),
          str(front.get("footer", "")), skip_first=with_cover)
    doc.set_metadata({"title": str(front["title"]), "author": COMPANY,
                      "subject": str(front.get("subtitle", "")), "creator": COMPANY})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = save(doc, out_path)
    doc.close()
    for tmp in TMP.glob(f"{stem}-*"):  # промежуточные html/pdf не нужны
        tmp.unlink(missing_ok=True)
    return result


def build_markdown(text: str, out_path: pathlib.Path, overrides: dict | None = None,
                   append_texts: list[str] | None = None,
                   chrome: str | None = None, name: str = "document") -> pathlib.Path:
    """Собирает PDF из markdown-строки (front matter учитывается)."""
    front, body = split_front_matter(text)
    front.update({k: v for k, v in (overrides or {}).items() if v is not None})
    keep_mm = str(front.get("mermaid", "true")).lower() not in (
        "false", "0", "off", "no")
    blocks = parse(body, keep_mermaid=keep_mm)
    for extra in append_texts or []:
        _, extra_body = split_front_matter(extra)
        blocks += parse(extra_body, keep_mermaid=keep_mm)
    return render_pdf(blocks, front, out_path, chrome=chrome, name=name)


def build(md_path: pathlib.Path, out_path: pathlib.Path | None = None,
          overrides: dict | None = None,
          append: list[pathlib.Path] | None = None,
          chrome: str | None = None, quiet: bool = False) -> pathlib.Path:
    """Собирает PDF из markdown-файла и возвращает путь к результату."""
    ensure_assets(quiet=quiet)
    out_path = out_path or md_path.with_suffix(".pdf")
    result = build_markdown(
        md_path.read_text(encoding="utf-8"), out_path, overrides=overrides,
        append_texts=[p.read_text(encoding="utf-8") for p in (append or [])],
        chrome=chrome, name=md_path.stem)
    if not quiet:
        with pymupdf.open(result) as d:
            print(f"{result}  —  {d.page_count} стр., "
                  f"{result.stat().st_size // 1024} KB")
    return result


def build_any(path: pathlib.Path, out_path: pathlib.Path | None = None,
              overrides: dict | None = None,
              append: list[pathlib.Path] | None = None,
              chrome: str | None = None, quiet: bool = False) -> pathlib.Path:
    """Собирает PDF из .md или .docx."""
    out_path = out_path or path.with_suffix(".pdf")
    if path.suffix.lower() != ".docx":
        return build(path, out_path, overrides=overrides, append=append,
                     chrome=chrome, quiet=quiet)

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
    result = render_pdf(blocks, front, out_path, chrome=chrome, name=path.stem)
    if not quiet:
        with pymupdf.open(result) as d:
            print(f"{result}  —  {d.page_count} стр., "
                  f"{result.stat().st_size // 1024} KB")
    return result


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
    ap.add_argument("--no-mermaid", action="store_true",
                    help="не рисовать диаграммы mermaid")
    args = ap.parse_args(argv)

    overrides: dict = {}
    for name in ("title", "subtitle", "kicker", "index", "footer", "header"):
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
                  chrome=chrome)


if __name__ == "__main__":
    main()
