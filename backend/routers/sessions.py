import logging
import shutil
import unicodedata
from datetime import date
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend.config import Settings
from backend.db import Database, new_id
from backend.deps import get_db, get_provider_factory, get_rules, get_settings_dep
from backend.errors import bad_input, not_found
from backend.models import Session, SessionDetail, SessionResponse
from backend.services.extraction import extract
from backend.services.llm import ImagePart, LLMProvider
from backend.services.routing import RulesConfig
from backend.services.session_flow import apply_extraction, to_response
from backend.services.uploads import resize_for_model, resolve_photo, save_photos, validate_photos

log = logging.getLogger("kural.sessions")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

MAX_TEXT_CHARS = 5000
MAX_ANSWER_CHARS = 500
# Keys accepted by /answers. `location` is the PRD's example key and is an
# alias of location_text; `area` (PRD example) is appended to the location.
ANSWER_KEYS = {"location_text", "location", "area", "duration", "photo_mismatch"}


class AnswersBody(BaseModel):
    """Body of POST /sessions/{id}/answers: the frontend contract is
    {"answers": {...}, "confirm_photo_mismatch": bool}. `answers` may be empty (the citizen
    skipped the question: that still counts as a round) and the PRD's answer key
    photo_mismatch="confirm" is accepted as the same confirmation."""

    model_config = ConfigDict(extra="forbid")  # a misspelt field is a 400, not silently ignored

    answers: dict[str, str] = Field(max_length=10)  # required, but may be empty
    confirm_photo_mismatch: bool = False


def _clean_answers(raw: dict[str, str]) -> dict[str, str]:
    unknown = sorted(set(raw) - ANSWER_KEYS)
    if unknown:
        raise bad_input(f"Unknown answer field(s): {', '.join(unknown)}. "
                        f"Allowed: {', '.join(sorted(ANSWER_KEYS))}.")
    out: dict[str, str] = {}
    for key, value in raw.items():
        value = value.strip()
        if not value:
            raise bad_input(f"Answer '{key}' is empty.")
        if len(value) > MAX_ANSWER_CHARS:
            raise bad_input(f"Answer '{key}' is longer than {MAX_ANSWER_CHARS} characters.")
        out["location_text" if key == "location" else key] = value
    if "photo_mismatch" in out and out["photo_mismatch"] != "confirm":
        raise bad_input("photo_mismatch must be 'confirm'. To retake the photo, start a new session.")
    return out


def _model_images(blobs: list[bytes]) -> list[ImagePart]:
    return [ImagePart(*resize_for_model(b)) for b in blobs]


@router.post("", response_model=SessionResponse)
async def create_session(
    text: str = Form(...),
    language: Literal["ta", "en"] = Form(...),
    photos: list[UploadFile] = File(default_factory=list),
    lat: Optional[float] = Form(None, ge=-90, le=90),
    lon: Optional[float] = Form(None, ge=-180, le=180),
    input_source: Literal["typed", "speech"] = Form("typed"),
    transcript_confirmed: bool = Form(False),
    settings: Settings = Depends(get_settings_dep),
    db: Database = Depends(get_db),
    rules: RulesConfig = Depends(get_rules),
    make_provider: Callable[[], LLMProvider] = Depends(get_provider_factory),
):
    text = text.strip()
    if not text:
        raise bad_input("Complaint text is required.")
    if not any(unicodedata.category(c)[0] in "LN" for c in text):
        raise bad_input("The complaint text has no readable words. Please type or record it again.")
    if input_source == "speech" and not transcript_confirmed:
        # Speech recognition makes mistakes (especially in Tamil). The citizen must
        # read and, if needed, correct the transcript before it is treated as the
        # complaint, because wrong words can change the category and the route.
        raise bad_input("Please review and confirm the transcript (correct any mistakes) "
                        "before continuing: send transcript_confirmed=true.")
    if len(text) > MAX_TEXT_CHARS:
        raise bad_input(f"Complaint text is longer than {MAX_TEXT_CHARS} characters.")
    if len(photos) > settings.max_photos:
        raise bad_input(f"At most {settings.max_photos} photos are allowed.")
    max_bytes = settings.max_photo_mb * 1024 * 1024
    blobs = [await p.read(max_bytes + 1) for p in photos]  # bounded read
    validated = validate_photos(blobs, settings.max_photos, max_bytes)

    provider = make_provider()  # 503 here if the mode is not configured
    extraction = await extract(provider, text=text, language=language,
                               images=_model_images(blobs))

    session = Session(id=new_id("s"), transcript=text, language=language, lat=lat, lon=lon,
                      status="needs_info")
    session = apply_extraction(session, extraction, db, rules, date.today())
    # Persist only a successful, validated extraction; files first, so a
    # failed DB write can be cleaned up without leaving orphan rows.
    names = save_photos(settings.uploads_dir, session.id, validated) if validated else []
    try:
        db.save_session(session.model_copy(update={"photo_paths": names}))
    except Exception:
        shutil.rmtree(settings.uploads_dir / session.id, ignore_errors=True)
        raise
    return to_response(session, rules)


@router.post("/{session_id}/answers", response_model=SessionResponse)
async def answer_session(
    session_id: str,
    body: AnswersBody,
    settings: Settings = Depends(get_settings_dep),
    db: Database = Depends(get_db),
    rules: RulesConfig = Depends(get_rules),
    make_provider: Callable[[], LLMProvider] = Depends(get_provider_factory),
):
    session = db.get_session(session_id)
    if session is None:
        raise not_found("Session")
    if session.status not in ("needs_info", "photo_mismatch"):
        raise bad_input("This session is not waiting for answers.")
    new = _clean_answers(body.answers)
    confirming = body.confirm_photo_mismatch or "photo_mismatch" in new
    if body.confirm_photo_mismatch:
        new["photo_mismatch"] = "confirm"

    blobs = [resolve_photo(settings.uploads_dir, p).read_bytes() for p in session.photo_paths]
    merged = {**session.answers, **new}
    # A round is a set of follow-up answers, or a skipped question (empty answers);
    # confirming the photo alone is not one.
    used_round = any(k != "photo_mismatch" for k in new) or not confirming

    if new:
        provider = make_provider()
        extraction = await extract(provider, text=session.transcript, language=session.language,
                                   images=_model_images(blobs), answers=merged)
    else:  # a skipped question: nothing new to extract, so no model call; the round still counts
        extraction = session.extraction
        if extraction is None:
            raise bad_input("This session has no analysis to continue.")

    updated = session.model_copy(update={
        "answers": merged,
        "answer_rounds": session.answer_rounds + (1 if used_round else 0),
        "photo_mismatch_confirmed": session.photo_mismatch_confirmed or "photo_mismatch" in new,
    })
    updated = apply_extraction(updated, extraction, db, rules, date.today())
    db.save_session(updated)  # single transaction; earlier failures leave the old row intact
    return to_response(updated, rules)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(session_id: str, db: Database = Depends(get_db),
                rules: RulesConfig = Depends(get_rules)) -> SessionDetail:
    session = db.get_session(session_id)
    if session is None:
        raise not_found("Session")
    return SessionDetail(**session.model_dump(), session_id=session.id,
                         notice=to_response(session, rules).notice)
