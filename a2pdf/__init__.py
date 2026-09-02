"""a2pdf — превращает markdown и docx в PDF в фирменном оформлении A2DATA."""
from .core import (  # noqa: F401
    ASSETS,
    build,
    build_any,
    build_markdown,
    ensure_assets,
    find_chrome,
    parse,
    render,
    render_pdf,
    split_front_matter,
)

__all__ = ["build", "build_any", "build_markdown", "render_pdf", "parse", "render",
           "split_front_matter", "ensure_assets", "find_chrome", "ASSETS"]
__version__ = "1.0.0"
