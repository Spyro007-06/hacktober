"""Local speech-to-text (PRD feature 1; POST /api/transcribe).

Pipeline: validate upload -> decode with PyAV (in memory) -> 16 kHz mono float32
-> split into <= AUDIO_CHUNK_S chunks at quiet points -> faster-whisper per chunk
-> join. Everything runs on this machine:

- The model is loaded from a local folder only (local_files_only, HF_HUB_OFFLINE=1);
  nothing is downloaded at runtime (see scripts/download_stt_model.py).
- Audio is decoded from an in-memory buffer, never a path or URL, and is never
  written by Kural. Transcripts and audio are never logged (sizes/timings only).
- faster_whisper.audio.decode_audio is NOT used: it is incompatible with PyAV 19
  (it passes the removed `metadata_errors` argument to av.open).
- Whisper's temperature fallback is disabled and speech is pre-filtered with the
  bundled Silero VAD: on noise it otherwise retries decoding at higher
  temperatures, which took 34-42 s for 3 s of Tamil-mode noise in a measured test.
- One lazily loaded model, one inference at a time, and a bounded number of
  requests in flight, so a low-memory machine is never oversubscribed.
- The speaker's words are transcribed in the language given; nothing is translated
  (task="transcribe", language fixed, no detection).
"""
import io
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

import numpy as np

from backend.config import Settings
from backend.errors import bad_input, model_timeout, model_unavailable

log = logging.getLogger("kural.stt")

SAMPLE_RATE = 16000
MAX_CONCURRENT_REQUESTS = 3  # one transcribing + two waiting; more get a 503
# Declared Content-Types accepted. The declared type is NOT trusted (the file header
# decides); this only rejects uploads that are plainly not WAV/WebM audio.
ALLOWED_MIME = {"", "application/octet-stream", "audio/webm", "video/webm",
                "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}
REQUIRED_MODEL_FILES = ("config.json", "model.bin", "tokenizer.json")

_request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)


class SttUnavailable(Exception):
    """Engine, package or model files are missing or unusable. `detail` is a short
    diagnostic for local logs and the benchmark; the API shows only str(self)."""

    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message)
        self.detail = detail


def describe_import_failure(exc: BaseException, package: str, label: str) -> tuple[str, str]:
    """(user-safe message, diagnostic detail) for a failed `import <package>`.
    Only a ModuleNotFoundError for the package itself is called "not installed": a
    missing dependency or a blocked/damaged native file (ImportError, OSError)
    is reported as what it is."""
    missing = exc.name.split(".")[0] if isinstance(exc, ModuleNotFoundError) and exc.name else None
    if missing == package:
        message = f"{label} is not installed."
    elif missing:
        message = f"{label} needs the package '{missing}', which is not installed."
    else:
        message = (f"{label} is installed but could not be loaded ({type(exc).__name__}). "
                   "A damaged package or a security policy may be blocking one of its files.")
    return message, f"{type(exc).__name__}: {_scrub(str(exc))}"


_PATH = re.compile(r"[A-Za-z]:[\\/][^\s'\"]*|\\\\[^\s'\"]+|/(?:[^\s'\"/]+/)+[^\s'\"]*")


def _scrub(text: str, limit: int = 200) -> str:
    """One short line with file-system paths removed: diagnostics may name a module
    or a policy, never where on the machine (or whose profile) a file lives."""
    return _PATH.sub("<path>", " ".join(text.split()))[:limit]


class SttFailed(Exception):
    """The model failed while processing audio."""


class SttTimeout(Exception):
    """The request deadline passed."""


class STTEngine(Protocol):
    name: str

    def transcribe(self, audio: np.ndarray, language: str, deadline: float) -> str:
        """audio: 16 kHz mono float32 of at most one chunk. `deadline` is a
        time.monotonic() value. Return the text, or '' when there is no speech."""


# -- validation ----------------------------------------------------------------------------
def detect_format(data: bytes) -> str:
    """WAV and WebM only (PRD p.9). Decided by the file header, not by name or MIME."""
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"\x1a\x45\xdf\xa3" and b"webm" in data[:64]:  # EBML header + DocType "webm"
        return "webm"
    raise bad_input("Unsupported audio format. Use WebM or WAV.")


def validate_upload(data: bytes, content_type: Optional[str], max_bytes: int) -> str:
    if not data:
        raise bad_input("The audio file is empty.")
    if len(data) > max_bytes:
        raise bad_input(f"The audio file is larger than {max_bytes // (1024 * 1024)} MB.")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in ALLOWED_MIME:
        raise bad_input("Unsupported audio type. Use WebM or WAV.")
    return detect_format(data)


# -- decoding ------------------------------------------------------------------------------
def decode_audio_bytes(data: bytes, max_seconds: float) -> np.ndarray:
    """Decode WAV/WebM bytes to 16 kHz mono float32 with PyAV. Aborts as soon as the
    audio exceeds `max_seconds`, so a small file of very long audio cannot exhaust
    memory. Raises a 400 AppError for unreadable, empty or over-long audio."""
    try:
        import av
    except (ImportError, OSError) as exc:
        message, detail = describe_import_failure(exc, "av", "The audio decoder (PyAV)")
        log.error("PyAV import failed error_type=%s detail=%s", type(exc).__name__, detail)
        raise model_unavailable(message)

    max_samples = int(max_seconds * SAMPLE_RATE)
    parts: list[np.ndarray] = []
    total = 0
    try:
        with av.open(io.BytesIO(data), mode="r") as container:  # a buffer only: never a path or URL
            if not container.streams.audio:
                raise bad_input("The file has no audio track.")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            frames = container.decode(audio=0)
            for frame in frames:
                for out in resampler.resample(frame):
                    arr = out.to_ndarray().reshape(-1)
                    total += arr.size
                    if total > max_samples:
                        raise bad_input(f"The audio is longer than {max_seconds:g} seconds.")
                    parts.append(arr)
            for out in resampler.resample(None):  # flush
                arr = out.to_ndarray().reshape(-1)
                total += arr.size
                if total > max_samples:
                    raise bad_input(f"The audio is longer than {max_seconds:g} seconds.")
                parts.append(arr)
    except (av.error.FFmpegError, ValueError, OSError, EOFError):
        raise bad_input("The audio could not be read. It may be corrupt.")
    if total == 0:
        raise bad_input("The audio contains no sound.")
    return np.concatenate(parts).astype(np.float32) / 32768.0


# -- chunking ------------------------------------------------------------------------------
def _quietest_cut(audio: np.ndarray, lo: int, hi: int, frame: int) -> int:
    """Sample index of the centre of the quietest `frame`-sample window in [lo, hi)."""
    n = (hi - lo) // frame
    if n <= 0:
        return hi
    energy = (audio[lo:lo + n * frame].astype(np.float64) ** 2).reshape(n, frame).mean(axis=1)
    quietest = int(np.flatnonzero(energy == energy.min())[-1])  # latest tie: closest to the limit
    return lo + quietest * frame + frame // 2


def split_chunks(audio: np.ndarray, chunk_s: float = 30, search_s: float = 2.0,
                 rate: int = SAMPLE_RATE, frame_ms: int = 20) -> list[np.ndarray]:
    """Split into chunks of at most `chunk_s` seconds (PRD: 30 s). Each cut is moved
    to the quietest 20 ms point within the last `search_s` seconds before the limit,
    so words are not cut in half. The chunks concatenate back to exactly `audio`."""
    limit = int(chunk_s * rate)
    if audio.size <= limit:
        return [audio]
    frame = max(1, int(rate * frame_ms / 1000))
    search = int(search_s * rate)
    chunks: list[np.ndarray] = []
    start = 0
    while audio.size - start > limit:
        target = start + limit
        lo = max(start + limit // 2, target - search)
        cut = _quietest_cut(audio, lo, target, frame)
        chunks.append(audio[start:cut])
        start = cut
    chunks.append(audio[start:])
    return chunks


def join_transcripts(parts: list[str]) -> str:
    return " ".join(p.strip() for p in parts if p and p.strip())


# -- the engine ----------------------------------------------------------------------------
class WhisperEngine:
    """faster-whisper on CPU (int8), loaded lazily from a local folder, one
    transcription at a time."""

    name = "whisper"

    def __init__(self, model_dir: Path, cpu_threads: int = 0, beam_size: int = 5):
        self.model_dir = Path(model_dir)
        self.cpu_threads = cpu_threads or max(1, min(8, (os.cpu_count() or 2) // 2))
        self.beam_size = beam_size
        self._model = None
        self._lock = threading.Lock()  # guards loading AND inference

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def check_files(self) -> Optional[str]:
        """None when the model folder looks complete, else a short problem text."""
        if not self.model_dir.is_dir():
            return "The speech model folder does not exist."
        missing = [f for f in REQUIRED_MODEL_FILES if not (self.model_dir / f).is_file()]
        if not any((self.model_dir / v).is_file() for v in ("vocabulary.txt", "vocabulary.json")):
            missing.append("vocabulary.txt")
        return f"The speech model is incomplete (missing: {', '.join(missing)})." if missing else None

    def _load(self) -> None:  # called with the lock held
        problem = self.check_files()
        if problem:
            raise SttUnavailable(problem)
        os.environ["HF_HUB_OFFLINE"] = "1"  # never reach the Hugging Face hub at runtime
        try:
            from faster_whisper import WhisperModel
        except (ImportError, OSError) as exc:
            message, detail = describe_import_failure(exc, "faster_whisper", "faster-whisper")
            log.error("faster-whisper import failed error_type=%s detail=%s", type(exc).__name__, detail)
            raise SttUnavailable(message, detail)
        start = time.perf_counter()
        try:
            self._model = WhisperModel(
                str(self.model_dir), device="cpu", compute_type="int8",
                cpu_threads=self.cpu_threads, num_workers=1, local_files_only=True)
        except Exception as exc:  # corrupt files, unsupported build, out of memory...
            log.error("speech model load failed error_type=%s", type(exc).__name__)
            raise SttUnavailable("The speech model could not be loaded.")
        log.info("speech model loaded ms=%.0f threads=%d", (time.perf_counter() - start) * 1000, self.cpu_threads)

    def transcribe(self, audio: np.ndarray, language: str, deadline: float) -> str:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not self._lock.acquire(timeout=remaining):
            raise SttTimeout()
        try:
            if self._model is None:
                self._load()
            try:
                segments, _info = self._model.transcribe(
                    audio, language=language, task="transcribe",  # never translate
                    beam_size=self.beam_size,
                    temperature=0.0,  # a single value: no temperature-fallback retries
                    vad_filter=True,  # drop non-speech before decoding
                    condition_on_previous_text=False,
                )
                texts = []
                for seg in segments:  # lazy: decoding happens here, so check the deadline per segment
                    if time.monotonic() > deadline:
                        raise SttTimeout()
                    texts.append(seg.text)
            except SttTimeout:
                raise
            except Exception as exc:
                log.error("transcription failed error_type=%s", type(exc).__name__)
                raise SttFailed("The speech model failed to process the audio.")
            return join_transcripts(texts)
        finally:
            self._lock.release()


def build_engine(settings: Settings) -> Optional[WhisperEngine]:
    """The engine for STT_ENGINE, or None when that engine is not implemented."""
    if settings.stt_engine == "whisper":
        return WhisperEngine(settings.stt_model_dir, settings.stt_cpu_threads, settings.stt_beam_size)
    return None


# -- orchestration -------------------------------------------------------------------------
@dataclass(frozen=True)
class Transcript:
    text: str
    chunks: int
    audio_s: float


def transcribe_upload(data: bytes, content_type: Optional[str], language: str,
                      get_engine: Callable[[], STTEngine], settings: Settings) -> Transcript:
    """Validate, decode, chunk and transcribe. Errors are AppErrors with the PRD
    codes: 400 BAD_INPUT, 503 MODEL_UNAVAILABLE, 504 MODEL_TIMEOUT."""
    if not _request_slots.acquire(blocking=False):
        raise model_unavailable("The speech service is busy. Please try again shortly.")
    try:
        started = time.monotonic()
        deadline = started + settings.stt_timeout_s
        validate_upload(data, content_type, settings.max_audio_mb * 1024 * 1024)
        audio = decode_audio_bytes(data, settings.max_audio_s)
        chunks = split_chunks(audio, settings.audio_chunk_s)
        engine = get_engine()  # 503 here if the engine is not implemented/configured
        parts: list[str] = []
        for chunk in chunks:
            if time.monotonic() > deadline:
                raise model_timeout()
            try:
                parts.append(engine.transcribe(chunk, language, deadline))
            except SttTimeout:
                raise model_timeout()
            except (SttUnavailable, SttFailed) as exc:
                raise model_unavailable(str(exc))
        text = join_transcripts(parts)
        if not text:
            raise bad_input("No speech was detected in the audio.")
        log.info("transcribed lang=%s audio_s=%.1f chunks=%d chars=%d ms=%.0f", language,
                 audio.size / SAMPLE_RATE, len(chunks), len(text), (time.monotonic() - started) * 1000)
        return Transcript(text, len(chunks), audio.size / SAMPLE_RATE)
    finally:
        _request_slots.release()
