"""POST /api/sessions, /answers and GET with a scripted (fake) provider."""
import io
from datetime import date, timedelta

import pytest
from PIL import Image

from backend.errors import model_timeout, model_unavailable
from backend.models import Session
from .conftest import extraction_json, make_image
from .test_db import make_complaint, make_draft, make_session


def create(client, text="The streetlight on Gandhi Street is dead", language="en", photos=()):
    files = [("photos", (f"{i}.png", b, "image/png")) for i, b in enumerate(photos)]
    return client.post("/api/sessions", data={"text": text, "language": language}, files=files)


def answer(client, sid, **answers):
    return client.post(f"/api/sessions/{sid}/answers", json={"answers": answers})


def count(client, table="sessions"):
    with client.app.state.db.connect() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def err(r):
    return r.json()["error"]["code"]


# -- creation ---------------------------------------------------------------------
def test_create_ready_session_matches_prd_response_shape_and_persists(client, use_provider):
    use_provider(extraction_json())
    r = create(client)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"session_id", "status", "extraction", "decision", "ward",
                         "follow_up_questions", "notice"}
    assert body["status"] == "ready" and body["follow_up_questions"] == []
    assert body["decision"]["rule_id"] == "R2" and body["decision"]["route"] == "local_body"
    assert body["extraction"]["category"] == "streetlight" and body["ward"] is None
    stored = client.get(f"/api/sessions/{body['session_id']}")
    assert stored.status_code == 200
    s = Session.model_validate(stored.json())
    assert s.transcript == "The streetlight on Gandhi Street is dead" and s.language == "en"
    assert s.extraction.location_text == "Gandhi Street" and s.status == "ready"


def test_missing_location_asks_a_follow_up_in_both_languages(client, use_provider):
    use_provider(extraction_json(location_text=None))
    body = create(client).json()
    assert body["status"] == "needs_info"
    [q] = body["follow_up_questions"]
    assert q["field"] == "location_text"
    assert q["question_en"] == "Which street is this on?" and q["question_ta"]
    assert body["extraction"]["missing_fields"] == ["location_text"]
    assert body["decision"] is not None  # PRD p.9 example: decision present while needs_info


def test_duration_omitted_still_proceeds_and_is_not_asked(client, use_provider):
    use_provider(extraction_json(duration=None))
    body = create(client).json()
    assert body["status"] == "ready" and body["follow_up_questions"] == []
    assert body["extraction"]["duration"] is None
    assert body["extraction"]["missing_fields"] == ["duration"]


def test_tamil_language_session(client, use_provider):
    fake = use_provider(extraction_json())
    assert create(client, text="தெருவிளக்கு எரியவில்லை", language="ta").status_code == 200
    assert "Tamil" in fake.calls[0][0]


# -- deterministic routing --------------------------------------------------------
def test_route_comes_from_python_rules_not_the_model(client, use_provider):
    use_provider(extraction_json(user_says_ignored=True))
    d = create(client).json()["decision"]
    assert (d["rule_id"], d["route"]) == ("R3", "cm_helpline")
    assert d["reason_en"].startswith("Your earlier complaint was ignored")  # text from rules.json


def test_model_supplied_route_is_rejected_not_obeyed(client, use_provider):
    fake = use_provider(extraction_json(route="rti"))
    r = create(client)
    assert r.status_code == 422 and err(r) == "MODEL_INVALID_OUTPUT"
    assert len(fake.calls) == 2 and count(client) == 0


def test_history_in_sqlite_feeds_the_rules(client, use_provider):
    db = client.app.state.db
    db.save_session(make_session(id="s_old"))
    db.save_draft(make_draft(session_id="s_old", id="d_old"))
    overdue = make_complaint("c_old", draft_id="d_old", location_text="Gandhi Street",
                             filed_on=date.today() - timedelta(days=60),
                             due_on=date.today() - timedelta(days=5))
    db.save_complaint(overdue)
    use_provider(extraction_json())  # the citizen never said "ignored"
    body = create(client).json()
    assert body["decision"]["rule_id"] == "R3"
    assert client.get(f"/api/sessions/{body['session_id']}").json()["prior_complaint_ids"] == ["c_old"]


def test_not_civic_has_no_decision_and_a_notice(client, use_provider):
    use_provider(extraction_json(category="not_civic"))
    body = create(client).json()
    assert body["status"] == "not_civic" and body["decision"] is None
    assert body["notice"]["en"] and body["notice"]["ta"] and body["follow_up_questions"] == []


def test_wants_records_routes_to_rti(client, use_provider):
    use_provider(extraction_json(wants_records=True, requested_info=["road repair budget"]))
    assert create(client).json()["decision"]["rule_id"] == "R1"


# -- failures never create sessions ----------------------------------------------
@pytest.mark.parametrize("reply,status,code,calls", [
    ("not json", 422, "MODEL_INVALID_OUTPUT", 2),
    (extraction_json(category="potholes"), 422, "MODEL_INVALID_OUTPUT", 2),
    (model_timeout(), 504, "MODEL_TIMEOUT", 1),
    (model_unavailable("down"), 503, "MODEL_UNAVAILABLE", 1),
])
def test_provider_failures_store_nothing(client, use_provider, settings, reply, status, code, calls):
    fake = use_provider(reply)
    r = create(client, photos=[make_image()])
    assert (r.status_code, err(r)) == (status, code)
    assert len(fake.calls) == calls
    assert count(client) == 0 and list(settings.uploads_dir.iterdir()) == []


def test_unconfigured_provider_is_503_after_validation(client):
    assert create(client).status_code == 503                      # no key in the test settings
    assert client.post("/api/sessions", data={"language": "en"}).status_code == 400  # still 400 first


# -- photos -------------------------------------------------------------------------
def test_photo_is_resized_before_the_model_and_original_is_stored(client, use_provider, settings):
    fake = use_provider(extraction_json(photo_findings=["unlit pole"], photo_matches_claim=True))
    big = make_image("PNG", (3000, 2000))
    body = create(client, photos=[big]).json()
    [img] = fake.calls[0][1]
    assert max(Image.open(io.BytesIO(img.data)).size) == 1024 and img.mime_type == "image/jpeg"
    [path] = client.get(f"/api/sessions/{body['session_id']}").json()["photo_paths"]
    assert (settings.uploads_dir / path).read_bytes() == big  # evidence kept at full size
    assert body["extraction"]["photo_findings"] == ["unlit pole"]


def test_no_photo_means_photo_check_is_not_claimed(client, use_provider):
    use_provider(extraction_json(photo_matches_claim=True, photo_findings=["x"]))
    e = create(client).json()["extraction"]
    assert e["photo_matches_claim"] is None and e["photo_findings"] == []


def test_photo_mismatch_status_then_confirm(client, use_provider):
    use_provider(extraction_json(photo_matches_claim=False, photo_findings=["garbage heap"],
                                 photo_mismatch_note="Photo shows garbage, not a streetlight"))
    first = create(client, photos=[make_image()]).json()
    assert first["status"] == "photo_mismatch"
    assert first["extraction"]["photo_mismatch_note"].startswith("Photo shows garbage")
    sid = first["session_id"]
    done = answer(client, sid, photo_mismatch="confirm").json()
    assert done["status"] == "ready"
    stored = Session.model_validate(client.get(f"/api/sessions/{sid}").json())
    assert stored.photo_mismatch_confirmed and stored.answer_rounds == 0
    assert stored.extraction.photo_matches_claim is False  # the mismatch is not erased


def test_mismatch_and_missing_location_are_both_visible(client, use_provider):
    use_provider(extraction_json(location_text=None, photo_matches_claim=False))
    body = create(client, photos=[make_image()]).json()
    assert body["status"] == "photo_mismatch" and len(body["follow_up_questions"]) == 1


def test_photo_mismatch_value_must_be_confirm(client, use_provider):
    use_provider(extraction_json(photo_matches_claim=False))
    sid = create(client, photos=[make_image()]).json()["session_id"]
    assert answer(client, sid, photo_mismatch="yes").status_code == 400


# -- answers ------------------------------------------------------------------------
def test_answer_supplies_location_and_updates_session(client, use_provider):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    use_provider(extraction_json(location_text="somewhere vague", duration="2 months"))
    r = answer(client, sid, location_text="Gandhi Street, near the bus stand")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready" and body["follow_up_questions"] == []
    assert body["extraction"]["location_text"] == "Gandhi Street, near the bus stand"  # citizen's words
    assert body["extraction"]["duration"] == "2 months"
    s = Session.model_validate(client.get(f"/api/sessions/{sid}").json())
    assert s.answer_rounds == 1 and s.answers == {"location_text": "Gandhi Street, near the bus stand"}
    assert s.extraction.location_text == "Gandhi Street, near the bus stand" and s.status == "ready"
    assert s.transcript == "The streetlight on Gandhi Street is dead"  # original text untouched


def test_prd_example_keys_location_and_area_are_accepted(client, use_provider):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    r = answer(client, sid, location="Gandhi Street, near the bus stand", area="Ward 12")
    assert r.status_code == 200
    assert r.json()["extraction"]["location_text"] == "Gandhi Street, near the bus stand, Ward 12"


def test_answer_reruns_extraction_with_the_answers_in_the_prompt(client, use_provider):
    fake = use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    answer(client, sid, location_text="Nehru Road")
    assert "location_text: Nehru Road" in fake.calls[-1][0]


def test_answer_recomputes_route_from_rules(client, use_provider):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    assert client.get(f"/api/sessions/{sid}").json()["decision"]["rule_id"] == "R2"
    use_provider(extraction_json(user_says_ignored=True))
    assert answer(client, sid, location_text="Gandhi Street").json()["decision"]["rule_id"] == "R3"


def test_at_most_two_question_rounds_then_blank_fields_for_the_preview(client, use_provider):
    use_provider(extraction_json(location_text=None))  # the model never learns the location
    sid = create(client).json()["session_id"]
    r1 = answer(client, sid, duration="1 week").json()
    assert r1["status"] == "needs_info"
    r2 = answer(client, sid, duration="2 weeks").json()
    assert r2["status"] == "ready" and r2["follow_up_questions"] == []
    assert r2["extraction"]["location_text"] is None  # left blank, not invented
    assert answer(client, sid, location_text="Gandhi Street").status_code == 400  # no round 3


def test_answers_for_unknown_or_finished_sessions(client, use_provider):
    assert answer(client, "s_nope", location_text="x").status_code == 404
    use_provider(extraction_json())
    sid = create(client).json()["session_id"]
    r = answer(client, sid, location_text="x")
    assert r.status_code == 400 and err(r) == "BAD_INPUT"


@pytest.mark.parametrize("answers", [{"colour": "red"}, {"location_text": "  "},
                                     {"location_text": "x" * 501}])
def test_answer_validation(client, use_provider, answers):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    assert answer(client, sid, **answers).status_code == 400


# -- failed answers leave the session intact ------------------------------------------
@pytest.mark.parametrize("reply,status,code", [
    ("garbage", 422, "MODEL_INVALID_OUTPUT"),
    (model_timeout(), 504, "MODEL_TIMEOUT"),
    (model_unavailable("down"), 503, "MODEL_UNAVAILABLE"),
])
def test_failed_answer_does_not_corrupt_the_session(client, use_provider, reply, status, code):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    before = client.get(f"/api/sessions/{sid}").json()
    use_provider(reply)
    r = answer(client, sid, location_text="Gandhi Street")
    assert (r.status_code, err(r)) == (status, code)
    assert client.get(f"/api/sessions/{sid}").json() == before  # byte-for-byte unchanged
    use_provider(extraction_json())  # and the citizen can simply try again
    assert answer(client, sid, location_text="Gandhi Street").json()["status"] == "ready"


def test_failed_answer_does_not_burn_a_question_round(client, use_provider):
    use_provider(extraction_json(location_text=None))
    sid = create(client).json()["session_id"]
    use_provider(model_timeout())
    answer(client, sid, duration="1 week")
    assert client.get(f"/api/sessions/{sid}").json()["answer_rounds"] == 0


def test_answer_keys_are_documented_values():
    from backend.routers.sessions import ANSWER_KEYS
    assert ANSWER_KEYS == {"location_text", "location", "area", "duration", "photo_mismatch"}
