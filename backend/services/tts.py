"""Offline text-to-speech (POST /api/tts, PRD feature 10).

Speech comes from Piper (https://github.com/OHF-Voice/piper1-gpl), which is GPL-3.0.
Kural does NOT import it or list it in requirements.txt: it is run as a separate local
process from its own virtual environment, configured with TTS_PIPER_PYTHON and one
voice file per language. With TTS_ENGINE=none (the default) or a language without a
configured voice, the API answers 501 and the UI shows text only.

Everything is local: no network, nothing is stored (the WAV is made in a temporary
folder that is removed), and the text is never logged. The command line is a fixed
argument list (no shell); the text goes to the process on stdin.
"""
import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, Protocol

from backend.config import Settings
from backend.errors import bad_input, model_unavailable, tts_unavailable

log = logging.getLogger("kural.tts")

BUSY_WAIT_S = 5


class TtsEngine(Protocol):
    name: str

    def supports(self, language: str) -> bool: ...

    def synthesize(self, text: str, language: str) -> bytes:
        """WAV bytes for `text`. Raises AppError (503) when synthesis fails."""


class PiperTts:
    name = "piper"

    def __init__(self, python: Optional[Path], voices: dict[str, Optional[Path]], timeout_s: int):
        self.python = python
        self.voices = voices
        self.timeout_s = timeout_s
        self._lock = threading.Lock()  # one synthesis at a time on a small machine

    def supports(self, language: str) -> bool:
        voice = self.voices.get(language)
        return bool(self.python and self.python.is_file() and voice and voice.is_file())

    def synthesize(self, text: str, language: str) -> bytes:
        voice = self.voices[language]
        if not self._lock.acquire(timeout=BUSY_WAIT_S):
            raise model_unavailable("Speech output is busy. Please try again shortly.")
        try:
            with tempfile.TemporaryDirectory(prefix="kural_tts_") as folder:
                out = Path(folder) / "speech.wav"
                # -X utf8: Piper reads stdin with the locale encoding (cp1252 on Windows),
                # which would garble Tamil; -I keeps the child out of the caller's PYTHON* settings.
                command = [str(self.python), "-I", "-X", "utf8", "-m", "piper",
                           "-m", str(voice), "-f", str(out)]
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                try:
                    done = subprocess.run(command, input=text.encode("utf-8"), capture_output=True,
                                          timeout=self.timeout_s, check=False, creationflags=flags)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    log.error("tts failed error_type=%s", type(exc).__name__)
                    raise model_unavailable("Speech output failed.")
                if done.returncode != 0 or not out.is_file() or out.stat().st_size < 64:
                    log.error("tts failed returncode=%s", done.returncode)  # never the text or stderr
                    raise model_unavailable("Speech output failed.")
                return out.read_bytes()
        finally:
            self._lock.release()


def build_tts(settings: Settings) -> Optional[TtsEngine]:
    """The engine for TTS_ENGINE, or None for 'none'."""
    if settings.tts_engine == "piper":
        return PiperTts(settings.tts_piper_python,
                        {"ta": settings.tts_voice_ta, "en": settings.tts_voice_en},
                        settings.tts_timeout_s)
    return None


def clean_text(text: str, max_chars: int) -> str:
    """Validate and normalise the text to speak. 400 for empty or over-long text."""
    cleaned = " ".join("".join(c if c.isprintable() or c in "\n\t" else " " for c in text).split())
    if not any(c.isalpha() for c in cleaned):
        raise bad_input("There is no text to speak.")
    if len(cleaned) > max_chars:
        raise bad_input(f"The text is longer than {max_chars} characters.")
    return cleaned


def speak(engine: Optional[TtsEngine], text: str, language: str, max_chars: int) -> bytes:
    cleaned = clean_text(text, max_chars)
    if engine is None or not engine.supports(language):
        raise tts_unavailable()
    return engine.synthesize(cleaned, language)
