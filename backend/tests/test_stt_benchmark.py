"""Tests for scripts/stt_benchmark.py. A fake engine stands in for Whisper: the real
model is never loaded and no recording of yours is read."""
import importlib.util
import re
import time
from pathlib import Path

import pytest

from backend.config import Settings
from backend.services.stt import SttFailed
from .conftest import NETWORK_ATTEMPTS, FakeSTTEngine, make_wav

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "stt_benchmark.py"
spec_ = importlib.util.spec_from_file_location("stt_benchmark", SCRIPT)
bench = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(bench)

TA_REF = "தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை"


class BenchFake(FakeSTTEngine):
    """FakeSTTEngine with the extra attributes the benchmark reads."""
    cpu_threads = 4

    def check_files(self):
        return None


@pytest.fixture(autouse=True)
def fake_engine_factory(monkeypatch):
    """Every main() run in this file gets a fake engine, never the real model."""
    made = []

    def make(model_dir, threads, beam):
        engine = made[0] if made else BenchFake("")
        return engine

    monkeypatch.setattr(bench, "make_engine", make)
    return made


def write_clip(folder: Path, name: str, reference: str, seconds=1.0, rate=16000):
    (folder / f"{name}.wav").write_bytes(make_wav(seconds, rate=rate))
    (folder / f"{name}.txt").write_text(reference, encoding="utf-8")


# -- normalisation and metrics -----------------------------------------------------------------
def test_normalize_ignores_case_punctuation_spacing_and_zero_width_marks():
    assert bench.normalize("  Hello,   WORLD! ") == "hello world"
    assert bench.normalize("தெரு‍விளக்கு,  எரிகிறது.") == "தெருவிளக்கு எரிகிறது"
    assert bench.normalize("") == "" and bench.normalize("...!?") == ""


def test_normalize_keeps_tamil_letters_intact():
    assert bench.normalize(TA_REF) == TA_REF


@pytest.mark.parametrize("text,expected", [
    ("க்ஷ", ["க்ஷ"]), ("ஸ்ரீ", ["ஸ்ரீ"]), ("கொடி", ["கொ", "டி"]), ("தமிழ்", ["த", "மி", "ழ்"]),
    ("abc", ["a", "b", "c"]), ("க ட", ["க", "ட"]), ("", []),
])
def test_tamil_letter_clusters(text, expected):
    assert bench.clusters(text) == expected


def test_edit_counts_known_values():
    d, s, dele, ins = bench.edit_counts("kitten", "sitting")
    assert d == 3 and s + dele + ins == 3
    assert bench.edit_counts("abc", "abc") == (0, 0, 0, 0)
    assert bench.edit_counts("", "abc") == (3, 0, 0, 3)
    assert bench.edit_counts("abc", "") == (3, 0, 3, 0)
    assert bench.edit_counts("abc".split(), "abd".split()) == (1, 1, 0, 0)
    assert bench.edit_counts(["a", "b"], ["a", "x", "b"]) == (1, 0, 0, 1)


def test_one_wrong_vowel_sign_is_penalised_per_metric_as_documented():
    m = bench.metrics("கொடி", "கோடி")      # கொ (க+ொ) vs கோ (க+ோ): one code point differs
    assert m["cer"].distance == 1 and m["cer"].ref_len == 4 and m["cer"].rate == pytest.approx(0.25)
    assert m["aer"].distance == 1 and m["aer"].ref_len == 2 and m["aer"].rate == pytest.approx(0.5)
    assert m["wer"].rate == pytest.approx(1.0)


def test_identical_text_scores_zero_after_normalisation():
    m = bench.metrics("Gandhi Street, near the library!", "gandhi street near the   library")
    assert all(m[k].rate == 0.0 for k in ("cer", "aer", "wer"))


def test_score_rate_handles_an_empty_reference():
    assert bench.Score(0, 0, 0, 0, 0).rate == 0.0 and bench.Score(3, 0, 0, 3, 0).rate == 1.0


def test_empty_hypothesis_is_a_total_miss():
    m = bench.metrics("hello world", "")
    assert m["cer"].rate == 1.0 and m["wer"].rate == 1.0
    assert m["cer"].dels == 11 and m["cer"].subs == 0 and m["cer"].ins == 0


def test_word_differences_show_what_changed():
    lines = bench.word_differences("the light is dead", "the lite is dead and gone")
    assert any("light  ->  lite" in l for l in lines) and any("(nothing)  ->  and gone" in l for l in lines)
    assert bench.word_differences("same text", "same text") == []


# -- finding recordings ---------------------------------------------------------------------------
def test_discover_pairs_audio_with_references_and_explains_every_skip(tmp_path):
    write_clip(tmp_path, "ta_one", TA_REF)
    write_clip(tmp_path, "en_two", "hello")
    (tmp_path / "ta_three.wav").write_bytes(make_wav(0.1))                 # no reference
    write_clip(tmp_path, "nolang", "text")                                  # no language prefix
    (tmp_path / "en_empty.wav").write_bytes(make_wav(0.1))
    (tmp_path / "en_empty.txt").write_text("  \n", encoding="utf-8")        # empty reference
    (tmp_path / "ta_four.mp3").write_bytes(b"x")                            # unsupported type: ignored
    (tmp_path / "notes.txt").write_text("not a reference for anything")
    (tmp_path / "sub").mkdir()
    samples, skipped = bench.discover(tmp_path)
    assert [(s.audio.name, s.language) for s in samples] == [("en_two.wav", "en"), ("ta_one.wav", "ta")]
    text = "\n".join(skipped)
    assert "ta_three.wav: no reference" in text and "nolang.wav: no language" in text and "en_empty.wav: the reference file is empty" in text
    assert "mp3" not in text


def test_language_override_applies_to_unprefixed_files(tmp_path):
    write_clip(tmp_path, "recording", "hello")
    samples, skipped = bench.discover(tmp_path, "en")
    assert [s.language for s in samples] == ["en"] and skipped == []


@pytest.mark.parametrize("name,lang", [("ta_x", "ta"), ("EN-x", "en"), ("ta", "ta"), ("tamil_x", None), ("data_ta", None), ("x", None)])
def test_language_comes_from_the_file_name_prefix(name, lang):
    assert bench.language_of(Path(name + ".wav")) == lang


def test_reference_files_with_a_byte_order_mark_are_read(tmp_path):
    (tmp_path / "ta_bom.wav").write_bytes(make_wav(0.5))
    (tmp_path / "ta_bom.txt").write_bytes("﻿".encode("utf-8") + TA_REF.encode("utf-8"))
    [s], _ = bench.discover(tmp_path)
    res = bench.run_benchmark([s], BenchFake(TA_REF), Settings(_env_file=None))[0]
    assert res.reference == TA_REF and res.scores["cer"].rate == 0.0


# -- running ----------------------------------------------------------------------------------------
def one(tmp_path, ref, hyp, name="ta_a", **kw):
    write_clip(tmp_path, name, ref, **kw)
    [s], _ = bench.discover(tmp_path)
    return bench.run_benchmark([s], BenchFake(hyp), Settings(_env_file=None))[0]


def test_a_perfect_transcript_scores_zero_and_records_timing(tmp_path):
    r = one(tmp_path, TA_REF, TA_REF, seconds=2.0)
    assert r.hypothesis == TA_REF and r.error is None and r.note is None
    assert all(r.scores[k].rate == 0.0 for k in ("cer", "aer", "wer"))
    assert r.audio_s == pytest.approx(2.0, abs=0.05) and r.chunks == 1 and len(r.chunk_seconds) == 1
    assert r.seconds > 0 and r.rtf == pytest.approx(r.seconds / r.audio_s)


def test_errors_are_scored_against_the_reference(tmp_path):
    r = one(tmp_path, "the light is dead", "the lite is dead")
    # light -> lite: g->t and h->e substituted, t deleted = 3 character edits; 1 of 4 words wrong
    assert r.scores["cer"].distance == 3 and r.scores["cer"].ref_len == 17 and r.scores["wer"].distance == 1


def test_long_clips_report_every_chunk(tmp_path):
    write_clip(tmp_path, "en_long", "one two three", seconds=70.0, rate=8000)
    [s], _ = bench.discover(tmp_path)
    r = bench.run_benchmark([s], BenchFake("one", "two", "three"), Settings(_env_file=None))[0]
    assert r.chunks == 3 and len(r.chunk_seconds) == 3 and r.hypothesis == "one two three"


def test_silence_is_scored_as_an_empty_transcript_not_hidden(tmp_path):
    r = one(tmp_path, "hello there", "")
    assert r.error is None and r.note and "no speech" in r.note
    assert r.hypothesis == "" and r.scores["cer"].rate == 1.0


def test_engine_failures_are_reported_and_the_clip_is_not_scored(tmp_path):
    r = one(tmp_path, "hello", SttFailed("The speech model failed to process the audio."))
    assert r.error.startswith("MODEL_UNAVAILABLE") and r.scores is None


def test_unreadable_audio_is_reported_as_a_failure(tmp_path):
    (tmp_path / "en_bad.wav").write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 40)
    (tmp_path / "en_bad.txt").write_text("hello", encoding="utf-8")
    [s], _ = bench.discover(tmp_path)
    r = bench.run_benchmark([s], BenchFake("x"), Settings(_env_file=None))[0]
    assert r.error and r.error.startswith("BAD_INPUT") and r.scores is None


def test_repeat_runs_each_clip_n_times_and_uses_the_median(tmp_path):
    write_clip(tmp_path, "en_r", "hello")
    [s], _ = bench.discover(tmp_path)
    fake = BenchFake("hello")
    r = bench.run_benchmark([s], fake, Settings(_env_file=None), repeat=3)[0]
    assert len(fake.calls) == 3 and len(r.runs) == 3 and r.seconds == sorted(r.runs)[1]


def test_the_benchmark_uses_the_apps_own_pipeline_and_limits(tmp_path):
    write_clip(tmp_path, "en_limit", "hello", seconds=2.0)
    [s], _ = bench.discover(tmp_path)
    r = bench.run_benchmark([s], BenchFake("hello"), Settings(_env_file=None, max_audio_s=1))[0]
    assert r.error and "longer than 1 seconds" in r.error     # the same 400 the endpoint gives


def test_peak_memory_is_attached_to_each_clip(tmp_path):
    write_clip(tmp_path, "en_m", "hello")
    [s], _ = bench.discover(tmp_path)
    readings = iter([{"ws": 100.0}] + [{"ws": 250.0}] * 50)
    sampler = bench.PeakSampler(read=lambda: next(readings, {"ws": 250.0}))
    sampler.start()
    try:
        r = bench.run_benchmark([s], BenchFake("hello"), Settings(_env_file=None), sampler=sampler)[0]
    finally:
        sampler.stop()
    assert r.peak_mb in (100.0, 250.0)


def test_peak_sampler_tracks_the_maximum_and_resets():
    values = iter([10.0, 300.0, 50.0])
    s = bench.PeakSampler(read=lambda: {"ws": next(values, 50.0)})
    s.start()
    time.sleep(0.25)
    s.stop()
    assert s.peak == 300.0
    s.reset()
    assert s.peak == 50.0


def test_process_memory_reports_a_positive_working_set_on_windows():
    m = bench.process_memory()
    assert m is None or (m["ws"] > 0 and m["peak_ws"] >= m["ws"])


# -- aggregation and formatting -------------------------------------------------------------------------
def test_totals_pool_errors_over_all_characters_not_average_the_rates(tmp_path):
    a = one(tmp_path, "abcdefghij", "abcdefghix", name="en_short")            # 1 error / 10 chars
    sub = tmp_path / "b"
    sub.mkdir()
    b = one(sub, "a" * 90, "a" * 80 + "b" * 10, name="en_long")                # 10 errors / 90 chars
    agg = bench.aggregate([a, b])
    assert agg["cer"].distance == 11 and agg["cer"].ref_len == 100 and agg["cer"].rate == pytest.approx(0.11)


def test_clip_report_shows_reference_hypothesis_scores_and_speed(tmp_path):
    r = one(tmp_path, TA_REF, "தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை இல்லை")
    text = "\n".join(bench.format_clip(r))
    for expected in ("ta_a.wav", "reference :", "hypothesis:", TA_REF, "CER", "AER", "WER", "real time", "chunks 1", "word differences"):
        assert expected in text
    assert re.search(r"CER\s+\d+\.\d%", text)


def test_failed_clips_are_flagged_in_the_report(tmp_path):
    r = one(tmp_path, "x", SttFailed("boom"))
    assert "FAILED: MODEL_UNAVAILABLE" in "\n".join(bench.format_clip(r))


def test_summary_is_split_by_language_and_says_it_is_not_a_guarantee(tmp_path):
    ta = one(tmp_path, TA_REF, TA_REF, name="ta_a")
    sub = tmp_path / "e"
    sub.mkdir()
    en = one(sub, "hello world", "hello word", name="en_b")
    text = "\n".join(bench.format_summary([ta, en], 2.5, Path("m"), 5, 4, {"peak_ws": 900.0, "peak_commit": 1400.0}))
    assert "ta: 1 clip(s)" in text and "en: 1 clip(s)" in text and "all: CER" in text
    assert "model load + warm-up" in text and "peak working set 900 MB" in text
    assert "not an accuracy guarantee" in text


# -- command line ----------------------------------------------------------------------------------------
def run_main(args):
    lines = []
    code = bench.main(args, out=lines.append)
    return code, "\n".join(lines)


def test_missing_samples_folder_is_explained_and_nothing_is_created(tmp_path):
    missing = tmp_path / "audio_samples"
    code, out = run_main(["--samples", str(missing)])
    assert code == 2 and "does not exist" in out and not missing.exists()


def test_empty_folder_and_unusable_files_exit_2(tmp_path):
    assert run_main(["--samples", str(tmp_path)])[0] == 2
    (tmp_path / "x.wav").write_bytes(make_wav(0.1))
    code, out = run_main(["--samples", str(tmp_path)])
    assert code == 2 and "skipped: x.wav: no language" in out and "No usable recordings" in out


def test_list_mode_decodes_nothing_and_loads_no_model(tmp_path, fake_engine_factory):
    write_clip(tmp_path, "ta_a", TA_REF)
    code, out = run_main(["--samples", str(tmp_path), "--list"])
    assert code == 0 and "ta_a.wav" in out and "Nothing was decoded and no model was loaded" in out
    assert fake_engine_factory == []


def test_report_must_stay_inside_the_samples_folder(tmp_path):
    folder = tmp_path / "audio_samples"
    folder.mkdir()
    write_clip(folder, "ta_a", TA_REF)
    outside = tmp_path / "report.txt"
    code, out = run_main(["--samples", str(folder), "--report", str(outside)])
    assert code == 2 and "must be inside the samples folder" in out and not outside.exists()


def test_missing_model_folder_stops_before_loading_anything(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "make_engine", lambda d, t, b: bench.stt.WhisperEngine(d, t, b))   # the real class
    write_clip(tmp_path, "ta_a", TA_REF)
    code, out = run_main(["--samples", str(tmp_path), "--model-dir", str(tmp_path / "no-model")])
    assert code == 2 and "Cannot run" in out and "does not exist" in out


def test_a_full_run_warms_up_separately_scores_and_reports(tmp_path, fake_engine_factory):
    folder = tmp_path / "audio_samples"
    folder.mkdir()
    write_clip(folder, "ta_a", TA_REF, seconds=2.0)
    write_clip(folder, "en_b", "hello world", seconds=1.0)
    fake = BenchFake("", TA_REF, "hello word")                 # first call is the warm-up, not a clip
    fake_engine_factory.append(fake)
    code, out = run_main(["--samples", str(folder), "--report", str(folder / "report.txt")])
    assert code == 0
    assert fake.calls[0]["size"] == 16000 and fake.calls[0]["language"] == "en"   # 1 s of silence, first clip's language
    assert len(fake.calls) == 3
    assert "model load + warm-up" in out and "SUMMARY" in out and "clips scored 2 of 2" in out
    assert TA_REF in out and "hello word" in out
    report = (folder / "report.txt").read_text(encoding="utf-8")
    assert report.strip() in out or "SUMMARY" in report and TA_REF in report
    assert sorted(p.name for p in folder.iterdir()) == ["en_b.txt", "en_b.wav", "report.txt", "ta_a.txt", "ta_a.wav"]


def test_nothing_is_written_without_report(tmp_path, fake_engine_factory):
    write_clip(tmp_path, "en_a", "hello")
    fake_engine_factory.append(BenchFake("", "hello"))
    before = sorted(p.name for p in tmp_path.iterdir())
    assert run_main(["--samples", str(tmp_path)])[0] == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_a_model_failure_during_warm_up_is_reported(tmp_path, fake_engine_factory):
    write_clip(tmp_path, "en_a", "hello")
    fake_engine_factory.append(BenchFake(SttFailed("The speech model could not be loaded.")))
    code, out = run_main(["--samples", str(tmp_path)])
    assert code == 1 and "failed to load or run" in out


# -- safety --------------------------------------------------------------------------------------------------
def test_the_script_never_reads_env_and_stays_offline():
    src = SCRIPT.read_text(encoding="utf-8")
    assert src.count("_env_file=None") >= 2                        # every Settings(...) ignores .env (secrets)
    assert not re.search(r"Settings\((?!_env_file=None)", src)
    assert 'os.environ["HF_HUB_OFFLINE"] = "1"' in src
    for banned in ("import httpx", "import requests", "urllib.request", "snapshot_download", "hf_hub_download"):
        assert banned not in src


def test_running_the_benchmark_makes_no_network_request(tmp_path, fake_engine_factory):
    write_clip(tmp_path, "ta_a", TA_REF)
    fake_engine_factory.append(BenchFake("", TA_REF))
    assert run_main(["--samples", str(tmp_path)])[0] == 0
    assert NETWORK_ATTEMPTS == []


def test_a_load_failure_prints_the_real_cause(tmp_path, monkeypatch):
    from backend.services.stt import SttUnavailable
    folder = tmp_path / "audio_samples"
    folder.mkdir()
    write_clip(folder, "ta_a", TA_REF)

    class Broken(BenchFake):
        def transcribe(self, audio, language, deadline):
            raise SttUnavailable("faster-whisper is installed but could not be loaded (ImportError).",
                                 "ImportError: DLL load failed: blocked by policy")

    monkeypatch.setattr(bench, "make_engine", lambda d, t, b: Broken(""))
    code, out = run_main(["--samples", str(folder)])
    assert code == 1 and "could not be loaded (ImportError)" in out
    assert "Cause: ImportError: DLL load failed: blocked by policy" in out
    assert "is not installed" not in out
