"""The shapes and behaviours the frontend relies on (docs/frontend-requirements.pdf section 6 and
docs/frontend-requirements.md), checked against the backend. Fakes only: no network, no model."""
from datetime import date, timedelta

import pytest

from backend.models import Session
from .conftest import (draft_body, extraction_json, make_image, make_mp4, make_wav, make_webm,
                       seed_session)

EDITABLE = {"summary_en", "summary_ta", "location_text", "duration", "requested_info"}


def create(client, text="The streetlight on Gandhi Street is dead", language="en", photos=()):
    files = [("photos", (f"{i}.png", b, "image/png")) for i, b in enumerate(photos)]
    return client.post("/api/sessions", data={"text": text, "language": language}, files=files)


def answers(client, sid, **body):
    return client.post(f"/api/sessions/{sid}/answers", json=body)


# -- GET /api/sessions/{id}: "same shape as POST /api/sessions" ---------------------------------------
def test_get_session_has_the_post_response_fields_so_a_refresh_can_recover(client, use_provider):
    use_provider(extraction_json(location_text=None))
    first = create(client).json()
    got = client.get(f"/api/sessions/{first['session_id']}").json()
    for key in ("session_id", "status", "extraction", "decision", "ward", "follow_up_questions", "notice"):
        assert key in got
    assert got["session_id"] == first["session_id"] and got["status"] == first["status"]
    assert got["follow_up_questions"] == first["follow_up_questions"] and got["extraction"] == first["extraction"]
    Session.model_validate(got)                                       # and it is still a full stored session


def test_get_session_carries_the_not_civic_notice(client, use_provider):
    use_provider(extraction_json(category="not_civic", location_text=None))
    sid = create(client, "My landlord keeps my deposit").json()["session_id"]
    got = client.get(f"/api/sessions/{sid}").json()
    assert got["status"] == "not_civic" and got["notice"]["en"] and got["notice"]["ta"]


# -- POST /api/sessions/{id}/answers: {"answers": {...}, "confirm_photo_mismatch": bool} ------------------
def test_confirm_photo_mismatch_flag_confirms_the_photo(client, use_provider):
    use_provider(extraction_json(photo_matches_claim=False, photo_findings=["garbage"], photo_mismatch_note="n"))
    sid = create(client, photos=[make_image()]).json()["session_id"]
    r = answers(client, sid, answers={}, confirm_photo_mismatch=True)       # exactly what client.js sends
    assert r.status_code == 200 and r.json()["status"] == "ready"
    stored = client.app.state.db.get_session(sid)
    assert stored.photo_mismatch_confirmed and stored.answer_rounds == 0   # confirming is not a question round


def test_the_flag_false_does_not_confirm(client, use_provider):
    use_provider(extraction_json(photo_matches_claim=False, photo_findings=["garbage"], photo_mismatch_note="n"))
    sid = create(client, photos=[make_image()]).json()["session_id"]
    r = answers(client, sid, answers={}, confirm_photo_mismatch=False)
    assert r.status_code == 200 and r.json()["status"] == "photo_mismatch"


def test_answering_with_the_frontend_body_shape_works(client, use_provider):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    use_provider(extraction_json(location_text="Gandhi Street, near the bus stand"))
    r = answers(client, sid, answers={"location_text": "Gandhi Street, near the bus stand"},
                confirm_photo_mismatch=False)
    assert r.status_code == 200 and r.json()["status"] == "ready"


def test_skipping_a_question_counts_as_a_round_and_makes_no_model_call(client, use_provider):
    fake = use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    calls = len(fake.calls)
    first = answers(client, sid, answers={}, confirm_photo_mismatch=False)
    assert first.status_code == 200 and first.json()["status"] == "needs_info"       # round 1: still asking
    second = answers(client, sid, answers={}, confirm_photo_mismatch=False)
    assert second.status_code == 200 and second.json()["status"] == "ready"          # after 2 rounds it continues
    assert second.json()["extraction"]["location_text"] is None                       # nothing was invented
    assert len(fake.calls) == calls                                                    # no extra model calls
    assert client.app.state.db.get_session(sid).answer_rounds == 2


@pytest.mark.parametrize("body", [{}, {"confirm_photo_mismatch": True},
                                  {"answers": {}, "confirm": True}, {"answers": {"location_text": "x"}, "extra": 1}])
def test_malformed_answer_bodies_are_400(client, use_provider, body):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    assert answers(client, sid, **body).status_code == 400


# -- drafts: editable_fields and requested_info -----------------------------------------------------------
def make_draft(client, rule_id="R2", **extraction):
    s = seed_session(client, rule_id=rule_id, **extraction)
    return s, client.post("/api/drafts", json=draft_body(s.id)).json()


def test_every_draft_response_carries_editable_fields(client):
    s, d = make_draft(client, duration=None)
    assert set(d["editable_fields"]) == EDITABLE
    assert d["editable_fields"]["summary_en"] == "The streetlight is dead."
    assert d["editable_fields"]["location_text"] == "Gandhi Street"
    assert d["editable_fields"]["duration"] == "" and d["editable_fields"]["requested_info"] == []   # null -> ""
    patched = client.patch(f"/api/drafts/{d['draft_id']}", json={"fields": {"summary_en": "Edited text"}}).json()
    assert patched["editable_fields"]["summary_en"] == "Edited text"
    assert patched["editable_fields"]["location_text"] == "Gandhi Street"


def test_requested_info_is_editable_as_a_list_and_appears_in_the_document(client):
    s, d = make_draft(client, rule_id="R1", wants_records=True, requested_info=["Road works records"])
    assert d["editable_fields"]["requested_info"] == ["Road works records"]
    r = client.patch(f"/api/drafts/{d['draft_id']}",
                     json={"fields": {"requested_info": ["  Who approved the work?  ", "", "   ", "When was it done?"]}})
    assert r.status_code == 200
    body = r.json()
    assert body["editable_fields"]["requested_info"] == ["Who approved the work?", "When was it done?"]
    assert "Who approved the work?" in body["html"] and "Road works records" not in body["html"]


def test_requested_info_can_be_cleared(client):
    s, d = make_draft(client, rule_id="R1", wants_records=True, requested_info=["x"])
    r = client.patch(f"/api/drafts/{d['draft_id']}", json={"fields": {"requested_info": []}})
    assert r.status_code == 200 and r.json()["editable_fields"]["requested_info"] == []


@pytest.mark.parametrize("fields", [
    {"requested_info": "one string"}, {"summary_en": ["a list"]}, {"requested_info": ["x" * 501]},
    {"requested_info": [f"q{i}" for i in range(21)]}, {"route": "rti"}, {"department": "x"},
])
def test_bad_edits_are_400_and_change_nothing(client, fields):
    s, d = make_draft(client)
    before = client.app.state.db.get_draft(d["draft_id"])
    assert client.patch(f"/api/drafts/{d['draft_id']}", json={"fields": fields}).status_code == 400
    assert client.app.state.db.get_draft(d["draft_id"]) == before


def test_the_escalation_draft_also_has_editable_fields(client):
    s, d = make_draft(client)
    filed = (date.today() - timedelta(days=45)).isoformat()
    c = client.post("/api/complaints", json={"draft_id": d["draft_id"], "filed_on": filed}).json()
    e = client.post(f"/api/complaints/{c['id']}/escalate").json()
    assert set(e["editable_fields"]) == EDITABLE and c["id"] in e["editable_fields"]["summary_en"]


# -- GET /api/complaints: "overdue first, then days_left ascending" -------------------------------------
def test_the_tracker_sorts_overdue_first_then_by_days_left(client):
    def file(days_ago):
        s, d = make_draft(client)
        client.post("/api/complaints", json={"draft_id": d["draft_id"],
                                             "filed_on": (date.today() - timedelta(days=days_ago)).isoformat()})
    for ago in (5, 40, 20, 100):       # days left 25, -10, 10, -70
        file(ago)
    items = client.get("/api/complaints").json()
    assert [i["status"] for i in items] == ["overdue", "overdue", "filed", "filed"]
    assert [i["days_left"] for i in items] == [-70, -10, 10, 25]


# -- POST /api/transcribe: the frontend records webm, or mp4 where webm is unsupported ---------------------
@pytest.mark.parametrize("data,mime,name", [
    (make_webm(0.5), "audio/webm", "clip.webm"), (make_mp4(0.5), "audio/mp4", "clip.mp4"),
    (make_wav(0.5), "audio/wav", "clip.wav"),
], ids=["webm", "mp4", "wav"])  # explicit ids: raw audio bytes as ids overflow pytest's env var
def test_every_recording_type_the_frontend_can_send_is_accepted(client, use_stt, data, mime, name):
    use_stt("hello")
    r = client.post("/api/transcribe", data={"language": "en"}, files={"audio": (name, data, mime)})
    assert r.status_code == 200 and r.json()["transcript"] == "hello"
