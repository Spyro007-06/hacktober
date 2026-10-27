#!/usr/bin/env python
"""Benchmark Kural's local speech-to-text on YOUR recordings.

    .\\.venv\\Scripts\\python.exe scripts\\stt_benchmark.py            # uses .\\audio_samples
    .\\.venv\\Scripts\\python.exe scripts\\stt_benchmark.py --list     # only list what it would run

Put recordings (WAV or WebM) in `audio_samples/` with a matching UTF-8 `.txt` file holding
exactly what was said. The language comes from the file-name prefix: `ta_...` or `en_...`
(or pass --language), e.g.  ta_20s_streetlight.wav + ta_20s_streetlight.txt

It runs Kural's real pipeline (validation, PyAV decoding, chunking, the speech filter,
faster-whisper) and reports, per clip and overall:
  * CER  - character error rate (Unicode code points, after normalisation)
  * AER  - aksharam error rate: Tamil letter+vowel-sign+pulli clusters count as ONE unit,
           so one wrong vowel sign is one error, not two
  * WER  - word error rate (Tamil is agglutinative: expect WER to look much worse than CER)
  * speed (seconds, real-time factor), chunk count, and memory (Windows only)
  * the reference and hypothesis side by side, with the first word differences.

It reports numbers only: no pass/fail threshold is invented. Judge the transcripts yourself.

Privacy: everything is local (offline model, HF_HUB_OFFLINE=1, .env is never read). Nothing is
written unless you pass --report, and the report must live inside the samples folder, which is
git-ignored. The console output contains your transcripts: treat it as private.
"""
import argparse
import ctypes
import difflib
import os
import statistics
import sys
import textwrap
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # so `backend` imports when this runs as a script

import numpy as np  # noqa: E402

from backend.config import Settings  # noqa: E402
from backend.errors import AppError  # noqa: E402
from backend.services import stt  # noqa: E402

AUDIO_TYPES = {".wav": "audio/wav", ".webm": "audio/webm"}
ZERO_WIDTH = {"​", "‌", "‍", "﻿"}
VIRAMA = "்"  # Tamil pulli: joins the next consonant into the same cluster
WRAP = 100


# -- text normalisation and error metrics --------------------------------------------------------
def normalize(text: str) -> str:
    """NFC, case-folded, punctuation and zero-width characters removed, spaces collapsed."""
    t = unicodedata.normalize("NFC", text).casefold()
    t = "".join(c for c in t if c not in ZERO_WIDTH and not unicodedata.category(c).startswith("P"))
    return " ".join(t.split())


def clusters(text: str) -> list[str]:
    """Letter clusters, ignoring spaces: a base letter plus its combining vowel signs,
    and a consonant that follows a pulli (so க்ஷ and ஸ்ரீ are single units)."""
    out: list[str] = []
    prev = ""
    for ch in text.replace(" ", ""):
        joins = unicodedata.category(ch) in ("Mn", "Mc", "Me") or prev == VIRAMA
        if out and joins:
            out[-1] += ch
        else:
            out.append(ch)
        prev = ch
    return out


def edit_counts(ref, hyp) -> tuple[int, int, int, int]:
    """Levenshtein distance with the split (distance, substitutions, deletions, insertions)."""
    prev = [(j, 0, 0, j) for j in range(len(hyp) + 1)]
    for i in range(1, len(ref) + 1):
        cur = [(i, 0, i, 0)]
        for j in range(1, len(hyp) + 1):
            if ref[i - 1] == hyp[j - 1]:
                cur.append(prev[j - 1])
                continue
            s, d, n = prev[j - 1], prev[j], cur[j - 1]
            cur.append(min(((s[0] + 1, s[1] + 1, s[2], s[3]),       # substitution first on ties
                            (d[0] + 1, d[1], d[2] + 1, d[3]),       # reference unit missing from hypothesis
                            (n[0] + 1, n[1], n[2], n[3] + 1)),      # extra unit in hypothesis
                           key=lambda t: t[0]))
        prev = cur
    return prev[-1]


@dataclass(frozen=True)
class Score:
    distance: int
    subs: int
    dels: int
    ins: int
    ref_len: int

    @property
    def rate(self) -> float:
        if self.ref_len == 0:
            return 0.0 if self.distance == 0 else 1.0
        return self.distance / self.ref_len


def score(ref_units, hyp_units) -> Score:
    d, s, de, i = edit_counts(ref_units, hyp_units)
    return Score(d, s, de, i, len(ref_units))


def metrics(reference: str, hypothesis: str) -> dict[str, Score]:
    r, h = normalize(reference), normalize(hypothesis)
    return {"cer": score(r, h), "aer": score(clusters(r), clusters(h)), "wer": score(r.split(), h.split())}


# -- finding the recordings ------------------------------------------------------------------------
@dataclass(frozen=True)
class Sample:
    audio: Path
    reference: Path
    language: str


def language_of(path: Path) -> Optional[str]:
    stem = path.stem.lower()
    for lang in ("ta", "en"):
        if stem == lang or stem.startswith((lang + "_", lang + "-")):
            return lang
    return None


def discover(folder: Path, language: Optional[str] = None) -> tuple[list[Sample], list[str]]:
    """Pairs of (recording, reference text). Returns (samples, reasons for skipped files)."""
    samples: list[Sample] = []
    skipped: list[str] = []
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in AUDIO_TYPES:
            continue
        lang = language or language_of(path)
        reference = path.with_suffix(".txt")
        if lang is None:
            skipped.append(f"{path.name}: no language (name it ta_... or en_..., or pass --language)")
        elif not reference.is_file():
            skipped.append(f"{path.name}: no reference file {reference.name}")
        elif not normalize(reference.read_text(encoding="utf-8-sig")):
            skipped.append(f"{path.name}: the reference file is empty")
        else:
            samples.append(Sample(path, reference, lang))
    return samples, skipped


# -- memory (Windows) ------------------------------------------------------------------------------
class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t)]


def process_memory() -> Optional[dict[str, float]]:
    """This process's working set and peak (MB), or None off Windows."""
    if sys.platform != "win32":
        return None
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    pmc = _PMC()
    pmc.cb = ctypes.sizeof(_PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_uint32]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(handle), ctypes.byref(pmc), pmc.cb):
        return None
    mb = 1024 * 1024
    return {"ws": pmc.WorkingSetSize / mb, "peak_ws": pmc.PeakWorkingSetSize / mb,
            "peak_commit": pmc.PeakPagefileUsage / mb}


class PeakSampler:
    """Samples the working set every 50 ms; `reset()` starts a new measurement window."""

    def __init__(self, read: Callable[[], Optional[dict]] = process_memory):
        self._read = read
        self.peak = 0.0
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop:
            m = self._read()
            if m:
                self.peak = max(self.peak, m["ws"])
            time.sleep(0.05)

    def start(self):
        self._thread.start()

    def reset(self):
        m = self._read()
        self.peak = m["ws"] if m else 0.0

    def stop(self):
        self._stop = True


# -- running ----------------------------------------------------------------------------------------
class TimingEngine:
    """Wraps an engine and records how long each chunk took."""

    def __init__(self, engine):
        self.engine = engine
        self.name = engine.name
        self.chunk_seconds: list[float] = []

    def transcribe(self, audio, language, deadline):
        start = time.perf_counter()
        try:
            return self.engine.transcribe(audio, language, deadline)
        finally:
            self.chunk_seconds.append(time.perf_counter() - start)


@dataclass
class ClipResult:
    sample: Sample
    reference: str
    hypothesis: str = ""
    audio_s: float = 0.0
    chunks: int = 0
    seconds: float = 0.0           # median over repeats
    runs: list[float] = field(default_factory=list)
    chunk_seconds: list[float] = field(default_factory=list)
    peak_mb: Optional[float] = None
    error: Optional[str] = None    # a failure that makes the clip unscorable
    note: Optional[str] = None     # e.g. "no speech detected" (scored as an empty hypothesis)
    scores: Optional[dict[str, Score]] = None

    @property
    def rtf(self) -> Optional[float]:
        return self.seconds / self.audio_s if self.audio_s else None


def run_benchmark(samples: list[Sample], engine, settings: Settings, repeat: int = 1,
                  sampler: Optional[PeakSampler] = None,
                  on_clip: Callable[[ClipResult], None] = lambda r: None) -> list[ClipResult]:
    results: list[ClipResult] = []
    for sample in samples:
        reference = sample.reference.read_text(encoding="utf-8-sig").strip()
        res = ClipResult(sample, reference)
        data = sample.audio.read_bytes()
        mime = AUDIO_TYPES[sample.audio.suffix.lower()]
        if sampler:
            sampler.reset()
        for _ in range(max(1, repeat)):
            timing = TimingEngine(engine)
            start = time.perf_counter()
            try:
                out = stt.transcribe_upload(data, mime, sample.language, lambda: timing, settings)
                res.hypothesis, res.audio_s, res.chunks = out.text, out.audio_s, out.chunks
            except AppError as exc:
                if exc.code == "BAD_INPUT" and "No speech" in exc.message:
                    res.hypothesis, res.note = "", "no speech detected (scored as an empty transcript)"
                else:
                    res.error = f"{exc.code}: {exc.message}"
                    break
            res.runs.append(time.perf_counter() - start)
            res.chunk_seconds = timing.chunk_seconds
        if res.runs:
            res.seconds = statistics.median(res.runs)
        if sampler:
            res.peak_mb = sampler.peak or None
        if res.error is None:
            res.scores = metrics(reference, res.hypothesis)
        results.append(res)
        on_clip(res)
    return results


# -- reporting ---------------------------------------------------------------------------------------
def pct(x: float) -> str:
    return f"{x * 100:5.1f}%"


def word_differences(reference: str, hypothesis: str, limit: int = 10) -> list[str]:
    r, h = normalize(reference).split(), normalize(hypothesis).split()
    lines = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=r, b=h, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        lines.append(f"  {' '.join(r[i1:i2]) or '(nothing)'}  ->  {' '.join(h[j1:j2]) or '(missing)'}")
        if len(lines) >= limit:
            lines.append("  ...")
            break
    return lines


def wrap(label: str, text: str) -> list[str]:
    return textwrap.wrap(text or "(empty)", WRAP, initial_indent=f"{label} ", subsequent_indent=" " * (len(label) + 1)) or [label]


def format_clip(r: ClipResult) -> list[str]:
    s = r.sample
    lines = ["", f"===== {s.audio.name}  [{s.language}]  {r.audio_s:.1f} s audio ====="]
    if r.error:
        return lines + [f"FAILED: {r.error}", "  (excluded from the totals)"]
    lines += wrap("reference :", r.reference) + wrap("hypothesis:", r.hypothesis)
    sc = r.scores
    lines.append(f"CER {pct(sc['cer'].rate)} (sub {sc['cer'].subs}, del {sc['cer'].dels}, ins {sc['cer'].ins} of {sc['cer'].ref_len} chars)"
                 f" | AER {pct(sc['aer'].rate)} ({sc['aer'].distance}/{sc['aer'].ref_len} letters)"
                 f" | WER {pct(sc['wer'].rate)} ({sc['wer'].distance}/{sc['wer'].ref_len} words)")
    mem = f" | peak RAM {r.peak_mb:,.0f} MB" if r.peak_mb else ""
    reps = f" (median of {len(r.runs)})" if len(r.runs) > 1 else ""
    rtf = f"{r.rtf:.2f}x real time" if r.rtf is not None else "n/a"
    lines.append(f"time {r.seconds:.1f} s{reps} = {rtf} | chunks {r.chunks} "
                 f"({', '.join(f'{c:.1f}s' for c in r.chunk_seconds)}){mem}")
    if r.note:
        lines.append(f"note: {r.note}")
    diffs = word_differences(r.reference, r.hypothesis)
    if diffs:
        lines.append("word differences (reference -> hypothesis):")
        lines += diffs
    return lines


def aggregate(results: list[ClipResult]) -> dict[str, Score]:
    """Pooled scores: errors summed over all clips, divided by total reference length."""
    out = {}
    for key in ("cer", "aer", "wer"):
        parts = [r.scores[key] for r in results if r.scores]
        out[key] = Score(sum(p.distance for p in parts), sum(p.subs for p in parts), sum(p.dels for p in parts),
                         sum(p.ins for p in parts), sum(p.ref_len for p in parts))
    return out


def format_summary(results: list[ClipResult], load_seconds: Optional[float], model_dir: Path, beam: int,
                   threads: int, overall_peak: Optional[dict]) -> list[str]:
    ok = [r for r in results if r.scores]
    lines = ["", "=" * 70, "SUMMARY",
             f"model: {model_dir} | beam {beam} | cpu threads {threads} | clips scored {len(ok)} of {len(results)}"]
    if load_seconds is not None:
        lines.append(f"model load + warm-up (1 s of silence): {load_seconds:.1f} s")
    for lang in ("ta", "en"):
        group = [r for r in ok if r.sample.language == lang]
        if group:
            a = aggregate(group)
            secs = sum(r.seconds for r in group)
            audio = sum(r.audio_s for r in group)
            lines.append(f"{lang}: {len(group)} clip(s) | CER {pct(a['cer'].rate)} | AER {pct(a['aer'].rate)} | "
                         f"WER {pct(a['wer'].rate)} | {audio:.0f} s of audio in {secs:.0f} s = {secs / audio if audio else 0:.2f}x real time")
    if ok:
        a = aggregate(ok)
        lines.append(f"all: CER {pct(a['cer'].rate)} | AER {pct(a['aer'].rate)} | WER {pct(a['wer'].rate)} "
                     "(pooled over all characters, letters and words)")
        slowest = max(ok, key=lambda r: r.rtf or 0)
        lines.append(f"slowest clip: {slowest.sample.audio.name} at {slowest.rtf:.2f}x real time ({slowest.seconds:.1f} s)")
    failed = [r for r in results if r.error]
    for r in failed:
        lines.append(f"FAILED: {r.sample.audio.name}: {r.error}")
    if overall_peak:
        lines.append(f"memory: peak working set {overall_peak['peak_ws']:,.0f} MB, peak commit {overall_peak['peak_commit']:,.0f} MB (whole run)")
    lines.append("These are measurements on your clips, not an accuracy guarantee. Read the transcripts above.")
    return lines


# -- command line -------------------------------------------------------------------------------------
def make_engine(model_dir: Path, threads: int, beam: int):
    return stt.WhisperEngine(model_dir, threads, beam)


def main(argv: Optional[list[str]] = None, out: Callable[[str], None] = print) -> int:
    defaults = Settings(_env_file=None)  # never reads .env: it holds secrets
    ap = argparse.ArgumentParser(description="Benchmark local STT on your recordings.")
    ap.add_argument("--samples", type=Path, default=ROOT / "audio_samples")
    ap.add_argument("--model-dir", type=Path, default=defaults.stt_model_dir)
    ap.add_argument("--beam", type=int, default=defaults.stt_beam_size)
    ap.add_argument("--threads", type=int, default=0, help="0 = automatic")
    ap.add_argument("--repeat", type=int, default=1, help="repeat each clip N times (median time)")
    ap.add_argument("--language", choices=["ta", "en"], help="override the file-name prefix")
    ap.add_argument("--timeout", type=int, default=600, help="per-clip time limit in seconds")
    ap.add_argument("--report", type=Path, help="also write the output here (must be inside the samples folder)")
    ap.add_argument("--list", action="store_true", help="only list the clips; decode nothing, load no model")
    args = ap.parse_args(argv)

    os.environ["HF_HUB_OFFLINE"] = "1"
    folder = args.samples
    if not folder.is_dir():
        out(f"The samples folder does not exist: {folder}")
        out("Create it and put recordings (WAV/WebM) there, each with a matching .txt reference "
            "(see the top of this script).")
        return 2
    report_path = None
    if args.report:
        report_path = args.report.resolve()
        if folder.resolve() not in report_path.parents:
            out(f"Refusing: --report must be inside the samples folder ({folder.resolve()}), which is git-ignored.")
            return 2

    samples, skipped = discover(folder, args.language)
    for reason in skipped:
        out(f"skipped: {reason}")
    if not samples:
        out("No usable recordings found (need name.wav/.webm + name.txt, named ta_... or en_...).")
        return 2
    if args.list:
        for s in samples:
            out(f"{s.audio.name}  [{s.language}]  {s.audio.stat().st_size:,} bytes  reference: {s.reference.name}")
        out(f"{len(samples)} clip(s) would be benchmarked. Nothing was decoded and no model was loaded.")
        return 0

    engine = make_engine(args.model_dir, args.threads, args.beam)
    problem = engine.check_files()
    if problem:
        out(f"Cannot run: {problem} ({args.model_dir})")
        return 2
    # The app's own limits (MAX_AUDIO_S etc. defaults), so the benchmark behaves like the endpoint.
    settings = Settings(_env_file=None, stt_timeout_s=args.timeout, stt_model_dir=args.model_dir)

    lines: list[str] = []

    def emit(text: str) -> None:
        lines.append(text)
        out(text)

    emit(f"Benchmarking {len(samples)} clip(s) with the local model. Output contains your transcripts: keep it private.")
    sampler = PeakSampler()
    sampler.start()
    t0 = time.perf_counter()
    try:  # load the model (and warm up) separately, so clip timings do not include loading
        engine.transcribe(np.zeros(16000, dtype=np.float32), samples[0].language, time.monotonic() + args.timeout)
    except (stt.SttUnavailable, stt.SttFailed, stt.SttTimeout) as exc:
        sampler.stop()
        emit(f"Cannot run: the model failed to load or run: {exc}")
        if getattr(exc, "detail", None):
            emit(f"Cause: {exc.detail}")
        return 1
    load_seconds = time.perf_counter() - t0
    results = run_benchmark(samples, engine, settings, args.repeat, sampler,
                            on_clip=lambda r: [emit(line) for line in format_clip(r)])
    sampler.stop()
    for line in format_summary(results, load_seconds, args.model_dir, args.beam, engine.cpu_threads, process_memory()):
        emit(line)
    if report_path:
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out(f"report written: {report_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Tamil on the Windows console
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
