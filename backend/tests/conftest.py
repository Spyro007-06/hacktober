import io
import json
import shutil
import urllib.request
from datetime import date

import httpx
import httpx2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.config import BACKEND_DIR, Settings
from backend.deps import get_provider_factory
from backend.main import create_app
from backend.models import Extraction
from backend.services.llm import LLMProvider, ProviderStatus

REAL_DATA = BACKEND_DIR / "data"
TODAY = date(2026, 10, 26)


@pytest.fixture
def settings(tmp_path):
    for name in ("departments.json", "rules.json", "portal_fields.json"):
        shutil.copy(REAL_DATA / name, tmp_path / name)
    # _env_file=None: tests must never pick up the developer's real .env (key, model).
    # stt_model_dir points at a folder that does not exist, so no test can ever load
    # the real Whisper model by accident.
    return Settings(_env_file=None, data_dir=tmp_path, model_mode="online",
                    stt_model_dir=tmp_path / "no-speech-model")


NETWORK_ATTEMPTS: list[str] = []  # hosts a test tried to reach (cleared for every test)


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Fail loudly if any test would send a request over the real network.

    Covers every HTTP client in the dependency tree: httpx (Kural itself),
    httpx2 (huggingface_hub) and urllib (WeasyPrint). httpx.MockTransport and
    the in-process TestClient use other classes and are unaffected. (Patching
    socket.connect is NOT enough: asyncio on Windows connects via ConnectEx and
    never calls it.) Attempts are also recorded in NETWORK_ATTEMPTS, because a
    library may swallow the AssertionError."""
    NETWORK_ATTEMPTS.clear()

    def blocked(self, request, *args, **kwargs):
        NETWORK_ATTEMPTS.append(str(request.url.host))
        raise AssertionError(f"test attempted a real network request to {request.url.host!r}")

    async def blocked_async(self, request, *args, **kwargs):
        blocked(self, request)

    for lib in (httpx, httpx2):
        monkeypatch.setattr(lib.HTTPTransport, "handle_request", blocked)
        monkeypatch.setattr(lib.AsyncHTTPTransport, "handle_async_request", blocked_async)

    # WeasyPrint fetches resources through urllib, not httpx: block that too.
    def blocked_urllib(self, req):
        NETWORK_ATTEMPTS.append(str(req.host))
        raise AssertionError(f"test attempted a real network request to {req.host!r}")

    monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", blocked_urllib)
    monkeypatch.setattr(urllib.request.HTTPSHandler, "https_open", blocked_urllib)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


class ScriptedProvider(LLMProvider):
    """Fake provider: returns scripted replies (dict -> JSON, str as-is, an
    Exception is raised). The last reply repeats. Makes no network calls."""

    name = "Fake"

    def __init__(self, *replies):
        self.model = "fake"
        self.replies = list(replies)
        self.calls: list[tuple[str, list]] = []

    async def generate_json(self, prompt, images, schema):
        self.calls.append((prompt, list(images)))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply if isinstance(reply, str) else json.dumps(reply)

    async def check(self):
        return ProviderStatus("Fake", "fake", True, True, "fake")


def extraction_json(**overrides) -> dict:
    """A valid model reply (what a well-behaved model would return)."""
    base = dict(
        category="streetlight", summary_en="The streetlight has not worked.",
        summary_ta="தெருவிளக்கு எரியவில்லை.", location_text="Gandhi Street",
        duration="3 months", severity="medium", photo_findings=[],
        photo_matches_claim=None, photo_mismatch_note=None, wants_records=False,
        user_says_ignored=False, requested_info=[], missing_fields=[],
    )
    base.update(overrides)
    return base


@pytest.fixture
def use_provider(client):
    """Install a ScriptedProvider for the app; returns it."""
    def install(*replies) -> ScriptedProvider:
        fake = ScriptedProvider(*replies)
        client.app.dependency_overrides[get_provider_factory] = lambda: (lambda: fake)
        return fake
    return install


TAMIL_SENTENCE = "தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை."


def make_wav(seconds=1.0, rate=44100, channels=1, freq=440.0, amp=0.3, sampwidth=2) -> bytes:
    """Synthetic WAV (a sine tone). No real speech or personal data."""
    import wave

    t = np.arange(int(seconds * rate)) / rate
    tone = amp * np.sin(2 * np.pi * freq * t)
    if sampwidth == 1:
        frames = (tone * 127 + 128).astype("u1")
    else:
        frames = (tone * 32767).astype("<i2")
    if channels > 1:
        frames = np.repeat(frames[:, None], channels, axis=1).reshape(-1)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        w.writeframes(frames.tobytes())
    return buf.getvalue()


def make_webm(seconds=1.0, freq=440.0) -> bytes:
    """Synthetic WebM/Opus (mono, 48 kHz) encoded in memory with PyAV."""
    import av

    buf = io.BytesIO()
    out = av.open(buf, mode="w", format="webm")
    stream = out.add_stream("libopus", rate=48000)
    stream.layout = "mono"
    n = (int(seconds * 48000) // 960) * 960
    pcm = (0.3 * np.sin(2 * np.pi * freq * (np.arange(n) / 48000)) * 32767).astype("<i2")
    for i in range(0, n, 960):
        frame = av.AudioFrame.from_ndarray(pcm[i:i + 960].reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = 48000
        for pkt in stream.encode(frame):
            out.mux(pkt)
    for pkt in stream.encode(None):
        out.mux(pkt)
    out.close()
    return buf.getvalue()


class FakeSTTEngine:
    """Scripted STT engine: returns the given texts in order (the last repeats); an
    Exception instance is raised. Records every call. Loads no model."""

    name = "whisper"

    def __init__(self, *texts, delay=0.0):
        self.texts = list(texts) or [""]
        self.calls: list[dict] = []
        self.delay = delay

    def transcribe(self, audio, language, deadline):
        self.calls.append({"dtype": audio.dtype, "ndim": audio.ndim, "size": audio.size,
                           "language": language, "deadline": deadline})
        if self.delay:
            import time
            time.sleep(self.delay)
        item = self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def use_stt(client):
    """Install a FakeSTTEngine for the app; returns it."""
    def install(*texts, **kw) -> FakeSTTEngine:
        fake = FakeSTTEngine(*texts, **kw)
        client.app.state.stt_engine = fake
        return fake
    return install


COMPLAINANT = {"name": "R. Priya", "address": "14 Gandhi Street", "phone": "98xxxxxx10"}


def seed_session(client, status="ready", rule_id="R2", ward=None, **extraction_overrides):
    """Store a session directly (no model involved). rule_id picks the route:
    R1/R4 -> rti, R2 -> local_body, R3 -> cm_helpline."""
    from backend.db import new_id
    from backend.models import RouteDecision, Session

    rule = client.app.state.rules.rules[rule_id]
    decision = RouteDecision(route=rule.route, rule_id=rule_id,
                             reason_en=rule.reason_en, reason_ta=rule.reason_ta)
    session = Session(id=new_id("s"), transcript="t", language="ta", status=status,
                      extraction=make_extraction(**extraction_overrides), decision=decision,
                      ward=ward)
    client.app.state.db.save_session(session)
    return session


def draft_body(session_id, **over):
    body = {"session_id": session_id, "complainant": dict(COMPLAINANT), "route_override": None}
    body.update(over)
    return body


def make_image(fmt="PNG", size=(40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "red").save(buf, fmt)
    return buf.getvalue()


def make_extraction(**overrides) -> Extraction:
    base = dict(
        category="streetlight", summary_en="The streetlight is dead.",
        summary_ta="தெருவிளக்கு எரியவில்லை.", location_text="Gandhi Street",
        duration="3 months", severity="medium",
    )
    base.update(overrides)
    return Extraction(**base)
