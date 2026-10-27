import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.config import Settings
from backend.deps import get_settings_dep
from backend.models import ModeBody
from backend.services.llm import build_provider

log = logging.getLogger("kural.system")
router = APIRouter(prefix="/api", tags=["system"])


class Health(BaseModel):
    status: str
    model_mode: str
    model: str


@router.get("/health", response_model=Health)
def health(settings: Settings = Depends(get_settings_dep)) -> Health:
    # `model` is the configured identifier; it says nothing about reachability.
    return Health(status="ok", model_mode=settings.model_mode, model=settings.active_model)


@router.put("/config/mode", response_model=Health)
def set_mode(body: ModeBody, request: Request) -> Health:
    """Switch between online (Gemini) and offline (local Ollama) for this run of the
    server (PRD feature 14). The switch is in memory only: .env is never changed, and a
    restart returns to the configured MODEL_MODE. A mode that is not fully configured
    is refused with 503 and the current mode stays in force. Online mode sends complaint
    text and photos to Google, so the switch must be an explicit user action."""
    current: Settings = request.app.state.settings
    wanted = current.model_copy(update={"model_mode": body.mode})
    build_provider(wanted)  # raises 503 MODEL_UNAVAILABLE when the target mode is not configured
    request.app.state.settings = wanted
    log.info("model mode set to %s", wanted.model_mode)
    return Health(status="ok", model_mode=wanted.model_mode, model=wanted.active_model)
