"""Draft creation and editing (POST/PATCH /api/drafts).

Rules enforced here, none of them delegated to a model:
- a draft exists only for a `ready` session, and the route is the session's
  deterministic decision (a user/operator `route_override` is recorded beside it,
  never in place of it);
- the department comes from departments.json via the lookup, never from text;
- only EDITABLE_FIELDS and complainant details can be edited; legal wording,
  route logic and department data are fixed (they live in templates/data);
- documents and next steps never present unverified data as official: a
  response time is stated only for a verified department.
"""
import base64
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from jinja2 import Environment
from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.db import Database, new_id
from backend.errors import bad_input, not_found, session_not_ready
from backend.models import (EDITABLE_FIELDS, Complainant, Department, Draft, DraftCreate,
                            DraftPatch, DraftResponse, Route, Session)
from backend.services.lookup import DepartmentLookup
from backend.services.pdf import render_pdf
from backend.services.render import render_html
from backend.services.routing import RulesConfig
from backend.services.uploads import resize_for_model, resolve_photo

log = logging.getLogger("kural.draft")

PDF_PHOTO_MAX_DIM = 1600  # px, longest side of a photo embedded in the PDF

# (min, max) length of an edited value after stripping. Location and duration
# may be cleared (min 0); the summaries may not.
FIELD_LIMITS = {"summary_en": (1, 2000), "summary_ta": (1, 2000),
                "location_text": (0, 500), "duration": (0, 200)}
MAX_REQUESTED_INFO = 20  # RTI questions; each at most INFO_ITEM_CHARS long
INFO_ITEM_CHARS = 500

PortalSource = Literal[
    "summary_en", "summary_ta", "summary_bilingual", "location_text", "duration",
    "complainant_name", "complainant_address", "complainant_phone", "department_name",
]


class PortalField(BaseModel):
    label: str = Field(min_length=1)
    source: PortalSource


class PortalRoute(BaseModel):
    fields: list[PortalField] = Field(default_factory=list)

    @field_validator("fields")
    @classmethod
    def _unique_labels(cls, v: list[PortalField]) -> list[PortalField]:
        labels = [f.label for f in v]
        if len(labels) != len(set(labels)):
            raise ValueError("duplicate portal field labels")
        return v


class PortalFieldsConfig(BaseModel):
    """portal_fields.json. `verified` stays false until the real form labels
    have been recorded and checked; it is copied onto every draft."""

    verified: bool = False
    note: str = ""
    routes: dict[Route, PortalRoute]

    @classmethod
    def load(cls, path: Path) -> "PortalFieldsConfig":
        cfg = cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if set(cfg.routes) != {"local_body", "cm_helpline", "rti"}:
            raise ValueError("portal_fields.json: needs local_body, cm_helpline and rti")
        return cfg


def _next_steps(route: Route, dept: Department, verified: bool, response_verified: bool,
                rules: RulesConfig) -> dict[str, str]:
    n = rules.next_steps
    out: dict[str, str] = {}
    for lang in ("en", "ta"):
        parts = [getattr(n.routes[route], lang),
                 getattr(n.submit_via, lang).format(submit_via=dept.submit_via)]
        if response_verified:
            parts.append(getattr(n.response_verified, lang).format(response_days=dept.response_days))
        else:  # no response-time commitment unless it is an official time limit
            parts.append(getattr(n.response_unverified, lang))
        if not verified:
            parts.append(getattr(n.demo_notice, lang))
        out[lang] = " ".join(parts)
    return out


def _values(session: Session, edits: dict) -> dict:
    e = session.extraction
    vals: dict = {
        "summary_en": e.summary_en, "summary_ta": e.summary_ta,
        "location_text": e.location_text, "duration": e.duration,
        "requested_info": list(e.requested_info),
    }
    vals.update(edits)  # the citizen's edits win; "" means cleared
    return vals


def _portal_fields(route: Route, vals: dict, c: Complainant, dept: Department,
                   portal: PortalFieldsConfig) -> dict[str, str]:
    sources = {
        **{k: vals[k] for k in ("summary_en", "summary_ta", "location_text", "duration")},
        "summary_bilingual": f"{vals['summary_en']}\n{vals['summary_ta']}",
        "complainant_name": c.name, "complainant_address": c.address,
        "complainant_phone": c.phone, "department_name": dept.name,
    }
    return {f.label: sources[f.source] or "" for f in portal.routes[route].fields}


def _context(draft: Draft, session: Session, rules: RulesConfig, portal: PortalFieldsConfig,
             evidence_photos: list[dict]) -> tuple[dict, dict[str, str], dict[str, str]]:
    """Template context from the draft's trusted stored parts plus the citizen's
    edits. Returns (context, portal_fields, next_steps)."""
    e = session.extraction
    route = draft.effective_route
    vals = _values(session, draft.edited_fields)
    portal_fields = _portal_fields(route, vals, draft.complainant, draft.department, portal)
    next_steps = _next_steps(route, draft.department, draft.department_verified,
                             draft.response_days_verified, rules)
    context = {
        "route": route, "draft_id": draft.id, "created_on": draft.created_at.date().isoformat(),
        "decision": {"reason_en": draft.decision.reason_en, "reason_ta": draft.decision.reason_ta},
        "department": {"name": draft.department.name, "address": draft.department.address},
        "department_verified": draft.department_verified,
        "demo_notice": rules.next_steps.demo_notice.model_dump(),
        "complainant": draft.complainant.model_dump(),
        "category": e.category, **vals,
        "photo_findings": e.photo_findings,
        "portal_fields": portal_fields, "portal_fields_verified": draft.portal_fields_verified,
        "next_steps": next_steps, "evidence_photos": evidence_photos,
    }
    return context, portal_fields, next_steps


def assemble(draft: Draft, session: Session, rules: RulesConfig,
             portal: PortalFieldsConfig, env: Environment) -> Draft:
    """Recompute everything derived (html, portal fields, next steps) from the
    draft's trusted stored parts plus the citizen's edits. The preview HTML never
    contains photos; they are added only when building the PDF."""
    context, portal_fields, next_steps = _context(draft, session, rules, portal, [])
    vals = _values(session, draft.edited_fields)
    return draft.model_copy(update={
        "html": render_html(env, draft.effective_route, context),
        "portal_fields": portal_fields, "next_steps": next_steps,
        # What the preview's Edit mode starts from: null becomes "" for the text boxes.
        "editable_fields": {k: (vals[k] if k == "requested_info" else (vals[k] or "")) for k in EDITABLE_FIELDS},
    })


def _evidence_photos(session: Session, uploads_dir: Path) -> list[dict]:
    """Stored photos as downscaled data URIs for the evidence page. A photo that
    is missing or unreadable becomes a placeholder entry, never an error: the
    document is still useful and the originals are never altered."""
    total = len(session.photo_paths)
    out: list[dict] = []
    for n, relative in enumerate(session.photo_paths, 1):
        try:
            data = resolve_photo(uploads_dir, relative).read_bytes()
            jpeg, mime = resize_for_model(data, PDF_PHOTO_MAX_DIM)  # EXIF-aware downscale
            uri = f"data:{mime};base64,{base64.b64encode(jpeg).decode('ascii')}"
        except Exception as exc:  # AppError, OSError, PIL errors, decompression bombs
            log.warning("evidence photo %d unavailable error_type=%s", n, type(exc).__name__)
            uri = None
        out.append({"n": n, "total": total, "data_uri": uri})
    return out


def build_pdf(draft: Draft, session: Session, rules: RulesConfig, portal: PortalFieldsConfig,
              env: Environment, uploads_dir: Path) -> bytes:
    """The bilingual PDF: the draft document plus an evidence page with the
    complainant's photos (when there are any)."""
    context, _, _ = _context(draft, session, rules, portal, _evidence_photos(session, uploads_dir))
    return render_pdf(render_html(env, draft.effective_route, context))


def create_draft(db: Database, lookup: DepartmentLookup, rules: RulesConfig,
                 portal: PortalFieldsConfig, env: Environment, body: DraftCreate,
                 now: Optional[datetime] = None) -> Draft:
    session = db.get_session(body.session_id)
    if session is None:
        raise not_found("Session")
    if session.status != "ready":
        reasons = {"needs_info": "Follow-up questions are still pending.",
                   "photo_mismatch": "The photo mismatch has not been resolved.",
                   "not_civic": "Kural does not cover this kind of problem, so no draft is possible."}
        raise session_not_ready(reasons.get(session.status, "The session is not ready."))
    if session.extraction is None or session.decision is None:
        raise session_not_ready("The session has no completed analysis.")

    rule_route = session.decision.route
    route = body.route_override or rule_route
    # No ward is known (GPS ward detection is not built), so address the office of the city named in the
    # complainant's address or the location, when a verified record exists for it.
    area = session.ward or lookup.area_in_text(body.complainant.address, session.extraction.location_text)
    record = lookup.require(route, session.extraction.category, area)  # 422 if none
    draft = Draft(
        id=new_id("d"), session_id=session.id, decision=session.decision,
        department=record.to_department(), complainant=body.complainant,
        html="", portal_fields={}, next_steps={}, created_at=now or datetime.now(),
        route_override=route if route != rule_route else None,
        department_verified=record.verified, response_days_verified=record.response_days_verified,
        portal_fields_verified=portal.verified,
    )
    draft = assemble(draft, session, rules, portal, env)
    db.save_draft(draft)
    return draft


def _clean_info(items) -> list[str]:
    if not isinstance(items, list):
        raise bad_input("'requested_info' must be a list of questions.")
    out = [i.strip() for i in items if i.strip()]  # blank lines are dropped
    if len(out) > MAX_REQUESTED_INFO or any(len(i) > INFO_ITEM_CHARS for i in out):
        raise bad_input(f"'requested_info' may have at most {MAX_REQUESTED_INFO} items of "
                        f"{INFO_ITEM_CHARS} characters.")
    return out


def _clean_edits(fields: dict) -> dict:
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        raise bad_input(f"Not editable: {', '.join(unknown)}. Editable: {', '.join(EDITABLE_FIELDS)}.")
    out: dict = {}
    for key, value in fields.items():
        if key == "requested_info":
            out[key] = _clean_info(value)
            continue
        if not isinstance(value, str):
            raise bad_input(f"'{key}' must be text.")
        value = value.strip()
        lo, hi = FIELD_LIMITS[key]
        if len(value) < lo or len(value) > hi:
            raise bad_input(f"'{key}' must be {'at most ' + str(hi) if lo == 0 else f'{lo}-{hi}'} characters.")
        out[key] = value
    return out


def _merged_complainant(current: Complainant, patch) -> Complainant:
    data = current.model_dump()
    for key, value in patch.model_dump(exclude_unset=True).items():
        if key == "phone":
            data["phone"] = (value or "").strip() or None
        elif value is None:
            raise bad_input(f"Complainant {key} cannot be cleared.")
        else:
            data[key] = value
    try:
        return Complainant.model_validate(data)
    except ValidationError:  # never echo submitted values
        raise bad_input("Invalid complainant details.")


def update_draft(db: Database, rules: RulesConfig, portal: PortalFieldsConfig,
                 env: Environment, draft_id: str, patch: DraftPatch) -> Draft:
    draft = db.get_draft(draft_id)
    if draft is None:
        raise not_found("Draft")
    session = db.get_session(draft.session_id)
    if session is None or session.extraction is None:
        raise not_found("Session")
    complainant_set = patch.complainant is not None and bool(patch.complainant.model_fields_set)
    if not patch.fields and not complainant_set:
        raise bad_input("Nothing to update.")

    edits = _clean_edits(patch.fields)
    complainant = _merged_complainant(draft.complainant, patch.complainant) if complainant_set \
        else draft.complainant
    updated = draft.model_copy(update={
        "complainant": complainant, "edited_fields": {**draft.edited_fields, **edits},
    })
    updated = assemble(updated, session, rules, portal, env)
    db.save_draft(updated)
    return updated


def to_response(d: Draft) -> DraftResponse:
    return DraftResponse(
        draft_id=d.id, decision=d.decision, route=d.effective_route,
        route_override=d.route_override, department=d.department,
        department_verified=d.department_verified,
        response_days_verified=d.response_days_verified, html=d.html,
        portal_fields=d.portal_fields, portal_fields_verified=d.portal_fields_verified,
        next_steps=d.next_steps, editable_fields=d.editable_fields,
    )
