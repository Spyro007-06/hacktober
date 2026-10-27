"""PUT /api/config/mode, POST /api/tts and /api/complaints (+ escalate).
Fake providers and a fake TTS process only: no network, no model, no real speech."""
import subprocess
from datetime import date, timedelta
from types import SimpleNamespace

import httpx
from pydantic import SecretStr
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.services import tts as tts_service
from backend.services.routing import escalation_decision
from .conftest import NETWORK_ATTEMPTS, draft_body, extraction_json, seed_session
from .test_db import make_complaint


def code(r):
    return r.json()["error"]["code"]


# -- PUT /api/config/mode -------------------------------------------------------------------------
def test_switching_to_an_unconfigured_mode_is_503_and_changes_nothing(client):
    r = client.put("/api/config/mode", json={"mode": "offline"})   # no OLLAMA_MODEL in the test settings
    assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"
    assert client.get("/api/health").json()["model_mode"] == "online"


def ollama(handler):
    return httpx.MockTransport(handler)


def tags(*names):
    return lambda request: httpx.Response(200, json={"models": [{"name": n} for n in names]})


def offline_client(settings, handler):
    s = settings.model_copy(update={"ollama_model": "gemma4:e2b"})
    c = TestClient(create_app(s))
    c.__enter__()
    c.app.state.http_transport = ollama(handler)
    return c


def test_switching_offline_checks_that_ollama_runs_and_has_the_model(settings):
    c = offline_client(settings, tags("gemma4:e2b"))
    try:
        r = c.put("/api/config/mode", json={"mode": "offline"})
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "model_mode": "offline", "model": "gemma4:e2b"}
        assert c.get("/api/health").json()["model_mode"] == "offline"
        assert c.app.state.settings.model_mode == "offline"
    finally:
        c.__exit__(None, None, None)
    assert NETWORK_ATTEMPTS == []


def test_switching_offline_when_ollama_is_not_running_is_503_and_reverts(settings):
    def down(request):
        raise httpx.ConnectError("refused")

    c = offline_client(settings, down)
    try:
        r = c.put("/api/config/mode", json={"mode": "offline"})
        assert r.status_code == 503 and code(r) == "MODEL_UNAVAILABLE"
        assert c.get("/api/health").json()["model_mode"] == "online"
    finally:
        c.__exit__(None, None, None)


def test_switching_offline_when_the_model_is_not_installed_is_503(settings):
    c = offline_client(settings, tags("llama3:8b"))
    try:
        r = c.put("/api/config/mode", json={"mode": "offline"})
        assert r.status_code == 503 and "not installed" in r.json()["error"]["message"]
        assert c.app.state.settings.model_mode == "online"
    finally:
        c.__exit__(None, None, None)


def test_switching_online_makes_no_network_call(settings):
    s = settings.model_copy(update={"model_mode": "offline", "ollama_model": "m",
                                    "gemini_api_key": SecretStr("k"), "gemini_model": "gemma-4-31b-it"})
    with TestClient(create_app(s)) as c:
        calls = []
        c.app.state.http_transport = httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(500))
        r = c.put("/api/config/mode", json={"mode": "online"})
        assert r.status_code == 200 and r.json()["model_mode"] == "online" and calls == []
    assert NETWORK_ATTEMPTS == []


@pytest.mark.parametrize("body", [{"mode": "hybrid"}, {}, {"mode": "online", "extra": 1}, {"mode": None}])
def test_bad_mode_bodies_are_400(client, body):
    assert client.put("/api/config/mode", json=body).status_code == 400


def test_the_switch_is_in_memory_only_and_never_writes_the_env_file(settings, tmp_path):
    env = tmp_path / ".env"
    env.write_text("MODEL_MODE=online\n")
    before = env.read_bytes()
    c = offline_client(settings, tags("gemma4:e2b"))
    try:
        assert c.put("/api/config/mode", json={"mode": "offline"}).status_code == 200
    finally:
        c.__exit__(None, None, None)
    assert env.read_bytes() == before


# -- POST /api/tts ------------------------------------------------------------------------------------
class FakeTts:
    name = "fake"

    def __init__(self, languages=("ta", "en"), audio=b"RIFF\x00\x00\x00\x00WAVEdata" + b"\x00" * 64):
        self.languages, self.audio, self.calls = languages, audio, []

    def supports(self, language):
        return language in self.languages

    def synthesize(self, text, language):
        self.calls.append((text, language))
        return self.audio


def tts(client, text="Submit this complaint to your local body.", language="en"):
    return client.post("/api/tts", json={"text": text, "language": language})


def test_no_engine_configured_is_501_tts_unavailable(client):
    assert client.app.state.tts is None
    r = tts(client)
    assert r.status_code == 501 and code(r) == "TTS_UNAVAILABLE"


def test_audio_is_returned_as_wav_with_privacy_headers(client):
    client.app.state.tts = fake = FakeTts()
    r = tts(client, text="  தெருவிளக்கு   எரியவில்லை  ", language="ta")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.headers["cache-control"] == "no-store" and r.content == fake.audio
    assert fake.calls == [("தெருவிளக்கு எரியவில்லை", "ta")]          # whitespace tidied, text otherwise untouched


def test_a_language_without_a_voice_is_501_not_a_wrong_language_voice(client):
    client.app.state.tts = FakeTts(languages=("ta",))
    assert tts(client, language="en").status_code == 501
    assert tts(client, text="தமிழ்", language="ta").status_code == 200


@pytest.mark.parametrize("body", [
    {"text": "", "language": "en"}, {"text": "   ", "language": "en"},
    {"text": "... ---", "language": "en"}, {"text": "x" * 2000, "language": "en"},
    {"text": "hi", "language": "fr"}, {"text": "hi"}, {"language": "en"},
    {"text": "hi", "language": "en", "voice": "x"},
])
def test_bad_tts_requests_are_400_and_never_reach_the_engine(client, body):
    client.app.state.tts = fake = FakeTts()
    assert client.post("/api/tts", json=body).status_code == 400
    assert fake.calls == []


def test_a_bad_request_is_a_400_even_when_there_is_no_engine(client):
    """Validation comes before the engine check, like /api/transcribe."""
    assert client.post("/api/tts", json={"text": "", "language": "en"}).status_code == 400


def piper(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"x")
    voice = tmp_path / "ta.onnx"
    voice.write_bytes(b"x")
    return tts_service.PiperTts(python, {"ta": voice, "en": None}, 5)


def test_piper_runs_a_fixed_command_without_a_shell_and_feeds_text_on_stdin(tmp_path, monkeypatch):
    seen = {}

    def fake_run(command, **kw):
        seen["command"], seen["kw"] = command, kw
        out = command[command.index("-f") + 1]
        with open(out, "wb") as f:
            f.write(b"RIFF" + b"\x00" * 100)
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(tts_service.subprocess, "run", fake_run)
    text = "தமிழ்; rm -rf / && echo"
    audio = piper(tmp_path).synthesize(text, "ta")
    assert audio.startswith(b"RIFF")
    assert isinstance(seen["command"], list) and not seen["kw"].get("shell")
    assert seen["kw"]["input"] == text.encode("utf-8")                       # the text goes only on stdin
    assert seen["command"][1:4] == ["-I", "-X", "utf8"]                      # UTF-8, so Tamil is not garbled
    assert "தமிழ்" not in " ".join(seen["command"]) and "rm -rf" not in " ".join(seen["command"])


@pytest.mark.parametrize("outcome", ["nonzero", "timeout", "oserror", "no_file"])
def test_piper_failures_are_503_without_leaking_text_or_output(tmp_path, monkeypatch, caplog, outcome):
    def fake_run(command, **kw):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(command, 1)
        if outcome == "oserror":
            raise OSError("C:\\secret\\path")
        return SimpleNamespace(returncode=1 if outcome == "nonzero" else 0, stderr=b"SECRET TEXT")

    monkeypatch.setattr(tts_service.subprocess, "run", fake_run)
    with caplog.at_level("ERROR", logger="kural.tts"):
        with pytest.raises(Exception) as info:
            piper(tmp_path).synthesize("my private complaint", "ta")
    assert info.value.status_code == 503 and "private" not in info.value.message
    log = caplog.text.lower()
    assert "my private complaint" not in log and "secret" not in log


def test_piper_supports_only_languages_with_an_existing_voice_and_python(tmp_path):
    p = piper(tmp_path)
    assert p.supports("ta") and not p.supports("en")
    assert not tts_service.PiperTts(tmp_path / "missing.exe", {"ta": tmp_path / "ta.onnx"}, 5).supports("ta")
    assert not tts_service.PiperTts(None, {"ta": None}, 5).supports("ta")


def test_settings_default_to_no_tts_and_blank_values_mean_unset():
    s = Settings(_env_file=None)
    assert s.tts_engine == "none" and tts_service.build_tts(s) is None
    s = Settings(_env_file=None, tts_engine="", tts_voice_en="", tts_piper_python=" ")
    assert s.tts_engine == "none" and s.tts_voice_en is None and s.tts_piper_python is None


# -- POST /api/complaints ---------------------------------------------------------------------------------
def file_draft(client, rule_id="R2", filed_days_ago=0, **extraction):
    s = seed_session(client, rule_id=rule_id, **extraction)
    d = client.post("/api/drafts", json=draft_body(s.id)).json()
    filed = (date.today() - timedelta(days=filed_days_ago)).isoformat()
    r = client.post("/api/complaints", json={"draft_id": d["draft_id"], "filed_on": filed})
    return s, d, r


def test_filing_saves_the_complaint_with_a_due_date_from_the_department(client):
    s, d, r = file_draft(client)
    assert r.status_code == 200
    c = r.json()
    assert c["draft_id"] == d["draft_id"] and c["route"] == "local_body" and c["category"] == "streetlight"
    assert c["location_text"] == "Gandhi Street" and c["status"] == "filed" and c["parent_complaint_id"] is None
    assert date.fromisoformat(c["due_on"]) == date.fromisoformat(c["filed_on"]) + timedelta(days=d["department"]["response_days"])
    assert client.app.state.db.get_complaint(c["id"]) is not None


def test_filing_the_same_draft_twice_returns_the_same_complaint(client):
    s, d, r = file_draft(client)
    again = client.post("/api/complaints", json={"draft_id": d["draft_id"], "filed_on": date.today().isoformat()})
    assert again.json()["id"] == r.json()["id"] and len(client.app.state.db.list_complaints()) == 1


def test_the_edited_location_is_what_gets_recorded(client):
    s = seed_session(client)
    d = client.post("/api/drafts", json=draft_body(s.id)).json()
    client.patch(f"/api/drafts/{d['draft_id']}", json={"fields": {"location_text": "Nehru Street"}})
    c = client.post("/api/complaints", json={"draft_id": d["draft_id"], "filed_on": date.today().isoformat()}).json()
    assert c["location_text"] == "Nehru Street"


@pytest.mark.parametrize("body,status", [
    ({"draft_id": "d_nope", "filed_on": "2026-01-01"}, 404),
    ({"filed_on": "2026-01-01"}, 400), ({"draft_id": "d_1"}, 400),
    ({"draft_id": "d_1", "filed_on": "01/02/2026"}, 400), ({"draft_id": "d_1", "filed_on": "not a date"}, 400),
    ({"draft_id": "d_1", "filed_on": "2026-01-01", "status": "resolved"}, 400),
])
def test_bad_filing_requests(client, body, status):
    assert client.post("/api/complaints", json=body).status_code == status


def test_a_future_filing_date_is_refused_and_nothing_is_saved(client):
    s = seed_session(client)
    d = client.post("/api/drafts", json=draft_body(s.id)).json()
    r = client.post("/api/complaints", json={"draft_id": d["draft_id"],
                                             "filed_on": (date.today() + timedelta(days=1)).isoformat()})
    assert r.status_code == 400 and client.app.state.db.list_complaints() == []


def test_the_tracker_lists_days_left_and_computes_overdue(client):
    file_draft(client)
    file_draft(client, filed_days_ago=45)
    items = client.get("/api/complaints").json()
    by_status = {i["status"]: i for i in items}
    assert set(by_status) == {"filed", "overdue"}
    assert by_status["filed"]["days_left"] == 30 and by_status["overdue"]["days_left"] == -15
    first = items[0]
    assert {"id", "draft_id", "title", "route", "filed_on", "due_on", "days_left", "status"} <= set(first)
    assert first["title"] == "Streetlight, Gandhi Street" and first["due_date_verified"] is False
    assert client.app.state.db.get_complaint(by_status["overdue"]["id"]).status == "overdue"   # persisted


def test_the_tracker_is_empty_before_anything_is_filed(client):
    assert client.get("/api/complaints").json() == []


def test_a_filed_complaint_feeds_the_routing_history_for_the_next_complaint(client, use_provider):
    file_draft(client, filed_days_ago=45)                       # an overdue streetlight on Gandhi Street
    use_provider(extraction_json())                             # the citizen says nothing about "ignored"
    r = client.post("/api/sessions", data={"text": "The streetlight on Gandhi Street is dead", "language": "en"})
    assert r.json()["decision"]["rule_id"] == "R3" and r.json()["decision"]["route"] == "cm_helpline"


# -- POST /api/complaints/{id}/escalate -------------------------------------------------------------------
def escalate(client, cid):
    return client.post(f"/api/complaints/{cid}/escalate")


def test_a_complaint_that_is_not_overdue_cannot_be_escalated(client):
    s, d, r = file_draft(client)
    e = escalate(client, r.json()["id"])
    assert e.status_code == 400 and "overdue" in e.json()["error"]["message"]
    assert client.app.state.db.get_complaint(r.json()["id"]).status == "filed"


def test_an_unknown_complaint_is_404(client):
    assert escalate(client, "c_nope").status_code == 404


def test_an_overdue_local_body_complaint_escalates_to_the_cm_helpline_level_1(client):
    s, d, r = file_draft(client, filed_days_ago=45)
    cid = r.json()["id"]
    e = escalate(client, cid)
    assert e.status_code == 200
    body = e.json()
    assert body["decision"]["rule_id"] == "R3" and body["route"] == "cm_helpline"
    assert body["decision"]["escalation_level"] == 1
    assert "Gandhi Street" in body["html"] and cid in body["html"]                # the stored facts, not invented ones
    assert body["department"]["id"] == "demo-cm-helpline"
    draft = client.app.state.db.get_draft(body["draft_id"])
    assert draft.parent_complaint_id == cid
    assert client.app.state.db.get_complaint(cid).status != "escalated"           # only filing the draft escalates


def test_filing_the_escalation_draft_links_the_parent_and_marks_it_escalated(client):
    s, d, r = file_draft(client, filed_days_ago=45)
    cid = r.json()["id"]
    esc = escalate(client, cid).json()
    child = client.post("/api/complaints", json={"draft_id": esc["draft_id"], "filed_on": date.today().isoformat()}).json()
    assert child["parent_complaint_id"] == cid and child["route"] == "cm_helpline" and child["escalation_level"] == 1
    assert client.app.state.db.get_complaint(cid).status == "escalated"
    assert escalate(client, cid).status_code == 400                                 # already escalated


def test_the_ladder_climbs_one_level_each_time_and_ends_in_an_rti(client):
    s, d, r = file_draft(client, filed_days_ago=400)                                # local body, long overdue
    cid = r.json()["id"]
    expected = [("R3", 1, "cm_helpline"), ("R3", 2, "cm_helpline"), ("R3", 3, "cm_helpline"), ("R4", 1, "rti")]
    for rule, level, route in expected:
        e = escalate(client, cid)
        assert e.status_code == 200, e.text
        dec = e.json()["decision"]
        assert (dec["rule_id"], dec["escalation_level"], e.json()["route"]) == (rule, level, route)
        child = client.post("/api/complaints", json={"draft_id": e.json()["draft_id"],
                                                     "filed_on": (date.today() - timedelta(days=400)).isoformat()})
        cid = child.json()["id"]
    last = escalate(client, cid)                                                    # an RTI is the end of the ladder
    assert last.status_code == 400 and "RTI" in last.json()["error"]["message"]


def test_rti_escalation_asks_fixed_questions_about_action_taken(client):
    s, d, r = file_draft(client, filed_days_ago=400)
    db = client.app.state.db
    cid = "c_level3"
    db.save_complaint(make_complaint(cid, draft_id=d["draft_id"], route="cm_helpline", escalation_level=3,
                                     filed_on=date.today() - timedelta(days=400),
                                     due_on=date.today() - timedelta(days=370)))
    e = escalate(client, cid).json()
    assert e["decision"]["rule_id"] == "R4" and e["route"] == "rti"
    assert "What action has been taken on my complaint" in e["html"] and cid in e["html"]


def test_an_rti_complaint_cannot_be_escalated(client):
    s, d, r = file_draft(client, rule_id="R1", filed_days_ago=400)
    assert r.json()["route"] == "rti"
    e = escalate(client, r.json()["id"])
    assert e.status_code == 400 and "RTI" in e.json()["error"]["message"]


@pytest.mark.parametrize("route,level,status,expected", [
    ("local_body", 1, "filed", ("R3", 1)), ("cm_helpline", 1, "filed", ("R3", 2)),
    ("cm_helpline", 2, "filed", ("R3", 3)), ("cm_helpline", 3, "filed", ("R4", 1)),
    ("rti", 1, "filed", None), ("local_body", 1, "resolved", None), ("local_body", 1, "escalated", None),
])
def test_the_ladder_rules_in_python(client, route, level, status, expected):
    c = make_complaint(route=route, escalation_level=level, status=status,
                       filed_on=date(2026, 1, 1), due_on=date(2026, 2, 1))
    decision = escalation_decision(c, client.app.state.rules, date(2026, 6, 1))
    assert (None if decision is None else (decision.rule_id, decision.escalation_level)) == expected


def test_a_complaint_not_yet_due_never_escalates_in_python(client):
    c = make_complaint(filed_on=date(2026, 5, 1), due_on=date(2026, 7, 1))
    assert escalation_decision(c, client.app.state.rules, date(2026, 6, 1)) is None


def test_nothing_in_these_endpoints_touches_the_network_or_a_model(client):
    file_draft(client, filed_days_ago=45)
    client.get("/api/complaints")
    assert NETWORK_ATTEMPTS == []
