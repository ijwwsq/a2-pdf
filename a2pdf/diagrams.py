"""Оформление диаграмм mermaid: пресеты, палитры и тема.

Пресет задаёт не только подложку, но и цвета элементов: заливку узлов,
обводку, линии и подписи. Свои цвета в classDef перекрывают тему mermaid,
поэтому их подменяем палитрой пресета.
"""
from __future__ import annotations

import json
import re

from . import brands


def tint(color: str, alpha: float) -> str:
    """Цвет с прозрачностью в виде #RRGGBBAA — запятых внутри значения нет,
    поэтому его можно писать и в classDef."""
    return color + format(round(max(0.0, min(1.0, alpha)) * 255), "02X")


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

    fill, stroke, text = palette[0]
    return {"key": key, "palette": palette, "theme": theme,
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


def theme_diagram(src: str, brand: brands.Brand,
                  style: dict | None = None) -> str:
    """Свои цвета в classDef и style перекрывают тему mermaid, поэтому
    подменяем их палитрой пресета: группы узлов остаются различимыми."""
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


def mermaid_init(brand: brands.Brand, fonts: brands.Fonts | None = None,
                 style: dict | None = None) -> str:
    """Тема mermaid в цветах пресета и выбранных шрифтах."""
    fonts = fonts or brand.fonts
    style = style or scheme_style(None, brand)
    theme = {"fontFamily": f"{fonts.body}, 'Segoe UI', sans-serif",
             "fontSize": "13px",
             "secondaryColor": brand.colors["brand_50"],
             "tertiaryColor": brand.colors["mark_50"],
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
    return """
mermaid.initialize({
  startOnLoad:false, theme:'base', securityLevel:'loose',
  flowchart:{curve:'basis',htmlLabels:true,useMaxWidth:true},
  sequence:{useMaxWidth:true,actorMargin:40,width:150},
  themeVariables:%(theme)s
});
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
for (const svg of document.querySelectorAll('.dg-mermaid svg')) {
  svg.removeAttribute('width');
  svg.removeAttribute('height');
  svg.style.maxWidth = '100%%';
  svg.style.maxHeight = '198mm';
  svg.style.width = 'auto';
  svg.style.height = 'auto';
}
""" % {"body": fonts.body, "theme": json.dumps(theme, ensure_ascii=False)}
