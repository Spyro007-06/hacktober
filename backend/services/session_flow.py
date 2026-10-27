"""Turns a validated Extraction into a Session: the deterministic route
decision (services/routing.py), follow-up questions, and status. Nothing here
reads a route from the model."""
from datetime import date

from backend.db import Database
from backend.models import (MAX_ANSWER_ROUNDS, REQUIRED_FIELDS, Extraction,
                            FollowUpQuestion, Session, SessionResponse)
from backend.services.routing import RulesConfig, decide_route, matching_open_complaints


def apply_extraction(session: Session, extraction: Extraction, db: Database,
                     rules: RulesConfig, today: date) -> Session:
    """Return `session` updated with `extraction`, its route decision, status
    and follow-up questions. Pure apart from reading complaint history."""
    prior = db.open_complaints_for_category(extraction.category)
    decision = decide_route(extraction, prior, rules, today)
    questions = [
        FollowUpQuestion(field=f, **rules.follow_up_questions[f].model_dump())
        for f in REQUIRED_FIELDS
        if f in extraction.missing_fields and f in rules.follow_up_questions
    ]
    mismatch = extraction.photo_matches_claim is False and not session.photo_mismatch_confirmed
    asking = bool(questions) and session.answer_rounds < MAX_ANSWER_ROUNDS

    if decision is None:  # R5
        status, questions = "not_civic", []
    elif mismatch:
        status = "photo_mismatch"
        questions = questions if asking else []
    elif asking:
        status = "needs_info"
    else:  # complete, or the 2 question rounds are used up (PRD p.10)
        status, questions = "ready", []

    return Session.model_validate({
        **session.model_dump(),
        "extraction": extraction.model_dump(),
        "decision": decision.model_dump() if decision else None,
        "prior_complaint_ids": [c.id for c in matching_open_complaints(extraction, prior)],
        "status": status,
        "follow_up_questions": [q.model_dump() for q in questions],
    })


def to_response(session: Session, rules: RulesConfig) -> SessionResponse:
    return SessionResponse(
        session_id=session.id, status=session.status, extraction=session.extraction,
        decision=session.decision, ward=session.ward,
        follow_up_questions=session.follow_up_questions,
        notice=rules.not_civic_notice.model_dump() if session.status == "not_civic" else None,
    )
