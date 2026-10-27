"""The seven Pydantic models from PRD p.6-7, plus the small additions approved
in decision D5 (marked "added")."""
from datetime import date, datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

Route = Literal["local_body", "cm_helpline", "rti"]
Category = Literal[
    "road", "streetlight", "garbage", "water", "drainage", "other_civic", "not_civic"
]
SessionStatus = Literal["needs_info", "photo_mismatch", "not_civic", "ready"]
ComplaintStatus = Literal["filed", "overdue", "resolved", "escalated"]

# Fields the model may report as missing and the user may be asked about (D4:
# only location_text is required; duration is asked but optional).
ASKABLE_FIELDS = ("location_text", "duration")
REQUIRED_FIELDS = ("location_text",)
MAX_ANSWER_ROUNDS = 2  # PRD p.10


class Extraction(BaseModel):
    """Returned by Gemma and validated. Unknown fields are rejected; there is
    deliberately no route field."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    summary_en: str = Field(min_length=1, max_length=2000)
    summary_ta: str = Field(min_length=1, max_length=2000)
    location_text: Optional[str] = Field(None, max_length=500)
    duration: Optional[str] = Field(None, max_length=200)
    severity: Literal["low", "medium", "high"]
    photo_findings: list[str] = Field(default_factory=list, max_length=20)
    photo_matches_claim: Optional[bool] = None  # None when no photo
    photo_mismatch_note: Optional[str] = Field(None, max_length=1000)
    wants_records: bool = False  # R1
    user_says_ignored: bool = False
    requested_info: list[str] = Field(default_factory=list, max_length=20)
    missing_fields: list[str] = Field(default_factory=list)

    @field_validator("summary_en", "summary_ta")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("missing_fields")
    @classmethod
    def _askable_only(cls, v: list[str]) -> list[str]:
        bad = [f for f in v if f not in ASKABLE_FIELDS]
        if bad:
            raise ValueError(f"unsupported missing_fields: {bad}")
        return list(dict.fromkeys(v))


class RouteDecision(BaseModel):
    """Produced by the rules engine, never by Gemma. R5 yields no decision."""

    route: Route
    rule_id: Literal["R1", "R2", "R3", "R4"]
    reason_en: str
    reason_ta: str
    escalation_level: int = Field(1, ge=1, le=3)  # within CM Helpline


class Department(BaseModel):
    id: str
    name: str
    address: str
    submit_via: str  # portal URL, email or office
    response_days: int = Field(gt=0)


class Complainant(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown keys are rejected, not dropped

    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator("name", "address")
    @classmethod
    def _strip_nonblank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class FollowUpQuestion(BaseModel):  # added: shape from PRD p.10 example
    field: str
    question_en: str
    question_ta: str


class Session(BaseModel):
    id: str
    transcript: str
    language: Literal["ta", "en"]
    photo_paths: list[str] = Field(default_factory=list, max_length=3)
    lat: Optional[float] = Field(None, ge=-90, le=90)  # P1 ward detection
    lon: Optional[float] = Field(None, ge=-180, le=180)
    ward: Optional[str] = None
    extraction: Optional[Extraction] = None
    decision: Optional[RouteDecision] = None
    prior_complaint_ids: list[str] = Field(default_factory=list)
    status: SessionStatus
    follow_up_questions: list[FollowUpQuestion] = Field(default_factory=list)  # added
    answer_rounds: int = Field(0, ge=0, le=MAX_ANSWER_ROUNDS)  # added
    answers: dict[str, str] = Field(default_factory=dict)  # added: citizen's follow-up answers
    photo_mismatch_confirmed: bool = False  # added: citizen confirmed the photo anyway


class SessionDetail(Session):
    """GET /api/sessions/{id}: the full stored session plus the fields of SessionResponse that
    the frontend reads after a refresh (it uses `session_id`, and `notice` for R5)."""

    session_id: str
    notice: Optional[dict[str, str]] = None


class SessionResponse(BaseModel):
    """Response of POST /api/sessions and POST /api/sessions/{id}/answers (PRD p.9-10)."""

    session_id: str
    status: SessionStatus
    extraction: Optional[Extraction] = None
    decision: Optional[RouteDecision] = None
    ward: Optional[str] = None
    follow_up_questions: list[FollowUpQuestion] = Field(default_factory=list)
    notice: Optional[dict[str, str]] = None  # added: {"en","ta"} when status is not_civic (R5)


# Generated text the citizen may edit in the preview (PRD p.11: only
# Gemma-written fields and complainant details). Everything else is fixed.
EDITABLE_FIELDS = ("summary_en", "summary_ta", "location_text", "duration", "requested_info")


class Draft(BaseModel):
    id: str
    session_id: str
    decision: RouteDecision  # always the RULE's decision; never replaced by an override
    department: Department
    complainant: Complainant
    html: str  # bilingual rendered template
    portal_fields: dict[str, str]  # CM Helpline field name -> value
    next_steps: dict[str, str]  # {"en": ..., "ta": ...}
    created_at: datetime
    # added: PRD p.11 says the draft records both the rule's choice (`decision`)
    # and the user's override. Set only when it differs from the rule's route.
    route_override: Optional[Route] = None
    # added: trust flags so documents never present placeholders as official.
    department_verified: bool = False
    # added: True when the department's response time is official (e.g. the 30 days the RTI Act gives).
    response_days_verified: bool = False
    portal_fields_verified: bool = False
    # added: citizen edits to EDITABLE_FIELDS, applied on top of the extraction.
    edited_fields: dict[str, Union[str, list[str]]] = Field(default_factory=dict)
    # added: the current value of every editable field (edits applied), for the preview's
    # Edit mode (docs/frontend-requirements.md); recomputed whenever the draft is rebuilt.
    editable_fields: dict[str, Union[str, list[str]]] = Field(default_factory=dict)
    # added: set on an escalation draft (POST /api/complaints/{id}/escalate); the
    # complaint filed from it records this as its parent.
    parent_complaint_id: Optional[str] = None

    @property
    def effective_route(self) -> Route:
        return self.route_override or self.decision.route


class TranscriptResponse(BaseModel):
    """Response of POST /api/transcribe (PRD p.9)."""

    transcript: str
    language: Literal["ta", "en"]
    engine: Literal["whisper"]  # "gemma" is not implemented


class DraftCreate(BaseModel):
    """Body of POST /api/drafts (PRD p.10)."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=64)
    complainant: Complainant
    route_override: Optional[Route] = None


class ComplainantPatch(BaseModel):
    """Partial complainant update for PATCH /api/drafts/{id}."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=500)
    phone: Optional[str] = Field(None, max_length=20)


class DraftPatch(BaseModel):
    """Body of PATCH /api/drafts/{id} (PRD p.11). Which `fields` keys are
    allowed is enforced in services/draft_flow.py (EDITABLE_FIELDS)."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, Union[str, list[str]]] = Field(default_factory=dict, max_length=10)
    complainant: Optional[ComplainantPatch] = None


class DraftResponse(BaseModel):
    """Response of POST and PATCH /api/drafts (PRD p.11), plus trust flags."""

    draft_id: str
    decision: RouteDecision
    route: Route  # effective route (override if set, else the rule's)
    route_override: Optional[Route] = None
    department: Department
    department_verified: bool  # False = no verified office for the complainant's city (generic addressee)
    response_days_verified: bool = False  # True only for an official time limit (e.g. the RTI Act's 30 days)
    html: str
    portal_fields: dict[str, str]
    portal_fields_verified: bool  # False = labels not confirmed against the real form
    next_steps: dict[str, str]
    editable_fields: dict[str, Union[str, list[str]]] = Field(default_factory=dict)  # added: see Draft


class Complaint(BaseModel):  # P0 history, stored in SQLite
    id: str
    draft_id: str
    route: Route
    category: Category
    location_text: Optional[str] = None
    ward: Optional[str] = None
    filed_on: date
    due_on: date  # filed_on + department.response_days
    status: ComplaintStatus
    parent_complaint_id: Optional[str] = None  # set when escalated from another
    escalation_level: int = Field(1, ge=1, le=3)  # added (D3): needed for R4

    def effective_status(self, today: date) -> ComplaintStatus:
        """`overdue` is computed from due_on (PRD p.12: days_left below 0)."""
        if self.status == "filed" and self.due_on < today:
            return "overdue"
        return self.status


class ComplaintCreate(BaseModel):
    """Body of POST /api/complaints: the citizen records that they filed this draft."""

    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1, max_length=64)
    filed_on: date


class ComplaintListItem(BaseModel):
    """One row of GET /api/complaints (PRD p.12): the tracker with days left."""

    id: str
    draft_id: str
    title: str
    route: Route
    category: Category
    location_text: Optional[str] = None
    ward: Optional[str] = None
    filed_on: date
    due_on: date
    days_left: int  # negative once overdue
    due_date_verified: bool = False  # False = response_days come from demo placeholder data
    status: ComplaintStatus
    parent_complaint_id: Optional[str] = None
    escalation_level: int = Field(1, ge=1, le=3)


class ModeBody(BaseModel):
    """Body of PUT /api/config/mode."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["online", "offline"]


class TtsBody(BaseModel):
    """Body of POST /api/tts. The text length limit is enforced by the TTS service."""

    model_config = ConfigDict(extra="forbid")

    text: str
    language: Literal["ta", "en"]
