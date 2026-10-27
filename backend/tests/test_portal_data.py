import json
import shutil

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.config import BACKEND_DIR
from backend.main import create_app
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.routing import RulesConfig

DATA = BACKEND_DIR / "data"


def write(tmp_path, data):
    p = tmp_path / "portal_fields.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


GOOD = {"verified": False, "routes": {"local_body": {"fields": []}, "cm_helpline": {"fields": []},
                                      "rti": {"fields": []}}}


def test_shipped_portal_fields_are_unverified_placeholders_with_only_prd_example_labels():
    cfg = PortalFieldsConfig.load(DATA / "portal_fields.json")
    assert cfg.verified is False and "PLACEHOLDER" in cfg.note
    assert [f.label for f in cfg.routes["cm_helpline"].fields] == ["Grievance details", "Communication address"]
    assert cfg.routes["local_body"].fields == [] and cfg.routes["rti"].fields == []


def test_unknown_source_is_rejected(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["routes"]["cm_helpline"]["fields"] = [{"label": "X", "source": "api_key"}]
    with pytest.raises(ValidationError):
        PortalFieldsConfig.load(write(tmp_path, bad))


def test_duplicate_labels_are_rejected(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["routes"]["cm_helpline"]["fields"] = [{"label": "X", "source": "summary_en"},
                                              {"label": "X", "source": "summary_ta"}]
    with pytest.raises(ValidationError):
        PortalFieldsConfig.load(write(tmp_path, bad))


def test_missing_route_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        PortalFieldsConfig.load(write(tmp_path, {"verified": False, "routes": {"rti": {"fields": []}}}))


def test_shipped_next_steps_cover_all_routes_in_both_languages():
    n = RulesConfig.load(DATA / "rules.json").next_steps
    for route in ("local_body", "cm_helpline", "rti"):
        assert n.routes[route].en.strip() and n.routes[route].ta.strip()
    for lang in ("en", "ta"):
        assert "{submit_via}" in getattr(n.submit_via, lang)
        assert "{response_days}" in getattr(n.response_verified, lang)
        assert getattr(n.response_unverified, lang).strip() and getattr(n.demo_notice, lang).strip()


def test_next_steps_missing_placeholder_is_rejected(tmp_path):
    data = json.loads((DATA / "rules.json").read_text(encoding="utf-8"))
    data["next_steps"]["response_verified"]["en"] = "Reply soon."
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        RulesConfig.load(p)


def test_startup_fails_fast_without_portal_fields(settings):
    (settings.data_dir / "portal_fields.json").unlink()
    with pytest.raises(FileNotFoundError):
        with TestClient(create_app(settings)):
            pass


def test_startup_fails_fast_on_invalid_portal_fields(settings):
    (settings.data_dir / "portal_fields.json").write_text('{"routes": {}}')
    with pytest.raises(ValueError):
        with TestClient(create_app(settings)):
            pass


def test_startup_warns_that_portal_labels_are_unverified(settings, caplog):
    with caplog.at_level("WARNING", logger="kural"):
        with TestClient(create_app(settings)):
            pass
    assert any("portal_fields.json" in r.getMessage() and "UNVERIFIED" in r.getMessage() for r in caplog.records)
