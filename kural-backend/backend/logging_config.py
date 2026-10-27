"""Logging setup. Only metadata is logged: never request bodies, transcripts,
personal details, uploaded files or API keys (PRD p.5 privacy)."""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    if not any(getattr(h, "_kural", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler._kural = True  # type: ignore[attr-defined]
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)
    # httpx logs every request URL at INFO; keep third-party chatter out of logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # WeasyPrint/fontTools log per-render progress at INFO; keep only warnings.
    logging.getLogger("weasyprint.progress").setLevel(logging.WARNING)
    logging.getLogger("fontTools").setLevel(logging.WARNING)
