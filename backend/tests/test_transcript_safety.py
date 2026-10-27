"""Speech -> transcript -> confirmation -> extraction -> deterministic route.

A speech transcript can be wrong (Tamil especially), and wrong words can change the
category or the route. These tests pin the safeguards: failures are not complaints,
an unconfirmed transcript is never extracted, an unsupported location becomes a
question, and the model can never choose the route. Fake STT engine and fake
provider only: no model is loaded and no network is used.
"""
import pytest

from backend.services.stt import SttFailed, SttUnavailable
from .conftest import NETWORK_ATTEMPTS, TAMIL_SENTENCE, extraction_json, make_wav


def transcribe(client, language="ta"):
    return client.post("/api/transcribe", data={"language": language},
                       files={"audio": ("clip.wav", make_wav(0.5), "audio/wav")})


def create(client, text, language="ta", **form):
    return client.post("/api/sessions", data={"text": text, "language": language, **form})


def rows(client, table="sessions"):
    with client.app.state.db.connect() as c:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# -- failures are not complaints ------------------------------------------------------------------
@pytest.mark.parametrize("error", [SttUnavailable("The speech model could not be loaded."),
                                   SttFailed("The speech model failed to process the audio.")])
def test_an_stt_failure_is_an_error_not_a_non_civic_complaint(client, use_stt, use_provider, error):
    use_stt(error)
    fake = use_provider(extraction_json(category="not_civic"))
    r = transcribe(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "MODEL_UNAVAILABLE"
    assert "transcript" not in r.json() and "not_civic" not in r.text
    assert fake.calls == [] and rows(client) == 0          # nothing was extracted or stored


def test_silence_is_a_clear_error_not_an_empty_complaint(client, use_stt, use_provider):
    use_stt("   ")
    fake = use_provider(extraction_json())
    r = transcribe(client)
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_INPUT"
    assert fake.calls == [] and rows(client) == 0


@pytest.mark.parametrize("text", ["", "   ", ".", "... ---", "?!", "​"])
def test_text_without_readable_words_never_reaches_the_model(client, use_provider, text):
    fake = use_provider(extraction_json(category="not_civic"))
    r = create(client, text, input_source="speech", transcript_confirmed="true")
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_INPUT"
    assert fake.calls == [] and rows(client) == 0


def test_a_genuine_non_civic_complaint_is_still_not_civic_with_a_notice(client, use_provider):
    use_provider(extraction_json(category="not_civic", location_text=None))
    body = create(client, "My landlord keeps my deposit", language="en").json()
    assert body["status"] == "not_civic" and body["decision"] is None
    assert body["notice"]["en"] and body["notice"]["ta"] and body["follow_up_questions"] == []


# -- the citizen must confirm a spoken transcript ---------------------------------------------------
def test_an_unconfirmed_speech_transcript_is_not_extracted_or_stored(client, use_provider):
    fake = use_provider(extraction_json())
    for extra in ({}, {"transcript_confirmed": "false"}):
        r = create(client, TAMIL_SENTENCE, input_source="speech", **extra)
        assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_INPUT"
        assert "confirm" in r.json()["error"]["message"]
    assert fake.calls == [] and rows(client) == 0 and NETWORK_ATTEMPTS == []


def test_a_confirmed_speech_transcript_proceeds_and_routes_by_rule(client, use_provider):
    use_provider(extraction_json(location_text="காந்தி தெரு"))
    r = create(client, "தெருவிளக்கு காந்தி தெரு எரியவில்லை", input_source="speech",
               transcript_confirmed="true")
    assert r.status_code == 200
    assert r.json()["decision"]["rule_id"] == "R2" and r.json()["status"] == "ready"


def test_typed_text_needs_no_confirmation_so_existing_clients_still_work(client, use_provider):
    use_provider(extraction_json())
    assert create(client, "The streetlight on Gandhi Street is dead", language="en").status_code == 200


def test_bad_input_source_is_rejected(client, use_provider):
    use_provider(extraction_json())
    assert create(client, "x y", input_source="telepathy").status_code == 400


def test_the_corrected_transcript_is_what_is_stored_and_extracted(client, use_stt, use_provider):
    use_stt("எங்கள் திருவில் உள்ள திருவிலக்கு எரியவில்லை")            # what the recogniser heard
    heard = transcribe(client).json()["transcript"]
    corrected = "எங்கள் தெருவில் உள்ள தெருவிளக்கு எரியவில்லை"          # what the citizen fixed it to
    fake = use_provider(extraction_json(location_text=None))
    r = create(client, corrected, input_source="speech", transcript_confirmed="true")
    assert r.status_code == 200
    stored = client.get(f"/api/sessions/{r.json()['session_id']}").json()
    assert stored["transcript"] == corrected and stored["transcript"] != heard
    assert corrected in fake.calls[0][0] and heard not in fake.calls[0][0]


# -- unsupported facts become questions, never silent values ------------------------------------------
def test_a_location_the_citizen_never_said_becomes_a_question_not_a_fact(client, use_provider):
    use_provider(extraction_json(location_text="Anna Nagar"))     # the model "knew" a place
    body = create(client, "The streetlight is dead", language="en").json()
    assert body["status"] == "needs_info"
    assert body["extraction"]["location_text"] is None
    assert [q["field"] for q in body["follow_up_questions"]] == ["location_text"]
    assert body["decision"]["rule_id"] == "R2"             # no phantom match with an earlier complaint


def test_an_ungrounded_location_cannot_pull_in_an_earlier_complaint(client, use_provider):
    """An invented location must not match history and push the route to R3."""
    from datetime import date, timedelta
    from .test_db import make_complaint, make_draft, make_session
    use_provider(extraction_json(location_text="Anna Nagar"))
    db = client.app.state.db
    db.save_session(make_session(id="s_old"))
    db.save_draft(make_draft(session_id="s_old", id="d_old"))
    db.save_complaint(make_complaint("c_old", draft_id="d_old", location_text="Anna Nagar",
                                     filed_on=date.today() - timedelta(days=60),
                                     due_on=date.today() - timedelta(days=5)))
    body = create(client, "The streetlight is dead", language="en").json()
    assert body["decision"]["rule_id"] == "R2" and body["extraction"]["location_text"] is None


# -- the model can never choose or override the route -------------------------------------------------
@pytest.mark.parametrize("field", ["route", "rule_id", "department", "decision"])
def test_a_model_reply_that_names_a_route_is_rejected_not_obeyed(client, use_provider, field):
    fake = use_provider(extraction_json(**{field: "rti"}))
    r = create(client, "The streetlight on Gandhi Street is dead", language="en")
    assert r.status_code == 422 and r.json()["error"]["code"] == "MODEL_INVALID_OUTPUT"
    assert len(fake.calls) == 2 and rows(client) == 0       # one corrective retry, then refused


def test_the_route_comes_only_from_the_extracted_facts_through_the_rules(client, use_provider):
    use_provider(extraction_json(wants_records=True))
    assert create(client, "Give me the road works records of Gandhi Street",
                  language="en").json()["decision"]["rule_id"] == "R1"
    use_provider(extraction_json(user_says_ignored=True))
    assert create(client, "I complained on Gandhi Street and nothing happened",
                  language="en").json()["decision"]["rule_id"] == "R3"
    use_provider(extraction_json())
    assert create(client, "The streetlight on Gandhi Street is dead",
                  language="en").json()["decision"]["rule_id"] == "R2"
