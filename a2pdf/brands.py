"""Бренды, для которых сервис верстает документы.

Каждый бренд описан одинаковым набором ролей — цвета, шрифты, логотип,
реквизиты. Вёрстка документа читает только роли, поэтому добавить компанию
можно правкой одного словаря.

Роли цветов:
    brand        основной фирменный цвет (фон обложки, заголовки)
    brand_dark   его тёмный тон для градиента
    brand_50/100 светлые подложки для кода и плашек
    accent       рабочий акцент: ссылки, номера разделов, узлы схем
    accent_dark  тот же акцент для мелкого текста на белом
    accent_50    светлая подложка акцента
    mark         редкий акцент-метка: штрих на обложке, выноски
    mark_50      подложка выноски
    ink          цвет основного текста
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fonts:
    """Шрифты для вёрстки и их запрос к Google Fonts."""
    key: str                # чем набор выбирается в форме и API
    title: str              # как он называется для человека
    display: str            # заголовки
    body: str               # основной текст
    mono: str               # технический слой
    query: str              # families для fonts.googleapis.com
    word_body: str          # чем набирать в Word: там свои шрифты
    word_display: str
    word_mono: str
    display_weight: int = 700
    display_tracking: str = "-.5px"


@dataclass(frozen=True)
class Brand:
    key: str
    name: str
    site: str
    place: str
    colors: dict[str, str]
    fonts: Fonts
    cover_style: str = "dark"          # каким фоном обложка выглядит по умолчанию
    logo: str = ""                     # имя файлов логотипа в assets/logo
    logo_width_mm: float = 25          # ширина знака на обложке
    logo_width_cm: float = 3.2         # ширина знака на титуле Word
    tagline: str = ""
    neutrals: dict[str, str] = field(default_factory=dict)

    def color(self, role: str) -> str:
        return self.colors[role]


MONO_QUERY = "&family=JetBrains+Mono:wght@400;500"

INTER = Fonts(
    key="inter", title="Inter",
    display="Inter", body="Inter", mono="JetBrains Mono",
    query="Inter:wght@400;500;600;700;800" + MONO_QUERY,
    word_body="Segoe UI", word_display="Segoe UI", word_mono="Consolas")

OSWALD = Fonts(
    key="oswald", title="Oswald + Roboto Condensed",
    display="Oswald", body="Roboto Condensed", mono="JetBrains Mono",
    query=("Oswald:wght@300;400;500;600"
           "&family=Roboto+Condensed:wght@300;400;700" + MONO_QUERY),
    word_body="Segoe UI", word_display="Bahnschrift", word_mono="Consolas",
    display_weight=500, display_tracking="0px")

MANROPE = Fonts(
    key="manrope", title="Manrope",
    display="Manrope", body="Manrope", mono="JetBrains Mono",
    query="Manrope:wght@400;500;600;700;800" + MONO_QUERY,
    word_body="Segoe UI", word_display="Segoe UI", word_mono="Consolas")

ROBOTO = Fonts(
    key="roboto", title="Roboto",
    display="Roboto", body="Roboto", mono="Roboto Mono",
    query=("Roboto:wght@400;500;700;900"
           "&family=Roboto+Mono:wght@400;500"),
    word_body="Segoe UI", word_display="Segoe UI", word_mono="Consolas")

PT_SERIF = Fonts(
    key="serif", title="PT Serif + PT Sans",
    display="PT Sans", body="PT Serif", mono="JetBrains Mono",
    query=("PT+Serif:wght@400;700&family=PT+Sans:wght@400;700" + MONO_QUERY),
    word_body="Georgia", word_display="Segoe UI", word_mono="Consolas",
    display_tracking="-.2px")

FONT_SETS: dict[str, Fonts] = {f.key: f for f in
                               (INTER, OSWALD, MANROPE, ROBOTO, PT_SERIF)}


NEUTRALS_COOL = {"n0": "#FFFFFF", "n50": "#F7F8FA", "n100": "#EFF1F4",
                 "n200": "#E1E4EA", "n400": "#9CA3AF", "n500": "#6B7280",
                 "n700": "#374151", "n800": "#212934", "n900": "#111722"}

NEUTRALS_BECLOUD = {"n0": "#FFFFFF", "n50": "#F5F7FA", "n100": "#EDEFF5",
                    "n200": "#D7DCE5", "n400": "#8A8FA3", "n500": "#7F7F8F",
                    "n700": "#2C2C33", "n800": "#1A1B24", "n900": "#0F0F14"}

A2DATA = Brand(
    key="a2data",
    name="A2DATA",
    site="a2data.ai",
    place="Almaty, Kazakhstan",
    tagline="IT Consulting · Big Data · AI",
    colors={
        "brand": "#0B2660", "brand_dark": "#06173B",
        "brand_50": "#F2F5FA", "brand_100": "#E3EAF4",
        "accent": "#1FA8FC", "accent_dark": "#1289D5", "accent_50": "#F1F8FF",
        "accent_100": "#E1F2FF",
        "mark": "#FF9F1C", "mark_dark": "#B86A06", "mark_50": "#FFF8EC",
        "ink": "#111722", "muted": "#8FA6CE",
    },
    neutrals=NEUTRALS_COOL,
    fonts=INTER,
    cover_style="dark",
    logo="a2data",
)

BECLOUD = Brand(
    key="becloud",
    name="BeCloud.AI",
    site="becloud.ai",
    place="Almaty, Kazakhstan",
    tagline="",
    colors={
        "brand": "#2F3586", "brand_dark": "#17194F",
        "brand_50": "#F1F2F9", "brand_100": "#DDDFF0",
        "accent": "#4A6BFF", "accent_dark": "#3555F2", "accent_50": "#EEF1FF",
        "accent_100": "#DCE3FF",
        "mark": "#8B3DFF", "mark_dark": "#6B22D6", "mark_50": "#F4EDFF",
        "ink": "#0F0F14", "muted": "#8A8FA3",
    },
    neutrals=NEUTRALS_BECLOUD,
    # в Word фирменных шрифтов нет: Bahnschrift — ближайший узкий гротеск
    fonts=OSWALD,
    cover_style="dark",
    logo="becloud",
    # в знак BeCloud входит слоган, поэтому он крупнее
    logo_width_mm=38,
    logo_width_cm=4.6,
)

BRANDS: dict[str, Brand] = {brand.key: brand for brand in (A2DATA, BECLOUD)}
DEFAULT = A2DATA.key


def get(key: str | None) -> Brand:
    """Бренд по ключу; неизвестный ключ откатывается к основному."""
    return BRANDS.get((key or "").strip().lower(), BRANDS[DEFAULT])


def fonts_for(brand: Brand, key: str | None = None) -> Fonts:
    """Набор шрифтов: выбранный вручную или тот, что задан брендбуком."""
    return FONT_SETS.get((key or "").strip().lower(), brand.fonts)


def rgba(color: str, alpha: float) -> str:
    color = color.lstrip("#")
    red, green, blue = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({red},{green},{blue},{alpha})"


def tokens(brand: Brand, fonts: Fonts | None = None) -> str:
    """CSS-переменные бренда и выбранного набора шрифтов."""
    fonts = fonts or brand.fonts
    values = {**brand.colors, **brand.neutrals}
    lines = "".join(f"  --{role.replace('_', '-')}:{value};\n"
                    for role, value in values.items())
    glow = (f"radial-gradient(circle,{rgba(brand.colors['accent'], .34)} 0,"
            f"{rgba(brand.colors['accent'], 0)} 62%)")
    tint = (f"linear-gradient(155deg,{rgba(brand.colors['brand'], .80)} 0%,"
            f"{rgba(brand.colors['brand_dark'], .95)} 82%)")
    return (":root{\n" + lines +
            f"  --muted-on-dark:{brand.colors['muted']};\n"
            f"  --cover-glow:{glow};\n"
            f"  --cover-tint:{tint};\n" +
            f"  --font:'{fonts.body}','Segoe UI',Arial,sans-serif;\n"
            f"  --display:'{fonts.display}','{fonts.body}',"
            "'Segoe UI',Arial,sans-serif;\n"
            f"  --mono:'{fonts.mono}','Cascadia Mono',Consolas,monospace;\n"
            f"  --display-weight:{fonts.display_weight};\n"
            f"  --display-tracking:{fonts.display_tracking};\n"
            "}\n")
