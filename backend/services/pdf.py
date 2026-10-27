"""PDF rendering with WeasyPrint and the bundled Noto Sans Tamil font.

Safety:
- WeasyPrint is imported lazily, so a machine without Pango can still run the
  rest of the API; PDF routes then answer 503 PDF_UNAVAILABLE.
- The URL fetcher allows only `data:` URIs and the one bundled font file. A
  template or edited text can therefore never make the renderer read another
  local file or contact the network.
- The PDF is built in memory only. Nothing is written to disk or logged except
  size and timing.
"""
import logging
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from backend.errors import pdf_unavailable

log = logging.getLogger("kural.pdf")

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
FONT_PATH = FONTS_DIR / "NotoSansTamil[wdth,wght].ttf"
FONT_FAMILY = "Noto Sans Tamil"

# WeasyPrint is not documented as safe for concurrent renders; serialise them.
_render_lock = threading.Lock()


def _load_weasyprint() -> tuple[Any, Any, Any, Any]:
    """Return (HTML, CSS, FontConfiguration, URLFetcher). Raises ImportError or
    OSError when the package or Pango/GTK libraries are missing."""
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration
    from weasyprint.urls import URLFetcher

    return HTML, CSS, FontConfiguration, URLFetcher


def font_face_css() -> str:
    # Variable font. WeasyPrint rejects weight/width *range* descriptors, and does
    # not need them: it instantiates the Regular and Bold instances itself
    # (verified: the PDF embeds Noto-Sans-Tamil and Noto-Sans-Tamil-Bold).
    return f'@font-face {{ font-family: "{FONT_FAMILY}"; src: url("{FONT_PATH.as_uri()}"); }}'


def _is_bundled_font(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return False
    try:
        return Path(url2pathname(unquote(parsed.path))).resolve() == FONT_PATH.resolve()
    except OSError:
        return False


def make_fetcher(url_fetcher_cls: Any) -> Any:
    class SafeFetcher(url_fetcher_cls):  # type: ignore[misc, valid-type]
        def fetch(self, url, headers=None):
            if url.lower().startswith("data:") or _is_bundled_font(url):
                return super().fetch(url, headers)
            raise ValueError("blocked: only data URIs and the bundled font may be loaded")

    return SafeFetcher(allowed_protocols={"data", "file"}, allow_redirects=False)


def render_pdf(html: str) -> bytes:
    """Render a complete HTML document to PDF bytes."""
    try:
        HTML, CSS, FontConfiguration, URLFetcher = _load_weasyprint()
    except (ImportError, OSError) as exc:
        log.error("PDF engine unavailable error_type=%s", type(exc).__name__)
        raise pdf_unavailable("The PDF engine (WeasyPrint/Pango) is not available.")
    if not FONT_PATH.is_file():
        log.error("bundled Tamil font missing")
        raise pdf_unavailable("The bundled Tamil font is missing.")

    start = time.perf_counter()
    fetcher = make_fetcher(URLFetcher)
    with _render_lock:
        fonts = FontConfiguration()
        css = CSS(string=font_face_css(), font_config=fonts, url_fetcher=fetcher)
        data = HTML(string=html, url_fetcher=fetcher).write_pdf(stylesheets=[css], font_config=fonts)
    log.info("pdf rendered bytes=%d ms=%.0f", len(data), (time.perf_counter() - start) * 1000)
    return data
