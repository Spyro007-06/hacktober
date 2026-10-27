"""Bilingual HTML rendering of a draft (Jinja2). The PDF step is added later.

Templates hold only fixed layout and neutral labels: no legal citations, fees
or deadlines. Anything that varies comes through the context built in
services/draft_flow.py. Autoescape is on and undefined variables raise, so a
typo or an injected "<script>" can never silently reach the document.

Context keys: route, draft_id, created_on, decision{reason_en,reason_ta},
department{name,address}, department_verified, demo_notice{en,ta},
complainant{name,address,phone}, category, summary_en, summary_ta,
location_text, duration, photo_findings, requested_info, portal_fields,
portal_fields_verified, next_steps{en,ta}.
"""
from pathlib import Path
from typing import Any, Mapping

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from backend.models import Route

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
# local_body and cm_helpline are both complaints; RTI is always separate (PRD p.3).
TEMPLATE_BY_ROUTE: dict[Route, str] = {
    "local_body": "grievance.html",
    "cm_helpline": "grievance.html",
    "rti": "rti.html",
}


def make_env(templates_dir: Path = TEMPLATES_DIR) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(enabled_extensions=("html",), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def check_templates(env: Environment) -> None:
    """Fail fast at startup if a template is missing or has a syntax error."""
    for name in set(TEMPLATE_BY_ROUTE.values()):
        env.get_template(name)


def render_html(env: Environment, route: Route, context: Mapping[str, Any]) -> str:
    return env.get_template(TEMPLATE_BY_ROUTE[route]).render(**context)
