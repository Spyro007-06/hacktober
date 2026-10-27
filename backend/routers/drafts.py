"""Draft endpoints: create, edit and download as PDF. POST /api/tts is a later step."""
import re

from fastapi import APIRouter, Depends, Response
from jinja2 import Environment

from backend.config import Settings
from backend.db import Database
from backend.deps import (get_db, get_lookup, get_portal, get_rules, get_settings_dep,
                          get_templates)
from backend.errors import not_found
from backend.models import DraftCreate, DraftPatch, DraftResponse
from backend.services import draft_flow
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.lookup import DepartmentLookup
from backend.services.routing import RulesConfig

router = APIRouter(prefix="/api", tags=["drafts"])


@router.post("/drafts", response_model=DraftResponse)
def create_draft(
    body: DraftCreate,
    db: Database = Depends(get_db),
    lookup: DepartmentLookup = Depends(get_lookup),
    rules: RulesConfig = Depends(get_rules),
    portal: PortalFieldsConfig = Depends(get_portal),
    env: Environment = Depends(get_templates),
) -> DraftResponse:
    draft = draft_flow.create_draft(db, lookup, rules, portal, env, body)
    return draft_flow.to_response(draft)


@router.get("/drafts/{draft_id}/pdf")
def get_draft_pdf(
    draft_id: str,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    rules: RulesConfig = Depends(get_rules),
    portal: PortalFieldsConfig = Depends(get_portal),
    env: Environment = Depends(get_templates),
) -> Response:
    draft = db.get_draft(draft_id)
    if draft is None:
        raise not_found("Draft")
    session = db.get_session(draft.session_id)
    if session is None or session.extraction is None:
        raise not_found("Session")
    pdf = draft_flow.build_pdf(draft, session, rules, portal, env, settings.uploads_dir)
    # PRD p.11: kural_<route>_<draft_id>.pdf. Both parts are sanitised again here
    # because they come from storage and end up in a response header.
    name = re.sub(r"[^A-Za-z0-9_-]", "_", f"kural_{draft.effective_route}_{draft.id}")
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{name}.pdf"',
        "Cache-Control": "no-store",  # contains personal data
        "X-Content-Type-Options": "nosniff",
    })


@router.patch("/drafts/{draft_id}", response_model=DraftResponse)
def patch_draft(
    draft_id: str,
    body: DraftPatch,
    db: Database = Depends(get_db),
    rules: RulesConfig = Depends(get_rules),
    portal: PortalFieldsConfig = Depends(get_portal),
    env: Environment = Depends(get_templates),
) -> DraftResponse:
    draft = draft_flow.update_draft(db, rules, portal, env, draft_id, body)
    return draft_flow.to_response(draft)
