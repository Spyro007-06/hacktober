import json

import pytest

from backend.config import BACKEND_DIR
from backend.errors import AppError
from backend.models import Department
from backend.services.lookup import DepartmentLookup, DepartmentsFile

PATH = BACKEND_DIR / "data" / "departments.json"
LOOKUP = DepartmentLookup.load(PATH)


def entry(id, areas):
    return {"id": id, "name": id, "address": "a", "submit_via": "s", "response_days": 5,
            "routes": ["local_body"], "categories": ["road"], "areas": areas}


def test_every_category_has_local_body_and_rti_department():
    for cat in ("road", "streetlight", "garbage", "water", "drainage", "other_civic"):
        assert LOOKUP.find("local_body", cat) is not None
        assert LOOKUP.find("rti", cat) is not None


def test_cm_helpline_wildcard_category():
    assert LOOKUP.find("cm_helpline", "water").id == "cm-helpline"


def test_no_match_raises_no_department():
    with pytest.raises(AppError) as e:
        LOOKUP.require("local_body", "not_civic")
    assert (e.value.status_code, e.value.code) == (422, "NO_DEPARTMENT")


def test_returns_plain_department_model():
    d = LOOKUP.require("local_body", "road").to_department()
    assert type(d) is Department and d.response_days == 30


def test_only_the_generic_fallbacks_are_unverified():
    assert json.loads(PATH.read_text(encoding="utf-8"))["_meta"]["verified"] is False
    assert sorted(LOOKUP.unverified_ids()) == ["local-body-generic", "rti-generic"]
    for r in LOOKUP._records:
        assert "DEMO" not in r.name and "PLACEHOLDER" not in r.address


def test_rti_response_time_is_the_statutory_30_days_and_nothing_else_is_claimed_official():
    for r in LOOKUP._records:
        assert r.response_days_verified is (r.routes == ["rti"])
        if r.response_days_verified:
            assert r.response_days == 30


@pytest.mark.parametrize("text,expected", [
    ("14 Gandhi Street, Anna Nagar, Chennai 600040", "chennai"),
    ("5 Market Road, சென்னை", "சென்னை"),
    ("RS Puram, Coimbatore", "coimbatore"),
    ("Gandhipuram, கோவை", "கோவை"),
    ("12 Temple Road, Madurai", None),
])
def test_city_is_found_in_the_address(text, expected):
    assert LOOKUP.area_in_text(text) == expected


def test_city_in_the_address_selects_that_citys_office():
    assert LOOKUP.find("local_body", "road", LOOKUP.area_in_text("Anna Nagar, Chennai")).id == "gcc-local-body"
    assert LOOKUP.find("local_body", "road", LOOKUP.area_in_text("RS Puram, Coimbatore")).id == "ccmc-local-body"
    assert LOOKUP.find("rti", "water", LOOKUP.area_in_text("RS Puram, Coimbatore")).id == "ccmc-rti"
    assert LOOKUP.find("local_body", "road", LOOKUP.area_in_text("Temple Road, Madurai")).id == "local-body-generic"


def test_area_specific_entry_beats_wildcard():
    data = {"departments": [entry("any", ["*"]), entry("w12", ["Ward 12"])]}
    lk = DepartmentLookup(DepartmentsFile.model_validate(data).departments)
    assert lk.find("local_body", "road", "ward 12").id == "w12"
    assert lk.find("local_body", "road", "Ward 3").id == "any"
    assert lk.find("local_body", "road").id == "any"


def test_area_only_entry_needs_matching_area():
    data = {"departments": [entry("w12", ["Ward 12"])]}
    lk = DepartmentLookup(DepartmentsFile.model_validate(data).departments)
    assert lk.find("local_body", "road") is None
    assert lk.find("local_body", "road", "Ward 3") is None


def test_duplicate_ids_rejected(tmp_path):
    d = json.loads(PATH.read_text(encoding="utf-8"))
    d["departments"].append(d["departments"][0])
    p = tmp_path / "d.json"
    p.write_text(json.dumps(d))
    with pytest.raises(Exception):
        DepartmentLookup.load(p)
