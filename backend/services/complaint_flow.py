"""Complaint history (POST/GET /api/complaints) and one-tap escalation.

Kural never submits anything to a government portal. "Filing" here means the
citizen tells Kural they filed a draft, so the complaint is saved with its
deadline and later routing can use it. Every rule stays in Python:
- the due date is the filed date plus the department's response_days;
- "overdue" is computed from the due date (never stated by a model);
- the next rung of the ladder comes from routing.escalation_decision;
- escalation wording is fixed text from rules.json, filled only with the stored
  complaint's own dates and reference.
"""
from datetime import date, timedelta
from typing import Optional

from jinja2 import Environment

from backend.db import Database, new_id
from backend.errors import bad_input, not_found
from backend.models import (Complaint, ComplaintCreate, ComplaintListItem, Draft, DraftCreate,
                            Session)
from backend.services import draft_flow
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.lookup import DepartmentLookup
from backend.services.routing import RulesConfig, escalation_decision

CATEGORY_TITLES = {
    "road": "Road", "streetlight": "Streetlight", "garbage": "Garbage", "water": "Water supply",
    "drainage": "Drainage", "other_civic": "Civic issue",
}


def title_for(c: Complaint) -> str:
    return f"{CATEGORY_TITLES.get(c.category, 'Complaint')}, {c.location_text or 'location not stated'}"


def file_complaint(db: Database, body: ComplaintCreate, today: date) -> Complaint:
    draft = db.get_draft(body.draft_id)
    if draft is None:
        raise not_found("Draft")
    existing = db.get_complaint_for_draft(draft.id)
    if existing is not None:  # filing the same draft twice returns the same complaint
        return existing
    if body.filed_on > today:
        raise bad_input("filed_on cannot be in the future.")
    session = db.get_session(draft.session_id)
    if session is None or session.extraction is None:
        raise not_found("Session")

    parent: Optional[Complaint] = None
    if draft.parent_complaint_id:
        parent = db.get_complaint(draft.parent_complaint_id)
        if parent is None:
            raise not_found("Complaint")

    route = draft.effective_route
    location = draft.edited_fields.get("location_text", session.extraction.location_text)
    complaint = Complaint(
        id=new_id("c"), draft_id=draft.id, route=route, category=session.extraction.category,
        location_text=(location or "").strip() or None, ward=session.ward,
        filed_on=body.filed_on, due_on=body.filed_on + timedelta(days=draft.department.response_days),
        status="filed", parent_complaint_id=draft.parent_complaint_id,
        # An override changes the route the citizen chose, not the rule's ladder position.
        escalation_level=draft.decision.escalation_level if route == draft.decision.route else 1,
    )
    db.save_complaint(complaint)
    if parent is not None:  # the escalation was actually filed: the parent is now superseded
        db.save_complaint(parent.model_copy(update={"status": "escalated"}))
    return complaint


def list_complaints(db: Database, today: date) -> list[ComplaintListItem]:
    db.mark_overdue(today)  # persist the computed overdue state
    items = []
    verified: dict[str, bool] = {}  # draft id -> were its response_days from verified data
    for c in db.list_complaints():
        if c.draft_id not in verified:
            draft = db.get_draft(c.draft_id)
            verified[c.draft_id] = bool(draft and draft.response_days_verified)
        items.append(ComplaintListItem(
            id=c.id, draft_id=c.draft_id, title=title_for(c), route=c.route, category=c.category,
            location_text=c.location_text, ward=c.ward, filed_on=c.filed_on, due_on=c.due_on,
            days_left=(c.due_on - today).days, due_date_verified=verified[c.draft_id],
            status=c.effective_status(today),
            parent_complaint_id=c.parent_complaint_id, escalation_level=c.escalation_level))
    items.sort(key=lambda i: (i.status != "overdue", i.days_left))  # overdue first, then soonest due
    return items


def escalate_complaint(db: Database, lookup: DepartmentLookup, rules: RulesConfig,
                       portal: PortalFieldsConfig, env: Environment, complaint_id: str,
                       today: date) -> Draft:
    """Create (not file) the draft for the next rung. The original complaint is marked
    `escalated` only when the citizen files this draft, so abandoning it loses nothing."""
    complaint = db.get_complaint(complaint_id)
    if complaint is None:
        raise not_found("Complaint")
    decision = escalation_decision(complaint, rules, today)
    if decision is None:
        status = complaint.effective_status(today)
        if status in ("escalated", "resolved"):
            raise bad_input(f"This complaint is already {status}.")
        if status != "overdue":
            raise bad_input("Only overdue complaints can be escalated.")
        raise bad_input("An information request (RTI) cannot be escalated further.")

    source = db.get_draft(complaint.draft_id)
    original = db.get_session(source.session_id) if source else None
    if source is None or original is None or original.extraction is None:
        raise not_found("Draft")
    lookup.require(decision.route, original.extraction.category, original.ward)  # 422 before saving anything

    ref = {"complaint_id": complaint.id, "filed_on": complaint.filed_on.isoformat(),
           "due_on": complaint.due_on.isoformat()}
    note = rules.escalation.note
    requested = ([f"{q.en.format(**ref)} / {q.ta.format(**ref)}" for q in rules.escalation.rti_questions]
                 if decision.route == "rti" else [])
    extraction = original.extraction.model_copy(update={
        "summary_en": f"{original.extraction.summary_en} {note.en.format(**ref)}"[:2000],
        "summary_ta": f"{original.extraction.summary_ta} {note.ta.format(**ref)}"[:2000],
        "user_says_ignored": True, "wants_records": False, "missing_fields": [],
        "requested_info": requested,
    })
    session = Session(
        id=new_id("s"), transcript=original.transcript, language=original.language,
        photo_paths=list(original.photo_paths), lat=original.lat, lon=original.lon,
        ward=original.ward, extraction=extraction, decision=decision,
        prior_complaint_ids=[complaint.id], status="ready")
    db.save_session(session)
    draft = draft_flow.create_draft(
        db, lookup, rules, portal, env,
        DraftCreate(session_id=session.id, complainant=source.complainant))
    draft = draft.model_copy(update={"parent_complaint_id": complaint.id})
    db.save_draft(draft)
    return draft
