"""POST /api/transcribe end to end with a fake engine (no model, no network)."""
import threading
import time
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import BACKEND_DIR, Settings
from backend.main import create_app
from backend.services import stt
from backend.services.stt import SttFailed, SttTimeout, SttUnavailable, WhisperEngine
from .conftest import (NETWORK_ATTEMPTS, TAMIL_SENTENCE, FakeSTTEngine, make_wav, make_webm)


def post(client, data, mime="audio/wav", language="ta", name="clip.wav"):
    return client.post("/api/transcribe", data={"language": language}, files={"audio": (name, data, mime)})


def code(r):
    return r.json()["error"]["code"]


@pytest.fixture
def client_with(settings):
    """Build apps with overridden settings; cleaned up afterwards."""
    opened = []

    def make(**overrides):
        c = TestClient(create_app(settings.model_copy(update=overrides)))
        c.__enter__()
        opened.append(c)
        return c

    yield make
    for c in opened:
        c.__exit__(None, None, None)


# -- success ----------------------------------------------------------------------------------
@pytest.mark.parametrize("language,text", [("ta", TAMIL_SENTENCE), ("en", "The streetlight near the library is broken.")])
def test_valid_audio_returns_exactly_the_documented_shape(client, use_stt, language, text):
    fake = use_stt(text)
    r = post(client, make_wav(1.0), language=language)
    assert r.status_code == 200
    assert r.json() == {"transcript": text, "language": language, "engine": "whisper"}  # PRD p.9, nothing extra
    assert r.headers["cache-control"] == "no-store"
    [call] = fake.calls
    assert call["language"] == language                       # the language asked for, never detected or translated
    assert str(call["dtype"]) == "float32" and call["ndim"] == 1 and abs(call["size"] - 16000) <= 320


def test_the_speakers_words_are_returned_untouched(client, use_stt):
    use_stt("  காந்தி தெருவில்   Gandhi Street \n")
    assert post(client, make_wav(1.0)).json()["transcript"] == "காந்தி தெருவில்   Gandhi Street"  # only outer whitespace trimmed


@pytest.mark.parametrize("data,mime,name", [
    (make_webm(1.0), "audio/webm", "rec.webm"),
    (make_webm(1.0), "video/webm;codecs=opus", "rec.webm"),          # browsers label recordings this way
    (make_wav(1.0, rate=48000, channels=2), "audio/x-wav", "a.wav"),
    (make_wav(1.0, rate=8000), "application/octet-stream", "a.bin"),
], ids=["webm", "webm-video-label", "wav-48k-stereo", "wav-8k-octet-stream"])
def test_supported_formats_all_reach_the_engine_as_16khz_mono(client, use_stt, data, mime, name):
    fake = use_stt("ok")
    assert post(client, data, mime=mime, name=name).status_code == 200
    assert abs(fake.calls[0]["size"] - 16000) <= 800 and fake.calls[0]["ndim"] == 1


def test_long_audio_is_split_into_30_second_chunks_and_joined(client, use_stt):
    fake = use_stt("one", "two", "three")
    r = post(client, make_wav(70.0, rate=8000))                  # 70 s: three chunks
    assert r.status_code == 200 and r.json()["transcript"] == "one two three"
    assert len(fake.calls) == 3 and all(c["size"] <= 30 * 16000 for c in fake.calls)
    assert abs(sum(c["size"] for c in fake.calls) - 70 * 16000) <= 800   # no audio lost between chunks


def test_a_chunk_without_speech_does_not_break_the_others(client, use_stt):
    use_stt("first part", "", "last part")
    assert post(client, make_wav(70.0, rate=8000)).json()["transcript"] == "first part last part"


# -- rejection ----------------------------------------------------------------------------------
BAD = [
    (b"", "audio/wav", "empty"),
    (b"\x00" * 500, "audio/wav", "zeros"),
    (b"just some text", "audio/wav", "text posing as wav"),
    (b"ID3\x04" + b"\x00" * 100, "audio/mpeg", "mp3"),
    (b"OggS" + b"\x00" * 100, "audio/ogg", "ogg"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png", "png"),
    (make_wav(0.5), "image/png", "valid wav declared as png"),
    (make_wav(0.5), "audio/mpeg", "valid wav declared as mp3"),
    (make_wav(0.5)[:30], "audio/wav", "truncated header"),
    (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 40, "audio/wav", "valid header, junk body"),
    (make_webm(0.5)[:150] + b"\x00" * 500, "audio/webm", "corrupt webm"),
]


@pytest.mark.parametrize("data,mime,label", BAD, ids=[b[2] for b in BAD])
def test_bad_uploads_are_a_400_and_never_reach_the_engine(client, use_stt, data, mime, label):
    fake = use_stt("should not be used")
    r = post(client, data, mime=mime)
    assert r.status_code == 400 and code(r) == "BAD_INPUT"
    assert fake.calls == []


def test_missing_or_invalid_form_fields_are_400(client, use_stt):
    use_stt("x")
    assert client.post("/api/transcribe", data={"language": "ta"}).status_code == 400            # no audio
    assert client.post("/api/transcribe", files={"audio": ("a.wav", make_wav(0.5), "audio/wav")}).status_code == 400  # no language
    assert post(client, make_wav(0.5), language="fr").status_code == 400
    assert post(client, make_wav(0.5), language="").status_code == 400


def test_upload_size_limit(client_with):
    c = client_with(max_audio_mb=1)
    c.app.state.stt_engine = FakeSTTEngine("x")
    r = post(c, make_wav(40.0, rate=16000))                      # ~1.28 MB
    assert r.status_code == 400 and "larger than 1 MB" in r.json()["error"]["message"]
    assert c.app.state.stt_engine.calls == []


def test_duration_limit(client_with):
    c = client_with(max_audio_s=1)
    c.app.state.stt_engine = FakeSTTEngine("x")
    r = post(c, make_wav(2.0, rate=8000))
    assert r.status_code == 400 and "longer than 1 seconds" in r.json()["error"]["message"]
    assert c.app.state.stt_engine.calls == []


# -- engine problems -----------------------------------------------------------------------------
@pytest.mark.parametrize("engine", ["gemma", "indic"])
def test_unimplemented_engines_are_503_but_only_after_validation(client_with, engine):
    c = client_with(stt_engine=engine)
    assert c.app.state.stt_engine is None
    assert post(c, b"garbage").status_code == 400                # input problems are reported first
    r = post(c, make_wav(0.5))
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"
    assert "STT_ENGINE=whisper" in r.json()["error"]["message"] and engine in r.json()["error"]["message"]


def test_missing_model_folder_is_503_and_nothing_is_loaded(client):
    engine = client.app.state.stt_engine                         # the real WhisperEngine from settings
    assert isinstance(engine, WhisperEngine) and not engine.loaded
    r = post(client, make_wav(0.5))
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE" and "does not exist" in r.json()["error"]["message"]
    assert not engine.loaded


def test_startup_warns_about_a_missing_model_but_does_not_fail(settings, caplog):
    with caplog.at_level("WARNING", logger="kural"):
        with TestClient(create_app(settings)) as c:
            assert c.get("/api/health").status_code == 200
    assert any("speech model not ready" in r.getMessage() for r in caplog.records)


def test_corrupt_model_files_are_503(client_with, tmp_path):
    d = tmp_path / "corrupt-model"
    d.mkdir()
    for n, content in (("config.json", b"{}"), ("model.bin", b"\x00" * 1024), ("tokenizer.json", b"{}"), ("vocabulary.txt", b"a")):
        (d / n).write_bytes(content)
    c = client_with(stt_model_dir=d)
    r = post(c, make_wav(0.5))
    assert r.status_code == 503 and "could not be loaded" in r.json()["error"]["message"]
    assert NETWORK_ATTEMPTS == []


@pytest.mark.parametrize("error,status,error_code", [
    (SttUnavailable("The speech model could not be loaded."), 503, "MODEL_UNAVAILABLE"),
    (SttFailed("The speech model failed to process the audio."), 503, "MODEL_UNAVAILABLE"),
    (SttTimeout(), 504, "MODEL_TIMEOUT"),
])
def test_engine_errors_map_to_the_documented_codes(client, use_stt, error, status, error_code):
    use_stt(error)
    r = post(client, make_wav(0.5))
    assert (r.status_code, code(r)) == (status, error_code)


def test_the_request_deadline_stops_further_chunks(client_with):
    c = client_with(stt_timeout_s=1)
    fake = FakeSTTEngine("a", "b", "c", delay=1.2)               # the first chunk alone exceeds the 1 s budget
    c.app.state.stt_engine = fake
    r = post(c, make_wav(70.0, rate=8000))
    assert r.status_code == 504 and code(r) == "MODEL_TIMEOUT"
    assert len(fake.calls) == 1                                  # chunks 2 and 3 were never started


@pytest.mark.parametrize("text", ["", "   ", "\n\t"])
def test_silence_or_blank_text_is_a_clear_400(client, use_stt, text):
    use_stt(text)
    r = post(client, make_wav(0.5))
    assert r.status_code == 400 and "No speech" in r.json()["error"]["message"]


# -- resource limits -----------------------------------------------------------------------------
def test_requests_beyond_the_in_flight_limit_get_503_and_slots_are_never_leaked(client, use_stt, monkeypatch):
    monkeypatch.setattr(stt, "_request_slots", threading.BoundedSemaphore(1))
    use_stt("ok")
    assert stt._request_slots.acquire(blocking=False)            # someone else is transcribing
    r = post(client, make_wav(0.5))
    assert r.status_code == 503 and "busy" in r.json()["error"]["message"]
    stt._request_slots.release()
    assert post(client, make_wav(0.5)).status_code == 200        # capacity is back
    for bad in (b"junk", make_wav(0.5)[:30]):                    # failing requests must release their slot
        assert post(client, bad).status_code == 400
    use_stt(SttFailed("x"))
    assert post(client, make_wav(0.5)).status_code == 503
    assert stt._request_slots.acquire(blocking=False)            # still free: no leak
    stt._request_slots.release()


def test_default_capacity_is_one_running_plus_two_waiting():
    assert stt.MAX_CONCURRENT_REQUESTS == 3


# -- privacy ---------------------------------------------------------------------------------------
def test_no_network_no_stored_files_and_no_database_rows(client, use_stt, settings):
    use_stt("private words")
    root = settings.data_dir
    before = sorted(str(p) for p in root.rglob("*"))
    assert post(client, make_wav(2.0)).status_code == 200
    assert NETWORK_ATTEMPTS == []
    assert sorted(str(p) for p in root.rglob("*")) == before     # nothing written (no audio, no transcript)
    with client.app.state.db.connect() as conn:
        assert [conn.execute(f"select count(*) from {t}").fetchone()[0] for t in ("sessions", "drafts", "complaints")] == [0, 0, 0]
    assert not (BACKEND_DIR / "data" / "kural.db").exists()


def test_logs_have_sizes_and_timings_but_never_the_transcript(client, use_stt, caplog):
    secret = "PRIVATE-SENTINEL-பிரியா-14-Gandhi-Street"
    use_stt(secret)
    with caplog.at_level("DEBUG"):
        assert post(client, make_wav(1.0)).status_code == 200
    assert "transcribed" in caplog.text and "chars=" in caplog.text
    assert secret not in caplog.text and "பிரியா" not in caplog.text


def test_large_uploads_that_spill_to_a_temp_file_are_cleaned_up(client, use_stt, tmp_path, monkeypatch):
    """Starlette spools uploads over 1 MB to a temp file. The endpoint must close it."""
    spool = tmp_path / "spool"
    spool.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(spool))
    rollovers = []
    real = tempfile.SpooledTemporaryFile.rollover

    def spy(self):
        rollovers.append(1)
        return real(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", spy)
    use_stt("ok")
    assert post(client, make_wav(60.0, rate=16000)).status_code == 200    # ~1.9 MB: spills to disk
    assert rollovers, "the test upload did not spill to a temp file, so it proves nothing"
    assert list(spool.iterdir()) == []                                      # and it was removed


def test_speech_model_is_not_loaded_by_startup_or_by_rejected_requests(client):
    engine = client.app.state.stt_engine
    assert isinstance(engine, WhisperEngine) and not engine.loaded
    post(client, b"junk")
    post(client, make_wav(0.5), mime="image/png")
    assert not engine.loaded


# -- contract and settings --------------------------------------------------------------------------
def test_the_endpoint_is_registered_with_the_prd_multipart_fields(client):
    spec = client.app.openapi()
    op = spec["paths"]["/api/transcribe"]["post"]
    schema_ref = op["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"].split("/")[-1]
    props = spec["components"]["schemas"][schema_ref]["properties"]
    assert set(props) == {"audio", "language"}
    assert spec["components"]["schemas"]["TranscriptResponse"]["required"] == ["transcript", "language", "engine"]


def test_other_endpoints_are_unaffected(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_defaults_and_resolution_of_the_new_settings():
    s = Settings(_env_file=None)
    assert s.stt_engine == "whisper"
    assert s.stt_model_dir == (BACKEND_DIR / "data" / "models" / "whisper" / "small").resolve()
    assert (s.max_audio_mb, s.max_audio_s, s.stt_timeout_s, s.stt_beam_size, s.stt_cpu_threads) == (10, 300, 120, 5, 0)
    assert s.audio_chunk_s == 30
    for bad in ({"max_audio_mb": 0}, {"max_audio_s": 0}, {"stt_timeout_s": 0}, {"audio_chunk_s": 31}, {"stt_beam_size": 0}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **bad)


def test_env_example_documents_whisper_and_the_new_limits():
    text = (BACKEND_DIR.parent / ".env.example").read_text(encoding="utf-8")
    for line in ("STT_ENGINE=whisper", "STT_MODEL_DIR=", "STT_TIMEOUT_S=", "MAX_AUDIO_MB=", "MAX_AUDIO_S="):
        assert line in text


def test_a_blocked_package_gives_a_generic_503_without_internal_detail(client_with, tmp_path, monkeypatch):
    import builtins
    d = tmp_path / "model"
    d.mkdir()
    for n in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (d / n).write_bytes(b"x")
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "faster_whisper":
            raise ImportError("DLL load failed: C:\\private\\path\\x.pyd blocked")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    c = client_with(stt_model_dir=d)
    r = post(c, make_wav(0.5))
    msg = r.json()["error"]["message"]
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"
    assert "installed but could not be loaded" in msg and "not installed." not in msg
    assert "private" not in msg and "pyd" not in msg
