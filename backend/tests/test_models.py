from datetime import date, datetime

import pytest
from pydantic import ValidationError

from backend.models import (Complainant, Complaint, Department, Draft,
                            RouteDecision, Session)
from .conftest import make_extraction


def test_extraction_valid_defaults():
    e = make_extraction()
    assert e.photo_findings == [] and e.photo_matches_claim is None
    assert e.wants_records is False and e.missing_fields == []


def test_extraction_rejects_route_field():
    with pytest.raises(ValidationError):
        make_extraction(route="rti")


def test_extraction_rejects_bad_category_and_severity():
    with pytest.raises(ValidationError):
        make_extraction(category="potholes")
    with pytest.raises(ValidationError):
        make_extraction(severity="extreme")


def test_extraction_rejects_blank_summary():
    with pytest.raises(ValidationError):
        make_extraction(summary_en="   ")


def test_extraction_missing_fields_restricted_and_deduped():
    e = make_extraction(missing_fields=["location_text", "location_text"])
    assert e.missing_fields == ["location_text"]
    with pytest.raises(ValidationError):
        make_extraction(missing_fields=["category"])


def test_department_requires_positive_response_days():
    with pytest.raises(ValidationError):
        Department(id="a", name="n", address="a", submit_via="s", response_days=0)


def test_route_decision_rejects_r5_and_bad_level():
    with pytest.raises(ValidationError):
        RouteDecision(route="rti", rule_id="R5", reason_en="x", reason_ta="x")
    with pytest.raises(ValidationError):
        RouteDecision(route="rti", rule_id="R1", reason_en="x", reason_ta="x", escalation_level=4)


def test_complainant_validation():
    assert Complainant(name=" R. Priya ", address="14 Gandhi St").name == "R. Priya"
    with pytest.raises(ValidationError):
        Complainant(name="  ", address="x")


def test_session_defaults_and_limits():
    s = Session(id="s_1", transcript="t", language="ta", status="needs_info")
    assert s.extraction is None and s.decision is None and s.answer_rounds == 0
    with pytest.raises(ValidationError):
        Session(id="s_1", transcript="t", language="fr", status="ready")
    with pytest.raises(ValidationError):
        Session(id="s_1", transcript="t", language="en", status="ready", photo_paths=list("abcd"))
    with pytest.raises(ValidationError):
        Session(id="s_1", transcript="t", language="en", status="ready", lat=91)


def test_complaint_effective_status():
    c = Complaint(id="c", draft_id="d", route="local_body", category="road",
                  filed_on=date(2026, 9, 1), due_on=date(2026, 10, 1), status="filed")
    assert c.effective_status(date(2026, 10, 1)) == "filed"
    assert c.effective_status(date(2026, 10, 2)) == "overdue"
    resolved = c.model_copy(update={"status": "resolved"})
    assert resolved.effective_status(date(2027, 1, 1)) == "resolved"


def test_draft_roundtrip():
    dec = RouteDecision(route="local_body", rule_id="R2", reason_en="a", reason_ta="b")
    d = Draft(id="d_1", session_id="s_1", decision=dec,
              department=Department(id="x", name="n", address="a", submit_via="s", response_days=30),
              complainant=Complainant(name="n", address="a"), html="<p/>",
              portal_fields={"k": "v"}, next_steps={"en": "e", "ta": "t"},
              created_at=datetime(2026, 10, 26, 10, 0))
    assert Draft.model_validate_json(d.model_dump_json()) == d
