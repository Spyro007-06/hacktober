"""WhisperEngine tests. faster_whisper is replaced by a stub, so no model is loaded
and the tests check exactly how the engine constructs and calls it. The one real
import (corrupt model files) loads nothing usable and makes no network request."""
import builtins
import os
import sys
import threading
import time
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from backend.services.stt import (REQUIRED_MODEL_FILES, SttFailed, SttTimeout, SttUnavailable,
                                  WhisperEngine)
from .conftest import NETWORK_ATTEMPTS, TAMIL_SENTENCE

AUDIO = np.zeros(16000, dtype=np.float32)


def far():
    return time.monotonic() + 60


@pytest.fixture
def model_dir(tmp_path):
    d = tmp_path / "model"
    d.mkdir()
    for name in (*REQUIRED_MODEL_FILES, "vocabulary.txt"):
        (d / name).write_bytes(b"x")
    return d


class StubModel:
    constructed: list = []
    behaviour = staticmethod(lambda audio, **kw: iter([SimpleNamespace(text=" hello ")]))
    active = 0
    max_active = 0
    calls: list = []

    def __init__(self, path, **kwargs):
        StubModel.constructed.append((path, kwargs))

    def transcribe(self, audio, **kwargs):
        StubModel.calls.append(kwargs)
        StubModel.active += 1
        StubModel.max_active = max(StubModel.max_active, StubModel.active)
        try:
            return StubModel.behaviour(audio, **kwargs), SimpleNamespace(language=kwargs.get("language"))
        finally:
            StubModel.active -= 1


@pytest.fixture
def stub(monkeypatch):
    StubModel.constructed, StubModel.calls = [], []
    StubModel.active = StubModel.max_active = 0
    StubModel.behaviour = staticmethod(lambda audio, **kw: iter([SimpleNamespace(text=" hello ")]))
    module = ModuleType("faster_whisper")
    module.WhisperModel = StubModel
    monkeypatch.setitem(sys.modules, "faster_whisper", module)
    return StubModel


# -- model folder checks -----------------------------------------------------------------------
def test_check_files_accepts_a_complete_folder(model_dir):
    assert WhisperEngine(model_dir).check_files() is None
    (model_dir / "vocabulary.txt").unlink()
    assert "vocabulary" in WhisperEngine(model_dir).check_files()
    (model_dir / "vocabulary.json").write_bytes(b"x")          # large-v3 style folders use .json
    assert WhisperEngine(model_dir).check_files() is None


@pytest.mark.parametrize("missing", REQUIRED_MODEL_FILES)
def test_check_files_names_what_is_missing(model_dir, missing):
    (model_dir / missing).unlink()
    assert missing in WhisperEngine(model_dir).check_files()


def test_missing_folder_is_unavailable(tmp_path):
    e = WhisperEngine(tmp_path / "nope")
    assert "does not exist" in e.check_files()
    with pytest.raises(SttUnavailable, match="does not exist"):
        e.transcribe(AUDIO, "ta", far())
    assert not e.loaded


# -- loading ------------------------------------------------------------------------------------
def test_the_model_is_loaded_lazily_and_only_once(model_dir, stub):
    e = WhisperEngine(model_dir)
    assert stub.constructed == [] and not e.loaded        # constructing the engine loads nothing
    e.transcribe(AUDIO, "ta", far())
    e.transcribe(AUDIO, "en", far())
    e.transcribe(AUDIO, "ta", far())
    assert len(stub.constructed) == 1 and e.loaded        # one copy, reused


def test_the_model_is_loaded_locally_on_the_cpu_with_int8(model_dir, stub, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    WhisperEngine(model_dir, cpu_threads=3).transcribe(AUDIO, "ta", far())
    path, kw = stub.constructed[0]
    assert path == str(model_dir)                          # a local path, never a hub repo id
    assert kw["local_files_only"] is True and kw["device"] == "cpu" and kw["compute_type"] == "int8"
    assert kw["cpu_threads"] == 3 and kw["num_workers"] == 1
    assert os.environ["HF_HUB_OFFLINE"] == "1"             # the hub is switched off before loading


def test_default_thread_count_is_a_sane_automatic_value(model_dir):
    auto = WhisperEngine(model_dir).cpu_threads
    assert 1 <= auto <= 8 and auto == max(1, min(8, (os.cpu_count() or 2) // 2))
    assert WhisperEngine(model_dir, cpu_threads=5).cpu_threads == 5


def test_corrupt_model_files_are_unavailable_not_a_crash_and_make_no_network_request(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    d = tmp_path / "corrupt"
    d.mkdir()
    (d / "config.json").write_text("{}")
    (d / "model.bin").write_bytes(os.urandom(2048))
    (d / "tokenizer.json").write_text("{}")
    (d / "vocabulary.txt").write_text("a")
    e = WhisperEngine(d)
    with pytest.raises(SttUnavailable, match="could not be loaded"):
        e.transcribe(AUDIO, "ta", far())                  # the REAL faster_whisper rejects it
    assert not e.loaded and NETWORK_ATTEMPTS == []
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    with pytest.raises(SttUnavailable):                   # a failed load is retried, not cached
        e.transcribe(AUDIO, "ta", far())


def test_a_missing_package_is_unavailable(model_dir, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # makes `import faster_whisper` fail
    with pytest.raises(SttUnavailable, match="faster-whisper is not installed"):
        WhisperEngine(model_dir).transcribe(AUDIO, "ta", far())


def fail_import(monkeypatch, name, exc):
    """Make `import <name>` raise `exc`, like a missing dependency or a blocked DLL."""
    real = builtins.__import__

    def fake(n, *a, **kw):
        if n == name:
            raise exc
        return real(n, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)


def test_a_blocked_or_broken_package_is_not_reported_as_not_installed(model_dir, monkeypatch, caplog):
    blocked = ImportError("DLL load failed while importing _cyutil: An Application Control policy has blocked this file.")
    fail_import(monkeypatch, "faster_whisper", blocked)
    e = WhisperEngine(model_dir)
    with caplog.at_level("ERROR", logger="kural.stt"):
        with pytest.raises(SttUnavailable) as info:
            e.transcribe(AUDIO, "ta", far())
    assert "not installed" not in str(info.value)
    assert "installed but could not be loaded (ImportError)" in str(info.value)
    assert "Application Control" not in str(info.value)           # the API message stays generic
    assert "Application Control" in info.value.detail             # the real cause is kept for local diagnostics
    assert any("error_type=ImportError" in r.getMessage() for r in caplog.records)
    assert not e.loaded


def test_a_missing_dependency_names_the_dependency_not_faster_whisper(model_dir, monkeypatch):
    fail_import(monkeypatch, "faster_whisper", ModuleNotFoundError("No module named 'av'", name="av"))
    with pytest.raises(SttUnavailable) as info:
        WhisperEngine(model_dir).transcribe(AUDIO, "ta", far())
    assert "'av'" in str(info.value) and "faster-whisper is not installed" not in str(info.value)


# -- how it transcribes --------------------------------------------------------------------------
def test_transcribe_arguments_enforce_the_safety_decisions(model_dir, stub):
    WhisperEngine(model_dir, beam_size=3).transcribe(AUDIO, "ta", far())
    kw = stub.calls[0]
    assert kw["language"] == "ta"                          # fixed: no language detection
    assert kw["task"] == "transcribe"                      # never translate
    assert kw["temperature"] == 0.0 and not isinstance(kw["temperature"], (list, tuple))  # no fallback retries
    assert kw["vad_filter"] is True                        # drop non-speech before decoding
    assert kw["condition_on_previous_text"] is False and kw["beam_size"] == 3


def test_text_is_returned_exactly_as_transcribed(model_dir, stub):
    stub.behaviour = staticmethod(lambda a, **k: iter([SimpleNamespace(text=f" {TAMIL_SENTENCE} "),
                                                       SimpleNamespace(text="near the library")]))
    out = WhisperEngine(model_dir).transcribe(AUDIO, "ta", far())
    assert out == f"{TAMIL_SENTENCE} near the library"


def test_no_segments_means_empty_text(model_dir, stub):
    stub.behaviour = staticmethod(lambda a, **k: iter([]))
    assert WhisperEngine(model_dir).transcribe(AUDIO, "en", far()) == ""


def test_inference_errors_become_stt_failed_and_release_the_lock(model_dir, stub):
    e = WhisperEngine(model_dir)

    def explode(a, **k):
        raise RuntimeError("out of memory while decoding")

    stub.behaviour = staticmethod(explode)
    with pytest.raises(SttFailed, match="failed to process"):
        e.transcribe(AUDIO, "ta", far())
    stub.behaviour = staticmethod(lambda a, **k: iter([SimpleNamespace(text="ok")]))
    assert e.transcribe(AUDIO, "ta", far()) == "ok"        # the lock was released; the engine recovers


def test_errors_raised_while_iterating_segments_are_also_stt_failed(model_dir, stub):
    def gen():
        yield SimpleNamespace(text="first")
        raise ValueError("decoder crashed mid-way")

    stub.behaviour = staticmethod(lambda a, **k: gen())
    with pytest.raises(SttFailed):
        WhisperEngine(model_dir).transcribe(AUDIO, "ta", far())


def test_failure_text_never_leaks_internal_details(model_dir, stub):
    def explode(a, **k):
        raise RuntimeError("secret internal path D:\\private\\thing")

    stub.behaviour = staticmethod(explode)
    with pytest.raises(SttFailed) as e:
        WhisperEngine(model_dir).transcribe(AUDIO, "ta", far())
    assert "private" not in str(e.value)


# -- deadline and concurrency --------------------------------------------------------------------
def test_an_expired_deadline_times_out_before_any_model_work(model_dir, stub):
    e = WhisperEngine(model_dir)
    with pytest.raises(SttTimeout):
        e.transcribe(AUDIO, "ta", time.monotonic() - 1)
    assert stub.constructed == [] and not e.loaded


def test_the_deadline_is_checked_between_segments(model_dir, stub):
    def slow():
        for i in range(5):
            time.sleep(0.15)
            yield SimpleNamespace(text=f"s{i}")

    stub.behaviour = staticmethod(lambda a, **k: slow())
    start = time.monotonic()
    with pytest.raises(SttTimeout):
        WhisperEngine(model_dir).transcribe(AUDIO, "ta", time.monotonic() + 0.3)
    assert time.monotonic() - start < 0.7                  # stopped early, not after all 5 segments


def test_only_one_inference_runs_at_a_time(model_dir, stub):
    def slow(a, **k):
        time.sleep(0.15)
        return iter([SimpleNamespace(text="x")])

    stub.behaviour = staticmethod(slow)
    e = WhisperEngine(model_dir)
    results, errors = [], []

    def work():
        try:
            results.append(e.transcribe(AUDIO, "ta", far()))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    [t.start() for t in threads]
    [t.join(30) for t in threads]
    assert not errors and results == ["x"] * 4
    assert stub.max_active == 1 and len(stub.constructed) == 1   # serialised, and still one model copy


def test_a_waiting_request_times_out_instead_of_waiting_forever(model_dir, stub):
    stub.behaviour = staticmethod(lambda a, **k: (time.sleep(0.6), iter([SimpleNamespace(text="x")]))[1])
    e = WhisperEngine(model_dir)
    t = threading.Thread(target=lambda: e.transcribe(AUDIO, "ta", far()))
    t.start()
    time.sleep(0.15)                                       # let the first request take the lock
    with pytest.raises(SttTimeout):
        e.transcribe(AUDIO, "ta", time.monotonic() + 0.1)
    t.join(10)
