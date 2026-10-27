"""Complaint history and escalation (PRD p.12). Nothing here contacts a government portal."""
from datetime import date

from fastapi import APIRouter, Depends
from jinja2 import Environment

from backend.db import Database
from backend.deps import get_db, get_lookup, get_portal, get_rules, get_templates
from backend.models import Complaint, ComplaintCreate, ComplaintListItem, DraftResponse
from backend.services import complaint_flow, draft_flow
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.lookup import DepartmentLookup
from backend.services.routing import RulesConfig

router = APIRouter(prefix="/api", tags=["complaints"])


@router.post("/complaints", response_model=Complaint)
def file_complaint(body: ComplaintCreate, db: Database = Depends(get_db)) -> Complaint:
    return complaint_flow.file_complaint(db, body, date.today())


@router.get("/complaints", response_model=list[ComplaintListItem])
def list_complaints(db: Database = Depends(get_db)) -> list[ComplaintListItem]:
    return complaint_flow.list_complaints(db, date.today())


@router.post("/complaints/{complaint_id}/escalate", response_model=DraftResponse)
def escalate_complaint(
    complaint_id: str,
    db: Database = Depends(get_db),
    lookup: DepartmentLookup = Depends(get_lookup),
    rules: RulesConfig = Depends(get_rules),
    portal: PortalFieldsConfig = Depends(get_portal),
    env: Environment = Depends(get_templates),
) -> DraftResponse:
    draft = complaint_flow.escalate_complaint(db, lookup, rules, portal, env, complaint_id, date.today())
    return draft_flow.to_response(draft)
