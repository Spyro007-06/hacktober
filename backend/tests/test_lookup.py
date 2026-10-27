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
    assert LOOKUP.find("cm_helpline", "water").id == "demo-cm-helpline"


def test_no_match_raises_no_department():
    with pytest.raises(AppError) as e:
        LOOKUP.require("local_body", "not_civic")
    assert (e.value.status_code, e.value.code) == (422, "NO_DEPARTMENT")


def test_returns_plain_department_model():
    d = LOOKUP.require("local_body", "road").to_department()
    assert type(d) is Department and d.response_days == 30


def test_all_shipped_entries_are_marked_unverified_placeholders():
    assert json.loads(PATH.read_text(encoding="utf-8"))["_meta"]["verified"] is False
    for r in LOOKUP._records:
        assert r.verified is False and "DEMO" in r.name


def test_unverified_ids_lists_every_placeholder():
    assert len(LOOKUP.unverified_ids()) == len(LOOKUP._records) == 7


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
