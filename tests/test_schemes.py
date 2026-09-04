"""Пресеты схем и перекраска пользовательских classDef."""
import pytest

from a2pdf import brands, core

BRANDS = ["a2data", "becloud"]
SRC = """flowchart LR
    A[Раз] --> B[Два]
    classDef edge fill:#e6f0fa,stroke:#1f5c8f,color:#16202e
    classDef ext fill:#fdecea,stroke:#b23b3b
    class A edge
    class B ext
"""


@pytest.mark.parametrize("key", list(core.DIAGRAM_SCHEMES))
@pytest.mark.parametrize("brand_key", BRANDS)
def test_style_is_complete(key, brand_key):
    style = core.scheme_style(key, brands.get(brand_key))
    assert style["key"] == key
    assert len(style["palette"]) >= 4
    for fill, stroke, text in style["palette"]:
        assert fill.startswith("#") and stroke.startswith("#")
        assert text.startswith("#")
    for field in ("mainBkg", "nodeBorder", "textColor", "lineColor"):
        assert style["theme"][field]


def test_unknown_scheme_falls_back():
    style = core.scheme_style("нет такого", brands.get("a2data"))
    assert style["key"] == core.DEFAULT_SCHEME


def test_old_scheme_keys_still_resolve():
    # до переделки пресеты назывались иначе, ссылки на них не должны падать
    for old in ("plain", "card"):
        assert core.scheme_style(old, brands.get("a2data"))["key"] == core.DEFAULT_SCHEME


@pytest.mark.parametrize("key", list(core.DIAGRAM_SCHEMES))
def test_classdef_repainted_without_commas(key):
    brand = brands.get("becloud")
    style = core.scheme_style(key, brand)
    out = core.theme_diagram(SRC, brand, style)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("classDef")]
    assert len(lines) == 2
    for line in lines:
        assert "#e6f0fa" not in line and "#1f5c8f" not in line
        # запятая внутри значения ломает разбор classDef
        assert "rgba(" not in line


def test_classdef_groups_stay_distinct():
    brand = brands.get("a2data")
    out = core.theme_diagram(SRC, brand, core.scheme_style("outline", brand))
    edge, ext = [ln for ln in out.splitlines() if "classDef" in ln]
    assert edge.split("stroke:")[1] != ext.split("stroke:")[1]


def test_diagram_without_classdef_untouched():
    brand = brands.get("a2data")
    src = "flowchart LR\n  A --> B\n"
    assert core.theme_diagram(src, brand, core.scheme_style(None, brand)) == src


def test_stroke_width_is_not_treated_as_stroke():
    brand = brands.get("a2data")
    src = "flowchart LR\n  A --> B\n  classDef x fill:#fff,stroke-width:4px\n"
    out = core.theme_diagram(src, brand, core.scheme_style("solid", brand))
    assert "stroke-width:4px" in out


def test_tint_produces_eight_digit_hex():
    assert core.tint("#112233", 0.5) == "#11223380"
    assert core.tint("#112233", 0) == "#11223300"
    assert core.tint("#112233", 1) == "#112233FF"


@pytest.mark.parametrize("key", list(core.DIAGRAM_SCHEMES))
def test_scheme_css_mentions_shape_and_labels(key):
    style = core.scheme_style(key, brands.get("a2data"))
    css = core.scheme_css(style)
    assert "rx:" in css and "edgeLabel" in css


@pytest.mark.parametrize("key", list(core.DIAGRAM_SCHEMES))
def test_preview_colors_present(key):
    preview = core.scheme_style(key, brands.get("a2data"))["preview"]
    assert set(preview) == {"bg", "fill", "stroke", "text"}
    assert preview["fill"] and preview["stroke"]


def test_mermaid_init_is_valid_json_theme():
    brand = brands.get("becloud")
    js = core.mermaid_init(brand, brand.fonts, core.scheme_style("dark", brand))
    assert "themeVariables:" in js
    assert "mermaid.run({querySelector: '.mermaid', suppressErrors: true})" in js


def test_dark_scheme_marked_dark_and_clear_transparent():
    assert core.DIAGRAM_SCHEMES["dark"]["dark"] is True
    assert core.DIAGRAM_SCHEMES["clear"]["clear"] is True
