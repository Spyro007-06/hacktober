"""Deterministic routing rules R1-R5 (PRD p.3). The LLM never chooses a route:
it only fills `Extraction`; this module decides from those fields plus the
complaint history.

Rules are disjoint except R1, which has precedence (PRD: first match wins), so
the evaluation order is R1, R5, then R4/R3/R2 by their specific conditions.
"""
import json
import re
from datetime import date
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from backend.models import Complaint, Extraction, Route, RouteDecision

RuleId = Literal["R1", "R2", "R3", "R4"]


class RuleText(BaseModel):
    route: Route
    reason_en: str
    reason_ta: str


class NotCivicNotice(BaseModel):
    en: str
    ta: str


class QuestionText(BaseModel):
    question_en: str
    question_ta: str


class Localized(BaseModel):
    en: str
    ta: str


class NextStepTexts(BaseModel):
    """Fixed bilingual next-step wording (reviewable data, never model-written)."""

    routes: dict[Route, Localized]
    submit_via: Localized  # contains {submit_via}
    response_verified: Localized  # contains {response_days}; used only for verified departments
    response_unverified: Localized
    demo_notice: Localized


class RulesConfig(BaseModel):
    spans_departments_categories: list[str] = []
    rules: dict[RuleId, RuleText]
    next_steps: NextStepTexts
    not_civic_notice: NotCivicNotice
    # Fixed follow-up wording per required field (never model-written).
    follow_up_questions: dict[str, QuestionText]

    @classmethod
    def load(cls, path: Path) -> "RulesConfig":
        cfg = cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
        expected = {"R1": "rti", "R2": "local_body", "R3": "cm_helpline", "R4": "rti"}
        for rid, route in expected.items():
            if cfg.rules.get(rid) is None or cfg.rules[rid].route != route:
                raise ValueError(f"rules.json: {rid} must exist with route {route}")
        if set(cfg.next_steps.routes) != {"local_body", "cm_helpline", "rti"}:
            raise ValueError("rules.json: next_steps.routes needs local_body, cm_helpline and rti")
        for lang in ("en", "ta"):
            if "{submit_via}" not in getattr(cfg.next_steps.submit_via, lang):
                raise ValueError(f"rules.json: next_steps.submit_via.{lang} needs {{submit_via}}")
            if "{response_days}" not in getattr(cfg.next_steps.response_verified, lang):
                raise ValueError(f"rules.json: next_steps.response_verified.{lang} needs {{response_days}}")
        if "location_text" not in cfg.follow_up_questions:
            raise ValueError("rules.json: follow_up_questions needs location_text")
        return cfg


_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_location(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", _PUNCT.sub(" ", (text or "").casefold())).strip()


def same_location(a: Optional[str], b: Optional[str]) -> bool:
    """Free-text match: equal after normalisation, or one contains the other.
    Missing locations never match."""
    na, nb = normalize_location(a), normalize_location(b)
    return bool(na) and bool(nb) and (na == nb or na in nb or nb in na)


def matching_open_complaints(
    extraction: Extraction, candidates: list[Complaint]
) -> list[Complaint]:
    """Earlier complaints that still count for routing: same category and
    location, and not resolved/escalated (those are superseded)."""
    return [
        c for c in candidates
        if c.category == extraction.category
        and c.status in ("filed", "overdue")
        and same_location(c.location_text, extraction.location_text)
    ]


def _decision(cfg: RulesConfig, rid: RuleId, level: int = 1) -> RouteDecision:
    r = cfg.rules[rid]
    return RouteDecision(
        route=r.route, rule_id=rid, reason_en=r.reason_en,
        reason_ta=r.reason_ta, escalation_level=level,
    )


def decide_route(
    extraction: Extraction,
    prior: list[Complaint],
    cfg: RulesConfig,
    today: date,
) -> Optional[RouteDecision]:
    """Return the RouteDecision, or None for R5 (not a civic problem).

    `prior` is any list of earlier complaints; matching and "ignored" (past
    due_on) are evaluated here.
    """
    # R1: wants records/information, not a fix.
    if extraction.wants_records:
        return _decision(cfg, "R1")
    # R5: not a civic problem -> no route.
    if extraction.category == "not_civic":
        return None

    matches = matching_open_complaints(extraction, prior)
    ignored = [c for c in matches if c.effective_status(today) == "overdue"]
    spans = extraction.category in cfg.spans_departments_categories

    # R4: CM Helpline grievance ignored after escalation (level 3 is the last).
    if any(c.route == "cm_helpline" and c.escalation_level >= 3 for c in ignored):
        return _decision(cfg, "R4")

    # R3: earlier complaint ignored, or problem spans departments. An ignored
    # CM Helpline complaint below level 3 climbs one level (PRD p.3 ladder).
    cm_ignored = [c for c in ignored if c.route == "cm_helpline"]
    if cm_ignored:
        return _decision(cfg, "R3", max(c.escalation_level for c in cm_ignored) + 1)
    if ignored or extraction.user_says_ignored or spans:
        return _decision(cfg, "R3", 1)

    # R2: civic problem, no earlier complaint. An earlier complaint that is
    # still within its deadline falls through to R2 (PRD gap, see issues list).
    return _decision(cfg, "R2")
