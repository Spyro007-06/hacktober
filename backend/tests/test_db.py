import sqlite3
from datetime import date, datetime

import pytest

from backend.db import Database, new_id
from backend.models import (Complainant, Complaint, Department, Draft,
                            RouteDecision, Session)
from .conftest import make_extraction


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "t.db")
    d.init()
    return d


def make_session(**kw):
    base = dict(id="s_1", transcript="hello", language="ta", status="ready",
                extraction=make_extraction(), photo_paths=["s_1/a.png"])
    base.update(kw)
    return Session(**base)


def make_draft(session_id="s_1", id="d_1"):
    return Draft(
        id=id, session_id=session_id,
        decision=RouteDecision(route="local_body", rule_id="R2", reason_en="a", reason_ta="b"),
        department=Department(id="x", name="n", address="a", submit_via="s", response_days=30),
        complainant=Complainant(name="n", address="a"), html="<p/>", portal_fields={},
        next_steps={"en": "e", "ta": "t"}, created_at=datetime(2026, 10, 26))


def make_complaint(id="c_1", **kw):
    base = dict(id=id, draft_id="d_1", route="local_body", category="streetlight",
                location_text="Gandhi Street", filed_on=date(2026, 9, 1),
                due_on=date(2026, 10, 1), status="filed")
    base.update(kw)
    return Complaint(**base)


def test_init_is_idempotent(db):
    db.init()
    with db.connect() as c:
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sessions", "drafts", "complaints"} <= names


def test_session_roundtrip_and_update(db):
    s = make_session()
    db.save_session(s)
    assert db.get_session("s_1") == s
    db.save_session(s.model_copy(update={"status": "needs_info"}))
    assert db.get_session("s_1").status == "needs_info"
    assert db.get_session("missing") is None


def test_persists_across_reopen(tmp_path):
    p = tmp_path / "t.db"
    a = Database(p)
    a.init()
    a.save_session(make_session())
    b = Database(p)
    b.init()
    assert b.get_session("s_1").transcript == "hello"


def test_draft_and_complaint_roundtrip(db):
    db.save_session(make_session())
    db.save_draft(make_draft())
    db.save_complaint(make_complaint())
    assert db.get_draft("d_1").complainant.name == "n"
    assert db.get_complaint("c_1") == make_complaint()


def test_foreign_keys_enforced(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.save_draft(make_draft(session_id="nope"))
    db.save_session(make_session())
    db.save_draft(make_draft())
    with pytest.raises(sqlite3.IntegrityError):
        db.save_complaint(make_complaint(draft_id="nope"))


def test_failed_write_rolls_back(db):
    db.save_session(make_session())
    with pytest.raises(sqlite3.IntegrityError):
        with db.connect() as c:
            c.execute("UPDATE sessions SET status='needs_info' WHERE id='s_1'")
            c.execute("INSERT INTO drafts (id, session_id, created_at, data) "
                      "VALUES ('d_2','nope','x','{}')")
    assert db.get_session("s_1").status == "ready"


def test_history_query_and_overdue(db):
    db.save_session(make_session())
    db.save_draft(make_draft())
    db.save_complaint(make_complaint("c_1"))
    db.save_complaint(make_complaint("c_2", status="resolved"))
    db.save_complaint(make_complaint("c_3", category="road"))
    assert [c.id for c in db.open_complaints_for_category("streetlight")] == ["c_1"]
    assert db.mark_overdue(date(2026, 10, 26)) == 2  # c_1 and c_3
    assert db.get_complaint("c_1").status == "overdue"
    assert db.get_complaint("c_2").status == "resolved"


def test_new_id_format():
    a, b = new_id("s"), new_id("s")
    assert a.startswith("s_") and a != b
