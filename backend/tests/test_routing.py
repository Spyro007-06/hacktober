from datetime import timedelta

import pytest

from backend.config import BACKEND_DIR
from backend.models import Complaint
from backend.services.routing import RulesConfig, decide_route, same_location
from .conftest import TODAY, make_extraction

CFG = RulesConfig.load(BACKEND_DIR / "data" / "rules.json")


def complaint(route="local_body", status="filed", due_offset=-10, level=1,
              category="streetlight", location="Gandhi Street"):
    return Complaint(id="c_1", draft_id="d_1", route=route, category=category,
                     location_text=location, filed_on=TODAY - timedelta(days=60),
                     due_on=TODAY + timedelta(days=due_offset), status=status,
                     escalation_level=level)


def route(ext, prior=()):
    return decide_route(ext, list(prior), CFG, TODAY)


def test_r1_wants_records():
    d = route(make_extraction(wants_records=True))
    assert (d.rule_id, d.route) == ("R1", "rti")


def test_r1_precedes_not_civic():
    assert route(make_extraction(category="not_civic", wants_records=True)).rule_id == "R1"


def test_r5_not_civic_returns_none():
    assert route(make_extraction(category="not_civic")) is None


def test_r2_new_civic_problem():
    d = route(make_extraction())
    assert (d.rule_id, d.route, d.escalation_level) == ("R2", "local_body", 1)


def test_r3_user_says_ignored():
    d = route(make_extraction(user_says_ignored=True))
    assert (d.rule_id, d.route, d.escalation_level) == ("R3", "cm_helpline", 1)


def test_r3_overdue_local_body_complaint_in_history():
    d = route(make_extraction(), [complaint(status="filed", due_offset=-1)])
    assert (d.rule_id, d.route) == ("R3", "cm_helpline")


def test_r3_spans_departments_configured_category():
    cfg = CFG.model_copy(update={"spans_departments_categories": ["drainage"]})
    assert decide_route(make_extraction(category="drainage"), [], cfg, TODAY).rule_id == "R3"


def test_earlier_complaint_within_deadline_falls_to_r2():
    assert route(make_extraction(), [complaint(due_offset=5)]).rule_id == "R2"


def test_resolved_or_escalated_history_is_ignored():
    for status in ("resolved", "escalated"):
        assert route(make_extraction(), [complaint(status=status)]).rule_id == "R2"


def test_history_for_other_location_or_category_does_not_match():
    assert route(make_extraction(), [complaint(location="Nehru Road")]).rule_id == "R2"
    assert route(make_extraction(), [complaint(category="road")]).rule_id == "R2"


def test_cm_helpline_ignored_climbs_levels():
    d = route(make_extraction(), [complaint(route="cm_helpline", level=1)])
    assert (d.rule_id, d.escalation_level) == ("R3", 2)
    d = route(make_extraction(), [complaint(route="cm_helpline", level=2)])
    assert (d.rule_id, d.escalation_level) == ("R3", 3)


def test_r4_after_level_three_ignored():
    d = route(make_extraction(), [complaint(route="cm_helpline", level=3)])
    assert (d.rule_id, d.route) == ("R4", "rti")


def test_r4_not_fired_when_level_three_within_deadline():
    prior = [complaint(route="cm_helpline", level=3, due_offset=3)]
    assert route(make_extraction(), prior).rule_id == "R2"


def test_not_civic_stays_r5_despite_ignored_flag_or_history():
    ext = make_extraction(category="not_civic", user_says_ignored=True)
    assert route(ext, [complaint(category="not_civic")]) is None


def test_r1_precedes_r4_and_r3():
    prior = [complaint(route="cm_helpline", level=3)]
    assert route(make_extraction(wants_records=True), prior).rule_id == "R1"
    assert route(make_extraction(wants_records=True, user_says_ignored=True)).rule_id == "R1"


def test_due_date_boundary_today_is_not_ignored_yesterday_is():
    assert route(make_extraction(), [complaint(due_offset=0)]).rule_id == "R2"
    assert route(make_extraction(), [complaint(due_offset=-1)]).rule_id == "R3"


def test_r4_beats_user_says_ignored_when_level_three_overdue():
    prior = [complaint(route="cm_helpline", level=3)]
    assert route(make_extraction(user_says_ignored=True), prior).rule_id == "R4"


def test_llm_cannot_inject_a_route():
    with pytest.raises(Exception):
        make_extraction(route="rti")


def test_reasons_come_from_rules_file_in_both_languages():
    d = route(make_extraction())
    assert d.reason_en == CFG.rules["R2"].reason_en and d.reason_ta


@pytest.mark.parametrize("a,b,expected", [
    ("Gandhi Street", "gandhi street.", True),
    ("Gandhi Street, near bus stand", "Gandhi Street", True),
    ("Gandhi Street", "Nehru Street", False),
    (None, "Gandhi Street", False),
    ("", "", False),
])
def test_same_location(a, b, expected):
    assert same_location(a, b) is expected


def test_rules_file_validation(tmp_path):
    bad = tmp_path / "rules.json"
    bad.write_text('{"rules": {}, "not_civic_notice": {"en": "a", "ta": "b"}}')
    with pytest.raises(Exception):
        RulesConfig.load(bad)
