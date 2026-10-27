"""Provider tests. Every HTTP call goes through httpx.MockTransport: no real
network, no live API key, no Ollama needed."""
import asyncio
import base64
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.config import Settings
from backend.errors import AppError
from backend.main import create_app
from backend.services import llm
from backend.services.llm import (GEMINI_BASE, GeminiProvider, ImagePart, OllamaProvider,
                                  build_provider, is_local_url)
from .conftest import extraction_json, make_image

KEY = "AIza-test-secret-key-123"
SCHEMA = {"type": "object"}
IMG = ImagePart(b"\x89PNGdata", "image/jpeg")


def run(coro):
    return asyncio.run(coro)


def gemini(handler, **kw):
    return GeminiProvider(KEY, "gemma-4-31b-it", kw.pop("timeout_s", 5),
                          httpx.MockTransport(handler))


def ollama(handler, **kw):
    return OllamaProvider("http://localhost:11434", "gemma4:e4b", kw.pop("timeout_s", 5),
                          httpx.MockTransport(handler))


def gemini_reply(text):
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


# -- Gemini ------------------------------------------------------------------
def test_gemini_request_shape_and_reply():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["headers"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return gemini_reply('{"a": 1}')

    out = run(gemini(handler).generate_json("PROMPT", [IMG], SCHEMA))
    assert out == '{"a": 1}'
    assert seen["url"] == f"{GEMINI_BASE}/models/gemma-4-31b-it:generateContent"
    assert KEY not in seen["url"] and seen["headers"]["x-goog-api-key"] == KEY
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[0] == {"text": "PROMPT"}
    assert parts[1]["inline_data"] == {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(IMG.data).decode()}


def sent_body(model, images=()):
    """POST one request through GeminiProvider(model) and return the JSON body sent."""
    seen = {}

    def handler(req: httpx.Request):
        seen["raw"], seen["body"] = req.content.decode(), json.loads(req.content)
        return gemini_reply("{}")

    p = GeminiProvider(KEY, model, 5, httpx.MockTransport(handler))
    run(p.generate_json("PROMPT", list(images), SCHEMA))
    assert KEY not in seen["raw"]  # the key is header-only, never in the body
    return seen["body"]


@pytest.mark.parametrize("model", ["gemma-4-31b-it", "gemma-4-26b-a4b-it", "models/gemma-4-31b-it"])
def test_gemma4_body_matches_googles_documented_minimal_shape(model):
    # Exactly the official single-turn REST body: contents/parts only.
    assert sent_body(model) == {"contents": [{"parts": [{"text": "PROMPT"}]}]}


def test_gemma4_body_has_no_role_temperature_or_generation_config():
    body = sent_body("gemma-4-31b-it", [IMG])
    assert "generationConfig" not in body and "role" not in body["contents"][0]
    assert "temperature" not in json.dumps(body)
    assert len(body["contents"]) == 1


def test_gemma4_images_are_still_sent_as_inline_data():
    parts = sent_body("gemma-4-31b-it", [IMG])["contents"][0]["parts"]
    assert parts[0] == {"text": "PROMPT"}
    assert parts[1]["inline_data"] == {"mime_type": "image/jpeg",
                                       "data": base64.b64encode(IMG.data).decode()}


def test_other_gemini_models_keep_the_existing_request_format():
    assert sent_body("gemini-2.5-flash") == {
        "contents": [{"role": "user", "parts": [{"text": "PROMPT"}]}],
        "generationConfig": {"temperature": 0},
    }


def test_url_and_auth_header_are_unchanged_for_gemma4():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-goog-api-key")
        return gemini_reply("{}")

    run(GeminiProvider(KEY, "gemma-4-31b-it", 5, httpx.MockTransport(handler)).generate_json("x", [], SCHEMA))
    assert seen["url"] == f"{GEMINI_BASE}/models/gemma-4-31b-it:generateContent"
    assert seen["key"] == KEY and KEY not in seen["url"]


def test_gemini_strips_models_prefix_and_skips_thought_parts():
    def handler(req):
        assert "/models/gemma-4-31b-it:" in str(req.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "thinking...", "thought": True}, {"text": '{"ok":'}, {"text": " true}"}]}}]})

    p = GeminiProvider(KEY, "models/gemma-4-31b-it", 5, httpx.MockTransport(handler))
    assert run(p.generate_json("x", [], SCHEMA)) == '{"ok": true}'


def test_gemini_blocked_reply_is_empty_text_not_a_crash():
    p = gemini(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}))
    assert run(p.generate_json("x", [], SCHEMA)) == ""


@pytest.mark.parametrize("status,code,http", [
    (401, "MODEL_UNAVAILABLE", 503), (403, "MODEL_UNAVAILABLE", 503),
    (404, "MODEL_UNAVAILABLE", 503), (429, "MODEL_UNAVAILABLE", 503),
    (500, "MODEL_UNAVAILABLE", 503), (400, "MODEL_UNAVAILABLE", 503),
    (504, "MODEL_TIMEOUT", 504), (408, "MODEL_TIMEOUT", 504),
])
def test_gemini_http_errors_map_to_prd_codes_without_leaking(status, code, http):
    p = gemini(lambda r: httpx.Response(status, text=f"upstream detail {KEY} prompt text"))
    with pytest.raises(AppError) as e:
        run(p.generate_json("x", [], SCHEMA))
    assert (e.value.code, e.value.status_code) == (code, http)
    assert KEY not in e.value.message and "upstream detail" not in e.value.message


def test_gemini_httpx_timeout_is_504():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(AppError) as e:
        run(gemini(handler).generate_json("x", [], SCHEMA))
    assert (e.value.code, e.value.status_code) == ("MODEL_TIMEOUT", 504)


def test_overall_timeout_is_enforced_even_if_transport_hangs():
    async def handler(req):
        await asyncio.sleep(5)
        return gemini_reply("{}")

    with pytest.raises(AppError) as e:
        run(gemini(handler, timeout_s=0.05).generate_json("x", [], SCHEMA))
    assert e.value.code == "MODEL_TIMEOUT"


def test_connection_failure_is_503():
    def handler(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(AppError) as e:
        run(gemini(handler).generate_json("x", [], SCHEMA))
    assert (e.value.code, e.value.status_code) == ("MODEL_UNAVAILABLE", 503)


def test_unreadable_200_body_is_503():
    p = gemini(lambda r: httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(AppError) as e:
        run(p.generate_json("x", [], SCHEMA))
    assert e.value.code == "MODEL_UNAVAILABLE"


def test_gemini_check_ok_and_missing_model():
    ok = run(gemini(lambda r: httpx.Response(200, json={"name": "models/x"})).check())
    assert ok.ok and ok.reachable and ok.model_available
    missing = run(gemini(lambda r: httpx.Response(404)).check())
    assert not missing.ok and missing.reachable and not missing.model_available
    down = run(gemini(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))).check())
    assert not down.reachable


# -- Ollama ------------------------------------------------------------------
def test_ollama_request_shape_and_reply():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": '{"a":1}'}})

    out = run(ollama(handler).generate_json("PROMPT", [IMG], SCHEMA))
    assert out == '{"a":1}'
    assert seen["url"] == "http://localhost:11434/api/chat"
    body = seen["body"]
    assert body["model"] == "gemma4:e4b" and body["stream"] is False and body["format"] == SCHEMA
    assert body["messages"][0]["images"] == [base64.b64encode(IMG.data).decode()]


def test_ollama_ignores_system_proxy_settings():
    assert ollama(lambda r: httpx.Response(200))._trust_env is False


def test_ollama_errors_map_like_gemini():
    def refuse(req):
        raise httpx.ConnectError("refused", request=req)

    with pytest.raises(AppError) as e:
        run(ollama(refuse).generate_json("x", [], SCHEMA))
    assert e.value.code == "MODEL_UNAVAILABLE"
    with pytest.raises(AppError) as e:
        run(ollama(lambda r: httpx.Response(404, json={"error": "model 'x' not found"})
                   ).generate_json("x", [], SCHEMA))
    assert e.value.code == "MODEL_UNAVAILABLE"

    def slow(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(AppError) as e:
        run(ollama(slow).generate_json("x", [], SCHEMA))
    assert e.value.code == "MODEL_TIMEOUT"


def test_ollama_check_model_installed_missing_or_down():
    tags = {"models": [{"name": "gemma4:e4b"}, {"name": "other:latest"}]}
    assert run(ollama(lambda r: httpx.Response(200, json=tags)).check()).ok
    missing = run(ollama(lambda r: httpx.Response(200, json={"models": []})).check())
    assert missing.reachable and not missing.model_available

    def refuse(req):
        raise httpx.ConnectError("refused", request=req)

    assert not run(ollama(refuse).check()).reachable


# -- provider selection ------------------------------------------------------
def mk_settings(**kw):
    return Settings(_env_file=None, **kw)


def test_online_mode_selects_gemini():
    p = build_provider(mk_settings(model_mode="online", gemini_api_key=KEY, gemini_model="gemma-4-31b-it"))
    assert isinstance(p, GeminiProvider) and p.model == "gemma-4-31b-it"


def test_offline_mode_selects_ollama():
    p = build_provider(mk_settings(model_mode="offline", ollama_model="gemma4:e4b"))
    assert isinstance(p, OllamaProvider)


@pytest.mark.parametrize("kw,fragment", [
    (dict(model_mode="online", gemini_model="m"), "GEMINI_API_KEY"),
    (dict(model_mode="online", gemini_api_key="  ", gemini_model="m"), "GEMINI_API_KEY"),
    (dict(model_mode="online", gemini_api_key=KEY), "GEMINI_MODEL"),
    (dict(model_mode="offline"), "OLLAMA_MODEL"),
    (dict(model_mode="offline", ollama_model="m", ollama_url="http://api.example.com:11434"),
     "local machine"),
])
def test_misconfiguration_is_503_with_clear_message(kw, fragment):
    with pytest.raises(AppError) as e:
        build_provider(mk_settings(**kw))
    assert e.value.status_code == 503 and e.value.code == "MODEL_UNAVAILABLE"
    assert fragment in e.value.message and KEY not in e.value.message


def test_no_model_id_is_guessed_or_substituted():
    # Missing GEMINI_MODEL must fail, not fall back to some default id.
    with pytest.raises(AppError):
        build_provider(mk_settings(model_mode="online", gemini_api_key=KEY))


def test_offline_mode_never_constructs_gemini(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Gemini provider must not be used in offline mode")

    monkeypatch.setattr(llm.GeminiProvider, "__init__", boom)
    # Even with a Gemini key present, offline must pick Ollama.
    p = build_provider(mk_settings(model_mode="offline", ollama_model="m", gemini_api_key=KEY,
                                gemini_model="g"))
    assert isinstance(p, OllamaProvider)


def test_online_mode_never_constructs_ollama(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("Ollama provider must not be used in online mode")

    monkeypatch.setattr(llm.OllamaProvider, "__init__", boom)
    p = build_provider(mk_settings(model_mode="online", gemini_api_key=KEY, gemini_model="g",
                                ollama_model="m"))
    assert isinstance(p, GeminiProvider)


@pytest.mark.parametrize("url,expected", [
    ("http://localhost:11434", True), ("http://127.0.0.1:11434", True),
    ("http://[::1]:11434", True), ("http://192.168.1.20:11434", True),
    ("http://10.0.0.5:11434", True), ("http://ollama:11434", True),
    ("http://8.8.8.8:11434", False), ("https://api.example.com", False),
    ("http://generativelanguage.googleapis.com", False), ("ftp://localhost", False),
    ("localhost:11434", False), ("", False),
])
def test_is_local_url(url, expected):
    assert is_local_url(url) is expected


# -- application-level privacy: where do requests actually go? ----------------
class Recorder:
    def __init__(self, reply):
        self.requests: list[httpx.Request] = []
        self.reply = reply

    def __call__(self, req: httpx.Request):
        self.requests.append(req)
        return self.reply(req)


def post_session(client, photo=True):
    files = [("photos", ("a.png", make_image(), "image/png"))] if photo else []
    return client.post("/api/sessions", data={"text": "Street light dead at Gandhi Street",
                                              "language": "en"}, files=files)


def test_offline_app_sends_complaint_only_to_local_ollama(settings):
    rec = Recorder(lambda r: httpx.Response(200, json={"message": {"content": json.dumps(
        extraction_json(photo_matches_claim=True, photo_findings=["unlit pole"]))}}))
    s = settings.model_copy(update={"model_mode": "offline", "ollama_model": "gemma4:e4b",
                                    "gemini_api_key": SecretStr(KEY), "gemini_model": "g"})
    app = create_app(s)
    app.state.http_transport = httpx.MockTransport(rec)
    with TestClient(app) as c:
        r = post_session(c)
    assert r.status_code == 200
    assert rec.requests, "expected a call to the local model"
    assert {(q.url.host, q.url.port) for q in rec.requests} == {("localhost", 11434)}
    assert all("googleapis" not in str(q.url) and "x-goog-api-key" not in q.headers
               for q in rec.requests)
    body = json.loads(rec.requests[0].content)
    assert body["messages"][0]["images"], "photo goes to the local model only"


def test_online_app_sends_to_gemini_only_with_key_in_header(settings):
    rec = Recorder(lambda r: gemini_reply(json.dumps(extraction_json())))
    s = settings.model_copy(update={"model_mode": "online", "gemini_api_key": SecretStr(KEY),
                                    "gemini_model": "gemma-4-31b-it"})
    app = create_app(s)
    app.state.http_transport = httpx.MockTransport(rec)
    with TestClient(app) as c:
        r = post_session(c, photo=False)
    assert r.status_code == 200
    assert {q.url.host for q in rec.requests} == {"generativelanguage.googleapis.com"}
    assert all(KEY not in str(q.url) for q in rec.requests)


def test_offline_app_with_unreachable_ollama_is_503_and_never_tries_gemini(settings):
    seen_hosts = []

    def refuse(req):
        seen_hosts.append(req.url.host)
        raise httpx.ConnectError("refused", request=req)

    s = settings.model_copy(update={"model_mode": "offline", "ollama_model": "m",
                                    "gemini_api_key": SecretStr(KEY), "gemini_model": "g"})
    app = create_app(s)
    app.state.http_transport = httpx.MockTransport(refuse)
    with TestClient(app) as c:
        r = post_session(c, photo=False)
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert set(seen_hosts) == {"localhost"}


def test_secret_never_appears_in_logs_or_error_bodies(settings, caplog):
    s = settings.model_copy(update={"gemini_api_key": SecretStr(KEY), "gemini_model": "g"})
    app = create_app(s)
    app.state.http_transport = httpx.MockTransport(
        lambda r: httpx.Response(401, text=f"bad key {KEY}"))
    with caplog.at_level(logging.DEBUG):
        with TestClient(app) as c:
            r = post_session(c, photo=False)
    assert r.status_code == 503
    assert KEY not in r.text and KEY not in caplog.text
    assert "Gandhi Street" not in caplog.text  # complaint text is never logged

