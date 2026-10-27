"""Pure audio-handling tests: validation, PyAV decoding, limits, chunking. Synthetic
audio only; no model is involved."""
import re
import unicodedata
from pathlib import Path

import numpy as np
import pytest

from backend.errors import AppError
from backend.services import stt
from backend.services.stt import (SAMPLE_RATE, decode_audio_bytes, detect_format, join_transcripts,
                                  split_chunks, validate_upload)
from .conftest import TAMIL_SENTENCE, make_mp4, make_wav, make_webm

MB = 1024 * 1024


def code(exc: AppError) -> tuple:
    return exc.status_code, exc.code


# -- format detection -----------------------------------------------------------------------
def test_wav_and_webm_are_recognised_by_their_headers():
    assert detect_format(make_wav(0.1)) == "wav"
    assert detect_format(make_webm(0.1)) == "webm"


@pytest.mark.parametrize("data", [
    b"ID3\x04\x00\x00" + b"\x00" * 64,                      # mp3
    b"OggS\x00\x02" + b"\x00" * 64,                          # ogg
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,                     # an image
    b"RIFF\x00\x00\x00\x00AVI LIST" + b"\x00" * 32,          # RIFF but not WAVE
    b"\x1a\x45\xdf\xa3\x9f\x42\x82\x88matroska" + b"\x00" * 32,  # EBML but a Matroska video, not WebM
    b"RIFF", b"\x1a\x45\xdf\xa3", b"plain text pretending to be a .wav file" * 4,
    b"http://203.0.113.7/evil.wav", b"C:\\Windows\\win.ini",
])
def test_everything_else_is_rejected(data):
    with pytest.raises(AppError) as e:
        detect_format(data)
    assert code(e.value) == (400, "BAD_INPUT")


# -- upload validation ----------------------------------------------------------------------
def test_empty_upload_is_rejected():
    with pytest.raises(AppError) as e:
        validate_upload(b"", "audio/wav", MB)
    assert code(e.value) == (400, "BAD_INPUT") and "empty" in e.value.message


def test_size_limit_is_enforced_exactly():
    ok = make_wav(0.1)
    assert validate_upload(ok, "audio/wav", len(ok)) == "wav"          # exactly at the limit
    with pytest.raises(AppError) as e:
        validate_upload(ok, "audio/wav", len(ok) - 1)                  # one byte over
    assert "larger than" in e.value.message


@pytest.mark.parametrize("mime", ["", None, "audio/wav", "audio/x-wav", "audio/webm", "video/webm",
                                  "application/octet-stream", "audio/webm;codecs=opus", "AUDIO/WAV",
                                  "audio/mp4", "video/mp4", "audio/x-m4a"])
def test_plausible_declared_types_are_accepted(mime):
    assert validate_upload(make_wav(0.1), mime, MB) == "wav"


@pytest.mark.parametrize("mime", ["image/png", "text/plain", "audio/mpeg", "audio/ogg",
                                  "application/json", "application/pdf"])
def test_unsupported_declared_types_are_rejected_even_for_valid_audio(mime):
    with pytest.raises(AppError) as e:
        validate_upload(make_wav(0.1), mime, MB)
    assert code(e.value) == (400, "BAD_INPUT") and "Unsupported audio type" in e.value.message


# -- decoding --------------------------------------------------------------------------------
def rms(a):
    return float(np.sqrt((a.astype(np.float64) ** 2).mean()))


@pytest.mark.parametrize("kwargs", [
    dict(rate=44100, channels=1), dict(rate=48000, channels=2), dict(rate=8000, channels=1),
    dict(rate=16000, channels=1), dict(rate=22050, channels=1, sampwidth=1),
])
def test_wav_variants_decode_to_16khz_mono_float32(kwargs):
    a = decode_audio_bytes(make_wav(1.0, **kwargs), 10)
    assert a.dtype == np.float32 and a.ndim == 1
    assert abs(a.size - SAMPLE_RATE) <= 320                        # ~1 s at 16 kHz
    assert np.abs(a).max() <= 1.0
    assert 0.15 < rms(a) < 0.27                                    # 0.3-amplitude sine has RMS ~0.21


def test_webm_opus_decodes_to_16khz_mono_float32():
    a = decode_audio_bytes(make_webm(1.0), 10)
    assert a.dtype == np.float32 and a.ndim == 1 and abs(a.size - SAMPLE_RATE) <= 800
    assert 0.1 < rms(a) < 0.3


def test_decoding_preserves_the_tone_frequency():
    a = decode_audio_bytes(make_wav(1.0, freq=1000.0), 10)
    spectrum = np.abs(np.fft.rfft(a))
    peak_hz = np.argmax(spectrum) * SAMPLE_RATE / a.size
    assert abs(peak_hz - 1000.0) < 5


@pytest.mark.parametrize("data", [
    b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\xff" * 40,                  # valid-looking header, junk body
    make_wav(0.5)[:30],                                              # truncated inside the header
    b"RIFF\xff\xff\xff\xffWAVE" + b"\x00" * 20,                      # nonsense sizes
    make_webm(0.5)[:200] + b"\x00" * 600,                            # corrupted WebM
    b"\x1a\x45\xdf\xa3webm" + b"\xaa" * 300,                         # EBML magic then noise
])
def test_corrupt_audio_is_a_400_never_a_crash(data):
    with pytest.raises(AppError) as e:
        decode_audio_bytes(data, 10)
    assert code(e.value) == (400, "BAD_INPUT")


def test_a_wav_with_no_samples_is_rejected():
    with pytest.raises(AppError) as e:
        decode_audio_bytes(make_wav(0.0), 10)
    assert code(e.value) == (400, "BAD_INPUT")


def test_duration_limit_is_enforced():
    with pytest.raises(AppError) as e:
        decode_audio_bytes(make_wav(3.0, rate=8000), 1)
    assert code(e.value) == (400, "BAD_INPUT") and "longer than 1 seconds" in e.value.message
    assert decode_audio_bytes(make_wav(1.0, rate=8000), 1.5).size > 0


def test_decoder_aborts_early_on_over_long_audio_instead_of_decoding_everything(monkeypatch):
    """A tiny file can hold very long audio; decoding must stop at the limit."""
    import av
    produced = []
    real_resample = av.AudioResampler.resample

    def counting(self, frame):
        out = real_resample(self, frame)
        produced.extend(out)
        return out

    monkeypatch.setattr(av.AudioResampler, "resample", counting)
    with pytest.raises(AppError):
        decode_audio_bytes(make_wav(30.0, rate=8000), 2)
    assert sum(f.samples for f in produced) < 16000 * 6  # far less than the 30 s file


def test_the_decoder_never_uses_faster_whispers_broken_helper_or_a_path():
    src = Path(stt.__file__).read_text(encoding="utf-8")
    assert "from faster_whisper.audio" not in src and not re.search(r"\bdecode_audio\(", src)
    assert "av.open(io.BytesIO(" in src            # always an in-memory buffer, never a path/URL


# -- chunking ----------------------------------------------------------------------------------
def tone(seconds, rate=SAMPLE_RATE):
    return (0.3 * np.sin(2 * np.pi * 220 * np.arange(int(seconds * rate)) / rate)).astype(np.float32)


@pytest.mark.parametrize("seconds,expected", [(0.5, 1), (29.9, 1), (30.0, 1), (30.1, 2), (59.9, 2), (95.0, 4)])
def test_chunk_counts_follow_the_30_second_rule(seconds, expected):
    chunks = split_chunks(tone(seconds), 30)
    assert len(chunks) == expected


@pytest.mark.parametrize("seconds", [30.1, 61.0, 95.0, 299.0])
def test_chunks_are_never_longer_than_the_limit_never_empty_and_lose_nothing(seconds):
    audio = np.random.default_rng(1).standard_normal(int(seconds * SAMPLE_RATE)).astype(np.float32) * 0.1
    chunks = split_chunks(audio, 30)
    assert all(0 < c.size <= 30 * SAMPLE_RATE for c in chunks)
    assert np.array_equal(np.concatenate(chunks), audio)          # concatenation == original


def test_cuts_land_in_silence_so_words_are_not_split():
    audio = tone(70)
    gap_start = int(28.5 * SAMPLE_RATE)
    audio[gap_start:gap_start + int(0.2 * SAMPLE_RATE)] = 0.0      # a 200 ms pause at 28.5 s
    first = split_chunks(audio, 30)[0]
    assert 28.5 <= first.size / SAMPLE_RATE <= 28.7               # cut inside the pause, not at 30 s


def test_the_search_window_is_bounded_so_chunks_stay_near_the_limit():
    audio = tone(70)
    audio[int(5 * SAMPLE_RATE):int(5.5 * SAMPLE_RATE)] = 0.0      # silence far from any limit: ignored
    first = split_chunks(audio, 30)[0]
    assert first.size / SAMPLE_RATE > 15


def test_custom_chunk_length_is_respected():
    chunks = split_chunks(tone(25), 10)
    assert len(chunks) == 3 and all(c.size <= 10 * SAMPLE_RATE for c in chunks)


# -- joining ---------------------------------------------------------------------------------
def test_join_spaces_parts_and_drops_empty_ones():
    assert join_transcripts([" one ", "", "  ", "two\n", None]) == "one two"
    assert join_transcripts([]) == "" and join_transcripts(["", " "]) == ""


def test_join_leaves_tamil_and_mixed_text_untouched():
    parts = [unicodedata.normalize("NFC", TAMIL_SENTENCE), "Gandhi Street near the library"]
    out = join_transcripts(parts)
    assert out == f"{TAMIL_SENTENCE} Gandhi Street near the library"
    assert unicodedata.normalize("NFC", out) == out


# -- decoder import failures --------------------------------------------------------------------
def test_a_blocked_decoder_is_reported_as_blocked_not_missing(monkeypatch, caplog):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "av":
            raise ImportError("DLL load failed while importing _cyutil: blocked by policy")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    with caplog.at_level("ERROR", logger="kural.stt"):
        with pytest.raises(AppError) as info:
            decode_audio_bytes(make_wav(0.2), 10)
    assert code(info.value) == (503, "MODEL_UNAVAILABLE")
    assert "installed but could not be loaded (ImportError)" in info.value.message
    assert "blocked by policy" not in info.value.message             # no internal detail in the API message
    assert any("error_type=ImportError" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("exc,expected", [
    (ModuleNotFoundError("No module named 'av'", name="av"), "is not installed."),
    (ModuleNotFoundError("No module named 'x'", name="x.y"), "needs the package 'x'"),
    (ImportError("DLL load failed"), "installed but could not be loaded (ImportError)"),
    (OSError("cannot open shared object"), "installed but could not be loaded (OSError)"),
])
def test_import_failures_are_described_by_their_real_cause(exc, expected):
    message, detail = stt.describe_import_failure(exc, "av", "PyAV")
    assert expected in message and detail.startswith(type(exc).__name__)


def test_diagnostic_detail_is_short_and_has_no_file_system_paths():
    long_tail = "x" * 500
    exc = ImportError("DLL load failed while importing _cyutil: blocked "
                      + r"C:\Users\someone\proj\.venv\av\_cyutil.pyd and /home/someone/proj/av.so "
                      + r"and \\server\share\a.dll " + long_tail)
    _message, detail = stt.describe_import_failure(exc, "av", "PyAV")
    assert "someone" not in detail and "Users" not in detail and "/home" not in detail and "server" not in detail
    assert "<path>" in detail and "blocked" in detail          # the cause stays readable
    assert len(detail) <= len("ImportError: ") + 200
    assert "\n" not in detail


# -- MP4 / M4A (Safari and iOS record this; the frontend sends it with a .mp4 name) -----------------
def test_mp4_is_recognised_by_its_header_not_its_name_or_type():
    data = make_mp4(0.3)
    assert detect_format(data) == "mp4"
    assert validate_upload(data, "audio/mp4", MB) == "mp4" and validate_upload(data, None, MB) == "mp4"


def test_mp4_aac_decodes_to_16khz_mono_float32():
    a = decode_audio_bytes(make_mp4(1.0), 10)
    assert a.dtype == np.float32 and a.ndim == 1 and abs(a.size - SAMPLE_RATE) <= 1500
    assert 0.15 < rms(a) < 0.27


@pytest.mark.parametrize("cut", [30, 200, 0.5])
def test_truncated_or_garbled_mp4_is_a_clean_400_not_a_crash(cut):
    data = make_mp4(0.5)
    broken = data[:int(len(data) * cut)] if isinstance(cut, float) else data[:cut]
    with pytest.raises(AppError) as e:
        decode_audio_bytes(broken, 10)
    assert code(e.value) == (400, "BAD_INPUT")


def test_the_container_is_chosen_by_the_header_so_a_mislabelled_stream_is_not_probed_as_something_else():
    """RIFF/WAVE header, but the body is not WAV: FFmpeg must not fall back to another demuxer."""
    with pytest.raises(AppError) as e:
        decode_audio_bytes(b"RIFF\x00\x00\x00\x00WAVE" + make_mp4(0.2), 10)
    assert code(e.value) == (400, "BAD_INPUT")
