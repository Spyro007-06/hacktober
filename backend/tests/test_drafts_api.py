import json
import shutil

import pytest
from fastapi.testclient import TestClient

from backend.config import BACKEND_DIR
from backend.deps import get_provider_factory
from backend.main import create_app
from backend.models import Draft
from .conftest import COMPLAINANT, draft_body, seed_session


def post(client, body):
    return client.post("/api/drafts", json=body)


def patch(client, draft_id, body):
    return client.patch(f"/api/drafts/{draft_id}", json=body)


def code(r):
    return r.json()["error"]["code"]


def create_draft(client, rule_id="R2", **over):
    s = seed_session(client, rule_id=rule_id)
    r = post(client, draft_body(s.id, **over))
    assert r.status_code == 200, r.text
    return s, r.json()


def write_departments(settings, records):
    (settings.data_dir / "departments.json").write_text(
        json.dumps({"departments": records}, ensure_ascii=False), encoding="utf-8")


def dept(id, routes, categories, verified=False, days=7):
    return {"id": id, "name": f"TEST ONLY {id}", "address": "TEST ADDRESS", "submit_via": "TEST CHANNEL",
            "response_days": days, "routes": routes, "categories": categories,
            "areas": ["*"], "verified": verified, "response_days_verified": verified}


# -- POST /api/drafts ---------------------------------------------------------------
def test_create_draft_returns_the_prd_shape_and_persists(client):
    s, body = create_draft(client)
    assert {"draft_id", "decision", "department", "html", "portal_fields", "next_steps"} <= set(body)
    assert body["draft_id"].startswith("d_")
    assert body["decision"]["rule_id"] == "R2" and body["route"] == "local_body"
    assert body["route_override"] is None
    assert set(body["department"]) == {"id", "name", "address", "submit_via", "response_days"}
    assert body["department"]["id"] == "local-body-generic"  # no known city in the address
    stored = client.app.state.db.get_draft(body["draft_id"])
    assert stored.session_id == s.id and stored.html == body["html"]
    assert stored.complainant.name == "R. Priya"


def test_placeholder_department_is_flagged_and_gives_no_deadline(client):
    _, body = create_draft(client)
    assert body["department_verified"] is False
    assert "could not be confirmed" in body["html"] and "உறுதிசெய்யப்படவில்லை" in body["html"]
    en, ta = body["next_steps"]["en"], body["next_steps"]["ta"]
    assert "has not been verified" in en and "within" not in en
    assert "சரிபார்க்கப்படவில்லை" in ta and "நாட்களுக்குள்" not in ta
    assert "30" not in en and "30" not in ta  # the placeholder 30 is never quoted as a deadline


def test_verified_department_states_its_configured_response_days(settings):
    write_departments(settings, [dept("test-verified", ["local_body"], ["streetlight"], verified=True, days=7)])
    with TestClient(create_app(settings)) as c:
        _, body = create_draft(c)
    assert body["department_verified"] is True and body["department"]["response_days"] == 7
    assert "within 7 days" in body["next_steps"]["en"] and "7 நாட்களுக்குள்" in body["next_steps"]["ta"]
    assert "could not be confirmed" not in body["html"]


def test_next_steps_use_fixed_text_from_rules_and_department_channel(client):
    _, body = create_draft(client)
    rules = client.app.state.rules.next_steps
    assert body["next_steps"]["en"].startswith(rules.routes["local_body"].en)
    assert "the office of your local body" in body["next_steps"]["en"]  # submit_via from departments.json


def test_cm_helpline_draft_has_placeholder_portal_fields_flagged_unverified(client):
    s, body = create_draft(client, rule_id="R3")
    assert body["route"] == "cm_helpline" and body["department"]["id"] == "cm-helpline"
    assert list(body["portal_fields"]) == ["Grievance details", "Communication address"]
    assert "The streetlight is dead." in body["portal_fields"]["Grievance details"]
    assert "தெருவிளக்கு எரியவில்லை." in body["portal_fields"]["Grievance details"]
    assert body["portal_fields"]["Communication address"] == "14 Gandhi Street"
    assert body["portal_fields_verified"] is False
    assert "unconfirmed placeholders" in body["html"]


def test_local_body_and_rti_have_no_portal_fields_because_the_prd_defines_none(client):
    assert create_draft(client, rule_id="R2")[1]["portal_fields"] == {}
    assert create_draft(client, rule_id="R1")[1]["portal_fields"] == {}


def test_rti_draft_uses_the_rti_template_and_lists_requested_info(client):
    s = seed_session(client, rule_id="R1", wants_records=True, requested_info=["Road repair budget"])
    body = post(client, draft_body(s.id)).json()
    assert body["route"] == "rti" and "following information" in body["html"]
    assert "Road repair budget" in body["html"]


def test_override_is_recorded_beside_the_rule_decision_not_instead_of_it(client):
    s = seed_session(client, rule_id="R2")
    body = post(client, draft_body(s.id, route_override="cm_helpline")).json()
    assert body["decision"]["route"] == "local_body" and body["decision"]["rule_id"] == "R2"
    assert body["route"] == "cm_helpline" and body["route_override"] == "cm_helpline"
    assert body["department"]["id"] == "cm-helpline"
    stored = client.app.state.db.get_draft(body["draft_id"])
    assert stored.decision.route == "local_body" and stored.route_override == "cm_helpline"
    assert stored.effective_route == "cm_helpline"


def test_override_equal_to_the_rule_route_is_not_stored_as_an_override(client):
    s = seed_session(client, rule_id="R2")
    assert post(client, draft_body(s.id, route_override="local_body")).json()["route_override"] is None


def test_unknown_override_value_is_rejected(client):
    s = seed_session(client)
    r = post(client, draft_body(s.id, route_override="mayor"))
    assert r.status_code == 400 and code(r) == "BAD_INPUT"


@pytest.mark.parametrize("status", ["needs_info", "photo_mismatch", "not_civic"])
def test_draft_only_allowed_when_session_is_ready(client, status):
    s = seed_session(client, status=status)
    r = post(client, draft_body(s.id))
    assert r.status_code == 409 and code(r) == "SESSION_NOT_READY"


def test_unknown_session_is_404(client):
    r = post(client, draft_body("s_nope"))
    assert r.status_code == 404 and code(r) == "NOT_FOUND"


def test_no_matching_department_is_422_no_department(settings):
    write_departments(settings, [dept("only-cm", ["cm_helpline"], ["*"])])
    with TestClient(create_app(settings)) as c:
        s = seed_session(c, rule_id="R2")  # local_body needs a department
        r = post(c, draft_body(s.id))
        assert r.status_code == 422 and code(r) == "NO_DEPARTMENT"
        assert c.app.state.db.get_session(s.id) is not None  # nothing else changed


def test_records_request_with_a_non_civic_category_has_no_department(client):
    s = seed_session(client, rule_id="R1", category="not_civic", wants_records=True)
    r = post(client, draft_body(s.id))
    assert r.status_code == 422 and code(r) == "NO_DEPARTMENT"


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("complainant"),
    lambda b: b["complainant"].update(name="   "),
    lambda b: b["complainant"].update(address=""),
    lambda b: b["complainant"].update(name="x" * 201),
    lambda b: b["complainant"].update(phone="9" * 21),
    lambda b: b["complainant"].update(email="a@b.c"),
    lambda b: b.update(html="<p>injected</p>"),
    lambda b: b.update(session_id=""),
])
def test_invalid_draft_requests_are_400(client, mutate):
    s = seed_session(client)
    body = draft_body(s.id)
    mutate(body)
    r = post(client, body)
    assert r.status_code == 400 and code(r) == "BAD_INPUT"


def test_several_drafts_per_session_are_allowed_and_independent(client):
    s = seed_session(client)
    a = post(client, draft_body(s.id)).json()["draft_id"]
    b = post(client, draft_body(s.id, complainant={"name": "Other", "address": "Elsewhere"})).json()["draft_id"]
    assert a != b
    db = client.app.state.db
    assert db.get_draft(a).complainant.name == "R. Priya" and db.get_draft(b).complainant.name == "Other"


def test_tamil_complainant_name_is_stored_and_rendered(client):
    s = seed_session(client)
    body = post(client, draft_body(s.id, complainant={"name": "பிரியா ரா", "address": "காந்தி தெரு 14"})).json()
    assert "பிரியா ரா" in body["html"] and "காந்தி தெரு 14" in body["html"]


def test_draft_endpoints_need_no_model_and_make_no_network_request(client):
    def boom():
        raise AssertionError("no model provider may be built for drafts")

    client.app.dependency_overrides[get_provider_factory] = lambda: boom
    s, body = create_draft(client)  # the autouse guard also blocks any real HTTP request
    assert patch(client, body["draft_id"], {"fields": {"summary_en": "Edited."}}).status_code == 200


def test_drafts_survive_an_app_restart(settings):
    with TestClient(create_app(settings)) as c1:
        s, body = create_draft(c1)
    with TestClient(create_app(settings)) as c2:
        stored = c2.app.state.db.get_draft(body["draft_id"])
        assert isinstance(stored, Draft) and stored.html == body["html"]
        r = patch(c2, body["draft_id"], {"fields": {"summary_en": "After restart."}})
        assert r.status_code == 200 and "After restart." in r.json()["html"]


def test_tests_never_touch_the_real_database():
    assert not (BACKEND_DIR / "data" / "kural.db").exists()


# -- PATCH /api/drafts/{id} ---------------------------------------------------------
def test_editing_a_summary_re_renders_and_persists(client):
    _, d = create_draft(client)
    r = patch(client, d["draft_id"], {"fields": {"summary_en": "Edited English text."}})
    assert r.status_code == 200
    body = r.json()
    assert body["draft_id"] == d["draft_id"] and "Edited English text." in body["html"]
    assert "The streetlight is dead." not in body["html"]
    assert "தெருவிளக்கு எரியவில்லை." in body["html"]  # untouched field unchanged
    stored = client.app.state.db.get_draft(d["draft_id"])
    assert stored.edited_fields == {"summary_en": "Edited English text."} and stored.html == body["html"]


def test_patch_returns_the_same_shape_as_post(client):
    _, d = create_draft(client)
    body = patch(client, d["draft_id"], {"fields": {"duration": "4 months"}}).json()
    assert set(body) == set(d)


@pytest.mark.parametrize("key", ["route", "decision", "department", "html", "legal_text", "next_steps",
                                 "portal_fields", "id", "category", "route_override"])
def test_only_generated_text_fields_are_editable(client, key):
    _, d = create_draft(client)
    before = client.app.state.db.get_draft(d["draft_id"])
    r = patch(client, d["draft_id"], {"fields": {key: "hacked"}})
    assert r.status_code == 400 and code(r) == "BAD_INPUT" and "Not editable" in r.json()["error"]["message"]
    assert client.app.state.db.get_draft(d["draft_id"]) == before  # nothing written


def test_edits_never_change_trusted_data(client):
    _, d = create_draft(client, rule_id="R3")
    r = patch(client, d["draft_id"], {"fields": {"summary_en": "x", "location_text": "y", "duration": "z",
                                                 "summary_ta": "ta"}}).json()
    assert r["decision"] == d["decision"] and r["department"] == d["department"]
    assert r["route"] == d["route"] and r["next_steps"] == d["next_steps"]
    assert r["department_verified"] == d["department_verified"] and r["portal_fields_verified"] is False


def test_edited_text_is_escaped_in_the_document(client):
    _, d = create_draft(client)
    html = patch(client, d["draft_id"], {"fields": {"summary_en": "<script>alert(1)</script>"}}).json()["html"]
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_edits_accumulate_and_feed_portal_fields(client):
    _, d = create_draft(client, rule_id="R3")
    patch(client, d["draft_id"], {"fields": {"summary_en": "First edit."}})
    r = patch(client, d["draft_id"], {"fields": {"summary_ta": "இரண்டாவது திருத்தம்."}}).json()
    assert "First edit." in r["portal_fields"]["Grievance details"]
    assert "இரண்டாவது திருத்தம்." in r["portal_fields"]["Grievance details"]
    assert client.app.state.db.get_draft(d["draft_id"]).edited_fields == {
        "summary_en": "First edit.", "summary_ta": "இரண்டாவது திருத்தம்."}


def test_location_and_duration_can_be_cleared_but_summaries_cannot(client):
    _, d = create_draft(client)
    r = patch(client, d["draft_id"], {"fields": {"location_text": "", "duration": ""}})
    html = r.json()["html"]
    assert r.status_code == 200 and "my locality" in html and "எங்கள் பகுதி" in html  # the subject has no place to name
    assert patch(client, d["draft_id"], {"fields": {"summary_en": "   "}}).status_code == 400
    assert patch(client, d["draft_id"], {"fields": {"summary_ta": ""}}).status_code == 400


@pytest.mark.parametrize("key,size", [("summary_en", 2001), ("summary_ta", 2001),
                                      ("location_text", 501), ("duration", 201)])
def test_edit_length_limits(client, key, size):
    _, d = create_draft(client)
    assert patch(client, d["draft_id"], {"fields": {key: "x" * size}}).status_code == 400
    assert patch(client, d["draft_id"], {"fields": {key: "x" * (size - 1)}}).status_code == 200


def test_complainant_partial_update_keeps_other_details(client):
    _, d = create_draft(client, rule_id="R3")
    r = patch(client, d["draft_id"], {"complainant": {"phone": "9000000000"}}).json()
    stored = client.app.state.db.get_draft(d["draft_id"]).complainant
    assert (stored.name, stored.address, stored.phone) == ("R. Priya", "14 Gandhi Street", "9000000000")
    r = patch(client, d["draft_id"], {"complainant": {"address": "99 New Road"}}).json()
    assert r["portal_fields"]["Communication address"] == "99 New Road" and "99 New Road" in r["html"]


def test_phone_can_be_cleared(client):
    _, d = create_draft(client)
    patch(client, d["draft_id"], {"complainant": {"phone": ""}})
    assert client.app.state.db.get_draft(d["draft_id"]).complainant.phone is None


@pytest.mark.parametrize("complainant", [{"name": "   "}, {"name": None}, {"address": None},
                                         {"address": ""}, {"id": "x"}, {"phone": "9" * 21}])
def test_invalid_complainant_edits_are_400_and_change_nothing(client, complainant):
    _, d = create_draft(client)
    before = client.app.state.db.get_draft(d["draft_id"])
    assert patch(client, d["draft_id"], {"complainant": complainant}).status_code == 400
    assert client.app.state.db.get_draft(d["draft_id"]) == before


@pytest.mark.parametrize("body", [{}, {"fields": {}}, {"complainant": {}}, {"fields": {}, "complainant": {}}])
def test_empty_patch_is_400(client, body):
    _, d = create_draft(client)
    r = patch(client, d["draft_id"], body)
    assert r.status_code == 400 and "Nothing to update" in r.json()["error"]["message"]


def test_unknown_top_level_patch_key_is_400(client):
    _, d = create_draft(client)
    assert patch(client, d["draft_id"], {"fields": {"summary_en": "x"}, "route": "rti"}).status_code == 400


def test_patch_unknown_draft_is_404(client):
    r = patch(client, "d_nope", {"fields": {"summary_en": "x"}})
    assert r.status_code == 404 and code(r) == "NOT_FOUND"
