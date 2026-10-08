"""Оформление диаграмм mermaid: пресеты, палитры и тема.

Пресет задаёт не только подложку, но и цвета элементов: заливку узлов,
обводку, линии и подписи. Свои цвета в classDef перекрывают тему mermaid,
поэтому их подменяем палитрой пресета.
"""
from __future__ import annotations

import csv
import io
import json
import pathlib
import re

from . import brands

FIX_JS = pathlib.Path(__file__).resolve().parent / "static" / "mermaid-fix.js"


def tint(color: str, alpha: float) -> str:
    """Цвет с прозрачностью в виде #RRGGBBAA — запятых внутри значения нет,
    поэтому его можно писать и в classDef."""
    return color + format(round(max(0.0, min(1.0, alpha)) * 255), "02X")


def mix(color: str, other: str, share: float) -> str:
    """Сплошной цвет между двумя: share — доля второго. Полупрозрачный цвет
    в графиках не годится: сектора и столбцы ложатся друг на друга."""
    a = [int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(other.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(format(round(x + (y - x) * share), "02X")
                         for x, y in zip(a, b))


DIAGRAM_SCHEMES = {
    "outline": {"title": "Контур", "note": "белый фон, тонкая обводка",
                "dark": False, "clear": False},
    "soft": {"title": "Мягкая", "note": "пастельные плашки",
             "dark": False, "clear": False},
    "solid": {"title": "Плотная", "note": "заливка в цвет бренда",
              "dark": False, "clear": False},
    "dark": {"title": "Тёмная", "note": "для слайдов",
             "dark": True, "clear": False},
    "clear": {"title": "Прозрачная", "note": "PNG без фона",
              "dark": False, "clear": True},
}
DEFAULT_SCHEME = "outline"


def scheme_style(key: str | None, brand: brands.Brand) -> dict:
    """Полное оформление пресета в цветах бренда.

    palette   — заливка, обводка и текст для групп узлов из classDef
    theme     — переменные темы mermaid для остальных узлов и линий
    backdrop  — подложка под диаграммой
    svg       — правка формы и теней уже отрисованного SVG
    """
    c, n = brand.colors, brand.neutrals
    white, key = n["n0"], str(key or DEFAULT_SCHEME)
    if key not in DIAGRAM_SCHEMES:
        key = DEFAULT_SCHEME

    if key == "soft":
        palette = [(c["accent_50"], c["accent_50"], c["brand"]),
                   (c["brand_100"], c["brand_100"], c["brand"]),
                   (c["mark_50"], c["mark_50"], c["brand"]),
                   (c["accent_100"], c["accent_100"], c["brand"]),
                   (c["brand_50"], c["brand_50"], c["brand"])]
        theme = {"mainBkg": c["accent_50"], "nodeBorder": c["accent_50"],
                 "primaryColor": c["accent_50"],
                 "primaryBorderColor": c["accent_50"],
                 "primaryTextColor": c["brand"], "textColor": c["brand"],
                 "lineColor": c["accent"], "edgeLabelBackground": n["n50"],
                 "clusterBkg": white, "clusterBorder": c["brand_100"]}
        backdrop = ("background:var(--n50);border-radius:4mm;padding:11mm")
        svg = {"radius": "12px", "stroke": "0", "shadow":
               f"drop-shadow(0 2px 5px {tint(c['brand'], .16)})",
               "edge": "1.6px"}
    elif key == "solid":
        palette = [(c["brand"], c["brand"], white),
                   (c["accent"], c["accent"], white),
                   (c["mark"], c["mark"], white),
                   (c["accent_dark"], c["accent_dark"], white),
                   (c["brand_dark"], c["brand_dark"], white)]
        theme = {"mainBkg": c["brand"], "nodeBorder": c["brand"],
                 "primaryColor": c["brand"], "primaryBorderColor": c["brand"],
                 "primaryTextColor": white, "textColor": n["n700"],
                 "lineColor": n["n500"], "edgeLabelBackground": white,
                 "clusterBkg": n["n50"], "clusterBorder": n["n200"]}
        backdrop = "background:#FFFFFF"
        svg = {"radius": "9px", "stroke": "0", "shadow":
               f"drop-shadow(0 2px 4px {tint(c['brand'], .22)})",
               "edge": "1.5px"}
    elif key == "dark":
        palette = [(tint(c["accent"], .26), c["accent"], white),
                   (tint(white, .12), n["n200"], white),
                   (tint(c["mark"], .26), c["mark"], white),
                   (tint(c["accent"], .40), c["accent_50"], white),
                   (tint(white, .20), white, white)]
        theme = {"mainBkg": tint(c["accent"], .26), "nodeBorder": c["accent"],
                 "primaryColor": tint(c["accent"], .26),
                 "primaryBorderColor": c["accent"],
                 "primaryTextColor": white, "textColor": white,
                 "lineColor": tint(white, .62),
                 "edgeLabelBackground": c["brand_dark"],
                 "clusterBkg": tint(white, .07),
                 "clusterBorder": tint(white, .28)}
        backdrop = "background:var(--brand-dark);border-radius:4mm;padding:11mm"
        svg = {"radius": "9px", "stroke": "1.2px", "shadow": "none",
               "edge": "1.4px"}
    else:  # outline и clear рисуются одинаково, различается только подложка
        palette = [(white, c["accent"], c["brand"]),
                   (white, c["brand"], c["brand"]),
                   (white, c["mark"], c["brand"]),
                   (white, c["accent_dark"], c["brand"]),
                   (white, n["n400"], c["brand"])]
        theme = {"mainBkg": white, "nodeBorder": c["brand"],
                 "primaryColor": white, "primaryBorderColor": c["brand"],
                 "primaryTextColor": c["brand"], "textColor": n["n700"],
                 "lineColor": n["n400"],
                 "edgeLabelBackground": white if key == "outline" else "#FFFFFF00",
                 "clusterBkg": white, "clusterBorder": n["n200"]}
        backdrop = ("background:none" if key == "clear"
                    else "background:#FFFFFF")
        svg = {"radius": "7px", "stroke": "1.5px", "shadow": "none",
               "edge": "1.3px"}

    # серии графиков (pie, xychart, gantt, mindmap…): насыщенные цвета бренда,
    # заметные на подложке пресета, — без бледных тонов, теряющихся на белом
    if key == "dark":
        series = [c["accent"], c["mark"], mix(c["accent"], white, .55), n["n200"],
                  mix(c["mark"], white, .5), c["accent_dark"], c["mark_dark"],
                  n["n400"]]
    else:
        series = [c["brand"], c["accent"], c["mark"], c["accent_dark"],
                  c["mark_dark"], mix(c["brand"], white, .4), n["n500"],
                  mix(c["accent"], c["brand"], .5)]

    fill, stroke, text = palette[0]
    return {"key": key, "palette": palette, "theme": theme, "series": series,
            "backdrop": backdrop, "svg": svg,
            # цвета для миниатюры пресета в форме
            "preview": {"bg": "" if key == "clear" else
                        c["brand_dark"] if key == "dark" else
                        n["n50"] if key == "soft" else white,
                        "fill": fill, "stroke": stroke, "text": text},
            "clear": DIAGRAM_SCHEMES[key]["clear"],
            "dark": DIAGRAM_SCHEMES[key]["dark"]}


def scheme_css(style: dict) -> str:
    """Форма узлов, тени и толщина линий — темой mermaid это не задаётся."""
    svg = style["svg"]
    theme = style["theme"]
    # цвет подписи ребра тема mermaid не отдаёт, поэтому задаём его сами
    rules = (".dg-mermaid .edgeLabel,.dg-mermaid .edgeLabel p,"
             ".dg-mermaid .edgeLabel span,.dg-mermaid .edgeLabel div{"
             f'color:{theme["textColor"]};'
             f'background:{theme["edgeLabelBackground"]}}}'
             ".dg-mermaid .node rect,.dg-mermaid .node .label-container{"
             f'rx:{svg["radius"]};ry:{svg["radius"]}}}'
             f'.dg-mermaid .node{{filter:{svg["shadow"]}}}'
             ".dg-mermaid .edgePath path,.dg-mermaid .flowchart-link{"
             f'stroke-width:{svg["edge"]}}}')
    if svg["stroke"] == "0":
        rules += (".dg-mermaid .node rect,.dg-mermaid .node polygon,"
                  ".dg-mermaid .node path,.dg-mermaid .node circle,"
                  ".dg-mermaid .node ellipse{stroke-width:0}")
    else:
        rules += (".dg-mermaid .node rect,.dg-mermaid .node polygon,"
                  ".dg-mermaid .node path,.dg-mermaid .node circle,"
                  ".dg-mermaid .node ellipse{"
                  f'stroke-width:{svg["stroke"]}}}')
    return rules


DIAGRAM_STYLE = re.compile(r"^\s*(classDef|style)\s+(\S+)", re.MULTILINE)
DIAGRAM_COLOR = re.compile(r"\b(fill|stroke|color)\s*:\s*#[0-9A-Fa-f]{3,8}")


INIT = re.compile(r"%%\{\s*init\s*:\s*(\{.*?\})\s*\}%%", re.S)


def strip_theme(src: str) -> str:
    """Тема схемы — только из брендбука: из директивы %%{init}%% (её пишет
    визуальный редактор) убираем theme и themeVariables, остальное оставляем."""
    def clean(m: re.Match) -> str:
        try:
            config = json.loads(m.group(1))
        except ValueError:
            return ""
        for key in ("theme", "themeVariables", "themeCSS"):
            config.pop(key, None)
        return f"%%{{init: {json.dumps(config, ensure_ascii=False)}}}%%" if config else ""
    return INIT.sub(clean, src)


LABELS_MARK = "%% a2pdf-labels "


def ascii_labels(src: str) -> str:
    """Sankey понимает в названиях только ASCII. Кириллицу меняем на метки
    lbl0q, lbl1q…, а словарь кладём комментарием: после отрисовки
    mermaid-fix.js вернёт настоящие подписи."""
    lines = src.splitlines()
    head = next((ln.strip() for ln in lines if ln.strip()
                 and not ln.strip().startswith("%%")), "")
    if not re.match(r"sankey(-beta)?\b", head) or LABELS_MARK in src:
        return src
    names: dict[str, str] = {}

    def token(field: str) -> str:
        if field.isascii():
            return field
        return names.setdefault(field, f"lbl{len(names)}q")

    out = []
    for line in lines:
        text = line.strip()
        if not text or text.startswith("%%") or text == head or "," not in text:
            out.append(line)
            continue
        fields = next(csv.reader([text]))
        buf = io.StringIO()
        csv.writer(buf, lineterminator="").writerow(
            [token(f) for f in fields[:-1]] + fields[-1:])
        out.append(buf.getvalue())
    if not names:
        return src
    out.append(LABELS_MARK + json.dumps({v: k for k, v in names.items()},
                                        ensure_ascii=True))
    return "\n".join(out)


def theme_diagram(src: str, brand: brands.Brand,
                  style: dict | None = None) -> str:
    """Свои цвета в classDef и style перекрывают тему mermaid, поэтому
    подменяем их палитрой пресета: группы узлов остаются различимыми."""
    src = ascii_labels(strip_theme(src))
    palette = (style or scheme_style(None, brand))["palette"]
    order: dict[str, int] = {}
    for _, name in DIAGRAM_STYLE.findall(src):
        order.setdefault(name, len(order))
    if not order:
        return src

    def repaint(line: str) -> str:
        head = DIAGRAM_STYLE.match(line)
        if not head:
            return line
        fill, stroke, text = palette[order[head.group(2)] % len(palette)]
        colors = {"fill": fill, "stroke": stroke, "color": text}
        return DIAGRAM_COLOR.sub(
            lambda m: f"{m.group(1)}:{colors[m.group(1)]}", line)

    return "\n".join(repaint(line) for line in src.splitlines())


def chart_theme(brand: brands.Brand, style: dict) -> dict:
    """Цвета графиков: без них mermaid выводит серии из secondary/tertiary
    и рисует бледно-жёлтые сектора на белом."""
    c, n, t = brand.colors, brand.neutrals, style["theme"]
    series, dark = style["series"], style["dark"]
    text, back = t["textColor"], c["brand_dark"] if dark else n["n0"]
    on_series = n["n0"]
    vars_ = {f"pie{i + 1}": series[i % len(series)] for i in range(12)}
    vars_ |= {f"cScale{i}": series[i % len(series)] for i in range(12)}
    vars_ |= {f"cScaleLabel{i}": on_series for i in range(12)}
    vars_ |= {f"git{i}": series[i % len(series)] for i in range(8)}
    vars_ |= {f"gitBranchLabel{i}": on_series for i in range(8)}
    vars_ |= {f"fillType{i}": series[i % len(series)] for i in range(8)}
    vars_ |= {
        "pieSectionTextColor": on_series, "pieTitleTextColor": text,
        "pieLegendTextColor": text, "pieStrokeColor": back,
        "pieOuterStrokeColor": back, "pieStrokeWidth": "2px",
        "pieOuterStrokeWidth": "0px", "pieOpacity": "1",
        "xyChart": {"plotColorPalette": ",".join(series),
                    "backgroundColor": "transparent", "titleColor": text,
                    "xAxisLabelColor": text, "xAxisTitleColor": text,
                    "xAxisTickColor": t["lineColor"],
                    "xAxisLineColor": t["lineColor"],
                    "yAxisLabelColor": text, "yAxisTitleColor": text,
                    "yAxisTickColor": t["lineColor"],
                    "yAxisLineColor": t["lineColor"]},
        # gantt: задачи акцентом, критичные меткой, секции — лёгкой подложкой
        "taskBkgColor": series[1], "taskBorderColor": series[1],
        "taskTextColor": on_series, "taskTextLightColor": on_series,
        "taskTextDarkColor": text, "taskTextOutsideColor": text,
        "taskTextClickableColor": text,
        "activeTaskBkgColor": mix(series[1], back, .45),
        "activeTaskBorderColor": series[1],
        "doneTaskBkgColor": n["n400"], "doneTaskBorderColor": n["n400"],
        "critBkgColor": c["mark"], "critBorderColor": c["mark_dark"],
        "sectionBkgColor": tint(n["n0"], .06) if dark else c["brand_50"],
        "sectionBkgColor2": tint(n["n0"], .03) if dark else n["n0"],
        "altSectionBkgColor": tint(n["n0"], .03) if dark else n["n0"],
        "gridColor": tint(n["n0"], .18) if dark else n["n200"],
        "todayLineColor": c["mark"],
        # quadrant: четверти тонкими подложками, точки — меткой
        "quadrant1Fill": mix(c["accent"], back, .86),
        "quadrant2Fill": mix(c["brand"], back, .9),
        "quadrant3Fill": mix(n["n400"], back, .85),
        "quadrant4Fill": mix(c["mark"], back, .86),
        "quadrant1TextFill": text, "quadrant2TextFill": text,
        "quadrant3TextFill": text, "quadrant4TextFill": text,
        "quadrantPointFill": c["mark"], "quadrantPointTextFill": text,
        "quadrantXAxisTextFill": text, "quadrantYAxisTextFill": text,
        "quadrantTitleFill": text,
        "quadrantInternalBorderStrokeFill": t["lineColor"],
        "quadrantExternalBorderStrokeFill": t["lineColor"],
        # venn: множества полупрозрачные, поэтому цвета насыщенные
        **{f"venn{i + 1}": series[i % len(series)] for i in range(8)},
        "vennSetTextColor": text, "vennTitleTextColor": text,
        "cynefin": {"complexBg": mix(c["accent"], back, .82),
                    "complicatedBg": mix(c["brand"], back, .86),
                    "chaoticBg": mix(c["mark"], back, .78),
                    "clearBg": mix(n["n400"], back, .82),
                    "confusionBg": mix(c["brand"], back, .7),
                    "cliffColor": c["mark_dark"],
                    "boundaryColor": t["lineColor"], "arrowColor": t["lineColor"],
                    "textColor": text, "labelColor": text},
        "wardleyEvolutionColor": c["mark"],
        # фон и режим: по ним mermaid красит карточки kanban, поле wardley,
        # заголовки gantt и прочее, что не берёт цвета из узлов
        "background": back, "darkMode": dark,
        "titleColor": text, "tertiaryTextColor": text,
        "packet": {"blockFillColor": style["palette"][0][0],
                   "blockStrokeColor": style["palette"][0][1],
                   "labelColor": style["palette"][0][2], "titleColor": text,
                   "startByteColor": text, "endByteColor": text},
        "treeView": {"labelColor": text, "lineColor": t["lineColor"],
                     "iconColor": c["accent"], "descriptionColor": n["n400"],
                     "highlightBg": tint(c["accent"], .15),
                     "highlightStroke": c["accent"]},
        "radar": {"graticuleColor": t["lineColor"], "axisColor": t["lineColor"]},
        # ER и классы: строки атрибутов чередуются
        "attributeBackgroundColorOdd": tint(n["n0"], .06) if dark else n["n0"],
        "attributeBackgroundColorEven": tint(n["n0"], .12) if dark else n["n50"],
    }
    return vars_


def mermaid_theme(brand: brands.Brand, fonts: brands.Fonts | None = None,
                  style: dict | None = None) -> dict:
    """Переменные темы mermaid: общие для печати и для конструктора схем."""
    fonts = fonts or brand.fonts
    style = style or scheme_style(None, brand)
    theme = {"fontFamily": f"{fonts.body}, 'Segoe UI', sans-serif",
             "fontSize": "13px",
             "secondaryColor": brand.colors["brand_50"],
             # из tertiary mermaid выводит цвета многих схем: бледно-жёлтый
             # mark_50 на белом не виден, поэтому берём подложку бренда
             "tertiaryColor": brand.colors["brand_50"],
             "actorBkg": style["theme"]["mainBkg"],
             "actorBorder": style["theme"]["nodeBorder"],
             "actorTextColor": style["theme"]["primaryTextColor"],
             "actorLineColor": style["theme"]["lineColor"],
             "signalColor": style["theme"]["textColor"],
             "signalTextColor": style["theme"]["textColor"],
             "labelBoxBkgColor": style["theme"]["mainBkg"],
             "labelBoxBorderColor": style["theme"]["nodeBorder"],
             # подпись ребра лежит на подложке диаграммы, а не на узле,
             # поэтому цвет берём от обычного текста
             "labelTextColor": style["theme"]["textColor"],
             "loopTextColor": style["theme"]["textColor"],
             "noteBkgColor": brand.colors["mark_50"],
             "noteBorderColor": brand.colors["mark"],
             "noteTextColor": brand.colors["brand"],
             "altBackground": brand.neutrals["n50"]}
    theme |= style["theme"]
    theme |= chart_theme(brand, style)
    return theme


def mermaid_config(brand: brands.Brand, fonts: brands.Fonts | None = None,
                   style: dict | None = None) -> dict:
    """Всё для mermaid.initialize: тема и настройки отдельных типов схем.
    Одна точка для печати документа и для конструктора в браузере."""
    style = style or scheme_style(None, brand)
    t = style["theme"]
    term, nonterm, special = style["palette"][0], style["palette"][1], style["palette"][2]
    return {
        # strict: html в подписях чистится, ссылки и обработчики не работают —
        # схему пишет пользователь, а печатает её браузер на сервере
        "startOnLoad": False, "theme": "base", "securityLevel": "strict",
        "flowchart": {"curve": "basis", "htmlLabels": True, "useMaxWidth": True},
        "sequence": {"useMaxWidth": True, "actorMargin": 40, "width": 150},
        # railroad берёт цвета не из темы, а из своего раздела настроек
        "railroad": {"terminalFill": term[0], "terminalStroke": term[1],
                     "terminalTextColor": term[2],
                     "nonTerminalFill": nonterm[0], "nonTerminalStroke": nonterm[1],
                     "nonTerminalTextColor": nonterm[2],
                     "specialFill": special[0], "specialStroke": special[1],
                     "lineColor": t["lineColor"], "markerFill": t["nodeBorder"],
                     "commentFill": t["clusterBkg"],
                     "commentStroke": t["clusterBorder"],
                     "commentTextColor": t["textColor"],
                     "ruleNameColor": t["textColor"]},
        "themeVariables": mermaid_theme(brand, fonts, style)}


def mermaid_init(brand: brands.Brand, fonts: brands.Fonts | None = None,
                 style: dict | None = None) -> str:
    """Тема mermaid в цветах пресета и выбранных шрифтах."""
    fonts = fonts or brand.fonts
    style = style or scheme_style(None, brand)
    config = mermaid_config(brand, fonts, style)
    return FIX_JS.read_text(encoding="utf-8") + """
mermaid.initialize(%(config)s);
// Ширину узлов mermaid считает по метрикам шрифта. Пока текста этим шрифтом
// на странице нет, браузер его не запрашивает, поэтому просим начертания сами:
// иначе подписи меряются запасным шрифтом и не влезают в рамку.
await Promise.all(['400 13px "%(body)s"', '600 13px "%(body)s"']
  .map(f => document.fonts.load(f).catch(() => {})));
await document.fonts.ready;

// Разбитая диаграмма не должна ронять сборку и рисовать чужую картинку
// с ошибкой: показываем исходник кодом, автор увидит, что чинить.
// селектор указываем явно: с объектом опций mermaid не подставляет
// свой умолчательный '.mermaid' и молча ничего не рисует
await mermaid.run({querySelector: '.mermaid', suppressErrors: true});
for (const pre of document.querySelectorAll('pre.mermaid')) {
  const svg = pre.querySelector('svg');
  if (svg) a2pdfFix(svg, pre.getAttribute('data-source'), %(series)s);
}
for (const pre of document.querySelectorAll('pre.mermaid')) {
  const svg = pre.querySelector('svg');
  // на разбитой схеме mermaid рисует собственную картинку с ошибкой —
  // она в документе не нужна, узнаём её по служебной разметке
  const failed = !svg || svg.querySelector('.error-icon, .error-text')
    || svg.getAttribute('aria-roledescription') === 'error';
  if (!failed) continue;
  const code = document.createElement('pre');
  code.className = 'code broken-diagram';
  code.textContent = pre.getAttribute('data-source') || pre.textContent;
  pre.replaceWith(code);
}

// Метрики всё равно расходятся на доли пикселя, и подпись обрезается
// по краю контейнера: измеряем её на месте и расширяем контейнер симметрично.
for (const box of document.querySelectorAll('.dg-mermaid foreignObject')) {
  const label = box.firstElementChild;
  if (!label) continue;
  label.style.overflow = 'visible';
  // многострочная подпись переносится по текущей ширине, поэтому её настоящую
  // ширину видно только при max-content
  const width = label.style.width;
  label.style.width = 'max-content';
  const loose = label.getBoundingClientRect().width;
  label.style.width = width;
  const need = Math.ceil(Math.max(loose, label.scrollWidth)) + 8;
  const have = box.width.baseVal.value;
  if (need > have) {
    box.setAttribute('width', need);
    box.setAttribute('x', box.x.baseVal.value - (need - have) / 2);
    // подпись сохраняет прежнюю ширину и без этого прижимается к левому краю
    label.style.width = need + 'px';
    label.style.textAlign = 'center';
  }
}

// Диаграмма должна влезать в страницу целиком: снимаем размеры, которые
// mermaid проставил инлайном, и ограничиваем высоту доступной областью.
// вложенные svg — иконки architecture: их размеры не трогаем
for (const svg of document.querySelectorAll('.dg-mermaid svg')) {
  if (svg.parentElement.closest('svg')) continue;
  svg.removeAttribute('width');
  svg.removeAttribute('height');
  svg.style.maxWidth = '100%%';
  svg.style.maxHeight = '198mm';
  svg.style.width = 'auto';
  svg.style.height = 'auto';
}
""" % {"body": fonts.body, "config": json.dumps(config, ensure_ascii=False),
       "series": json.dumps(style["series"])}


# Заготовки конструктора схем: все типы, которые умеет вшитый mermaid.
# group — раздел в конструкторе; snippets — вставки одной кнопкой.
# Блок-схему конструктор собирает сам, остальные типы правятся кодом.
def _t(group: str, title: str, source: str, *snippets: tuple[str, str]) -> dict:
    return {"group": group, "title": title, "source": source.strip("\n"),
            "snippets": list(snippets)}


TEMPLATES = {
    # ---------- процессы ----------
    "flowchart": _t("Процессы", "Блок-схема", """
flowchart LR
    A["Источник"] --> B("ETL")
    B --> C[("Витрина")]
""", ("Узел", '    X["Узел"]'), ("Связь", "    A --> B"),
        ("Подпись", '    A -->|"подпись"| B'),
        ("Решение", '    D{"Условие?"}'),
        ("Группа", '    subgraph G["Группа"]\n        X\n    end')),
    "sequence": _t("Процессы", "Последовательность", """
sequenceDiagram
    autonumber
    actor U as Клиент
    participant API
    participant DB as База данных
    U->>API: Запрос отчёта
    activate API
    API->>DB: Выборка
    DB-->>API: Строки
    API-->>U: PDF
    deactivate API
    Note over API,DB: кэш на 5 минут
""", ("Участник", "    participant X as Участник"),
        ("Запрос", "    A->>B: Запрос"), ("Ответ", "    B-->>A: Ответ"),
        ("Заметка", "    Note over A,B: заметка"),
        ("Цикл", "    loop Каждую минуту\n        A->>B: Проверка\n    end"),
        ("Условие", "    alt Успех\n        B-->>A: 200\n    else Ошибка\n"
                    "        B-->>A: 500\n    end")),
    "state": _t("Процессы", "Состояния", """
stateDiagram-v2
    [*] --> Черновик
    Черновик --> Проверка : отправить
    Проверка --> Черновик : вернуть
    Проверка --> Опубликован : одобрить
    Опубликован --> [*]
""", ("Переход", "    A --> B : событие"), ("Старт", "    [*] --> A"),
        ("Финиш", "    A --> [*]"),
        ("Составное", "    state Группа {\n        [*] --> X\n    }")),
    "swimlane": _t("Процессы", "Дорожки (swimlane)", """
swimlane-beta LR
  subgraph Клиент
    Order[Оформить заказ]
    Pay[Оплатить]
  end
  subgraph Склад
    Pick[Собрать]
    Ship[Отгрузить]
  end
  subgraph Бухгалтерия
    Invoice[Выставить счёт]
  end
  Order --> Pay
  Pay --> Pick
  Pick --> Ship
  Pay --> Invoice
""", ("Дорожка", "  subgraph Роль\n    X[Шаг]\n  end"), ("Связь", "  A --> B")),
    "journey": _t("Процессы", "Путь клиента", """
journey
    title Путь клиента
    section Знакомство
      Нашёл сайт: 4: Клиент
      Изучил кейсы: 3: Клиент
    section Сделка
      Созвон: 5: Клиент, Менеджер
      Подписал договор: 4: Клиент, Юрист
""", ("Секция", "    section Этап"), ("Шаг", "      Шаг: 3: Клиент")),
    "eventmodeling": _t("Процессы", "Event modeling", """
eventmodeling

tf 01 ui CartUI
tf 02 cmd AddItem [[AddItem01]]
tf 03 evt ItemAdded [[ItemAdded]]

data AddItem01 {
  description: 'Подписка'
  price: 20.4
}

data ItemAdded {
  description: string
  price: number
}
""", ("Экран", "tf 04 ui Screen"), ("Команда", "tf 05 cmd Command"),
        ("Событие", "tf 06 evt Event")),

    # ---------- структура и архитектура ----------
    "architecture": _t("Архитектура", "Архитектура", """
architecture-beta
    group cloud(cloud)[Облако]

    service api(server)[API] in cloud
    service db(database)[База] in cloud
    service s3(disk)[Хранилище] in cloud
    service web(internet)[Клиенты]

    web:R -- L:api
    api:R -- L:db
    db:B -- T:s3
""", ("Сервис", "    service x(server)[Сервис]"),
        ("Группа", "    group g(cloud)[Группа]"),
        ("Связь", "    a:R -- L:b")),
    "c4": _t("Архитектура", "C4", """
C4Context
    title Контекст системы
    Person(user, "Аналитик", "Готовит отчёты")
    System(pdf, "a2pdf", "Документы в фирменном стиле")
    System_Ext(notion, "Notion", "Источник текстов")
    Rel(user, pdf, "Загружает markdown")
    Rel(pdf, notion, "Читает страницы", "HTTPS")
""", ("Человек", '    Person(p, "Роль", "описание")'),
        ("Система", '    System(s, "Система", "описание")'),
        ("Внешняя", '    System_Ext(e, "Внешняя", "описание")'),
        ("Связь", '    Rel(a, b, "что делает")')),
    "class": _t("Архитектура", "Классы", """
classDiagram
    class Document {
        +str title
        +list blocks
        +render() bytes
    }
    class Brand {
        +str key
        +dict colors
    }
    Document --> Brand : оформлен
    Document <|-- Report
""", ("Класс", "    class Name {\n        +field\n        +method()\n    }"),
        ("Наследование", "    Base <|-- Child"),
        ("Связь", "    A --> B : использует")),
    "er": _t("Архитектура", "Сущности (ER)", """
erDiagram
    CLIENT ||--o{ ORDER : "оформляет"
    ORDER ||--|{ ITEM : "содержит"
    CLIENT {
        int id PK
        string name
    }
    ORDER {
        int id PK
        date created
    }
""", ("Сущность", "    ENTITY {\n        int id PK\n    }"),
        ("Один ко многим", '    A ||--o{ B : "связь"'),
        ("Один к одному", '    A ||--|| B : "связь"')),
    "requirement": _t("Архитектура", "Требования", """
requirementDiagram

    requirement auth {
    id: 1
    text: "Вход по паролю"
    risk: medium
    verifymethod: test
    }

    element login_page {
    type: page
    }

    login_page - satisfies -> auth
""", ("Требование", "    requirement r {\n    id: 2\n    text: \"текст\"\n"
                       "    risk: low\n    verifymethod: test\n    }"),
        ("Элемент", "    element e {\n    type: module\n    }")),
    "block": _t("Архитектура", "Блоки", """
block-beta
columns 3
  src["Источники"]:3
  etl["ETL"] dwh[("Хранилище")] bi["BI"]
  etl --> dwh
  dwh --> bi
""", ("Блок", '  x["Блок"]'), ("Колонки", "columns 3"),
        ("Пусто", "  space")),
    "packet": _t("Архитектура", "Пакет", """
packet-beta
0-15: "Порт источника"
16-31: "Порт назначения"
32-63: "Номер последовательности"
64-95: "Номер подтверждения"
96-99: "Смещение"
100-105: "Резерв"
106-111: "Флаги"
112-127: "Окно"
""", ("Поле", '128-143: "Поле"')),
    "gitgraph": _t("Архитектура", "Git", """
gitGraph
    commit id: "init"
    branch develop
    checkout develop
    commit id: "фича"
    commit id: "тесты"
    checkout main
    merge develop tag: "v1.0"
    commit id: "hotfix"
""", ("Коммит", '    commit id: "изменение"'),
        ("Ветка", "    branch feature\n    checkout feature"),
        ("Слияние", "    checkout main\n    merge feature")),
    "treeview": _t("Архитектура", "Дерево файлов", """
treeView-beta
├── a2pdf/
│   ├── core.py
│   ├── diagrams.py
│   └── static/
│       └── index.html
├── tests/
└── README.md
""", ("Файл", "├── файл.txt"), ("Папка", "├── папка/\n│   └── файл.txt")),

    # ---------- данные и графики ----------
    "pie": _t("Данные", "Круговая", """
pie showData
    title Структура затрат
    "Инфраструктура" : 42
    "Разработка" : 33
    "Поддержка" : 15
    "Лицензии" : 10
""", ("Сектор", '    "Сектор" : 10')),
    "xychart": _t("Данные", "График", """
xychart-beta
    title "Выручка, млн"
    x-axis ["Янв", "Фев", "Мар", "Апр", "Май", "Июн"]
    y-axis "млн" 0 --> 120
    bar [42, 55, 61, 70, 88, 97]
    line [40, 50, 58, 72, 85, 101]
""", ("Столбцы", "    bar [10, 20, 30, 40, 50, 60]"),
        ("Линия", "    line [10, 20, 30, 40, 50, 60]")),
    "sankey": _t("Данные", "Потоки (Sankey)", """
sankey-beta

Бюджет,Инфраструктура,42
Бюджет,Разработка,33
Бюджет,Поддержка,15
Разработка,Бэкенд,20
Разработка,Фронтенд,13
""", ("Поток", "Откуда,Куда,10")),
    "radar": _t("Данные", "Радар", """
radar-beta
  title Компетенции команды
  axis py["Python"], sql["SQL"], ml["ML"]
  axis bi["BI"], ops["DevOps"], dm["Моделирование"]
  curve a["Команда A"]{85, 90, 60, 70, 55, 80}
  curve b["Команда B"]{70, 75, 85, 60, 80, 65}
  max 100
  min 0
""", ("Кривая", '  curve c["Ещё"]{50, 50, 50, 50, 50, 50}')),
    "treemap": _t("Данные", "Тримэп", """
treemap-beta
"Продажи"
    "Казахстан": 45
    "Узбекистан": 20
"Сервис"
    "Поддержка": 25
    "Обучение": 10
""", ("Раздел", '"Раздел"\n    "Пункт": 10')),
    "quadrant": _t("Данные", "Квадрант", """
quadrantChart
    title Приоритизация
    x-axis Низкая ценность --> Высокая ценность
    y-axis Низкие затраты --> Высокие затраты
    quadrant-1 Планировать
    quadrant-2 Пересмотреть
    quadrant-3 Отложить
    quadrant-4 Делать сейчас
    Отчёты: [0.8, 0.3]
    ML-модель: [0.7, 0.8]
    Миграция: [0.3, 0.7]
""", ("Точка", "    Пункт: [0.5, 0.5]")),
    "venn": _t("Данные", "Венн", """
venn-beta
  title Хороший продукт
  set need["Нужен"]
  set can["Реализуем"]
  set pay["Окупится"]
  union need,can["Можно делать"]
  union can,pay["Устойчиво"]
  union need,pay["Продаётся"]
  union need,can,pay["В работу"]
""", ("Множество", '  set x["Новое"]'), ("Пересечение", '  union a,b["Общее"]')),

    # ---------- планирование ----------
    "gantt": _t("Планирование", "Диаграмма Ганта", """
gantt
    title План проекта
    dateFormat YYYY-MM-DD
    axisFormat %d.%m
    section Анализ
    Интервью        :done, a1, 2026-10-01, 7d
    Требования      :active, a2, after a1, 5d
    section Разработка
    Витрина данных  :b1, after a2, 14d
    Дашборды        :crit, b2, after b1, 10d
    Сдача           :milestone, m1, after b2, 0d
""", ("Секция", "    section Этап"), ("Задача", "    Задача :t1, after a1, 5d"),
        ("Критичная", "    Задача :crit, t2, after t1, 3d"),
        ("Веха", "    Сдача :milestone, m2, after t2, 0d")),
    "timeline": _t("Планирование", "Хронология", """
timeline
    title Дорожная карта
    2026 Q1 : Пилот : Сбор требований
    2026 Q2 : MVP
    2026 Q3 : Промышленный запуск
""", ("Этап", "    2026 Q4 : Событие")),
    "kanban": _t("Планирование", "Канбан", """
kanban
  todo[Сделать]
    t1[Сверстать обложку]
    t2[Подключить Notion]
  doing[В работе]
    t3[Конструктор схем]
  done[Готово]
    t4[Оглавление]
""", ("Колонка", "  col[Колонка]"), ("Задача", "    task[Задача]")),
    "mindmap": _t("Планирование", "Карта мыслей", """
mindmap
  root((Платформа данных))
    Источники
      CRM
      1С
    Хранилище
      Озеро
      Витрины
    Аналитика
      Дашборды
      ML
""", ("Ветка", "    Ветка\n      Лист")),

    # ---------- анализ и стратегия ----------
    "ishikawa": _t("Анализ", "Исикава", """
ishikawa-beta
    Отчёт опаздывает
    Данные
        Источник недоступен
        Дубли в выгрузке
    Люди
        Нет дежурного
    Процесс
        Ручная сверка
        Нет SLA
    Инфраструктура
        Медленная база
""", ("Причина", "    Категория\n        Причина")),
    "wardley": _t("Анализ", "Карта Уордли", """
wardley-beta
title Платформа отчётности

anchor "Клиент" [0.95, 0.63]
component "Отчёт" [0.79, 0.61]
component "Конвертер" [0.63, 0.55]
component "Шаблоны" [0.52, 0.30]
component "Облако" [0.10, 0.85]

"Клиент" -> "Отчёт"
"Отчёт" -> "Конвертер"
"Конвертер" -> "Шаблоны"
"Конвертер" -> "Облако"

evolve "Шаблоны" 0.62
note "Шаблоны уходят в товар" [0.35, 0.45]
""", ("Компонент", 'component "Новый" [0.5, 0.5]'), ("Связь", '"A" -> "B"')),
    "cynefin": _t("Анализ", "Cynefin", """
cynefin-beta
  title Разбор инцидента

  complex
    "Искать первопричину"

  complicated
    "Анализ метрик"
    "Ревью эксперта"

  clear
    "Перезапуск сервиса"

  chaotic
    "Поднять дежурного"

  confusion
    "Непонятный сбой"
""", ("Пункт", '    "Пункт"')),
    "railroad": _t("Анализ", "Синтаксис (railroad)", """
railroad-ebnf-beta
title "Номер договора"

contract = prefix "-" digit digit digit ;
prefix = "КП" | "ДГ" | "СЧ" ;
digit = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
""", ("Правило", 'rule = "a" | "b" ;')),
}
