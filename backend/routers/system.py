import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from backend.config import Settings
from backend.deps import get_settings_dep
from backend.errors import model_unavailable
from backend.models import ModeBody
from backend.services.llm import build_provider

log = logging.getLogger("kural.system")
router = APIRouter(prefix="/api", tags=["system"])


class Health(BaseModel):
    status: str
    model_mode: str
    model: str
    tts: list[str] = []  # languages with a working voice; empty means POST /api/tts answers 501


def _tts_languages(request: Request) -> list[str]:
    engine = getattr(request.app.state, "tts", None)
    return [lang for lang in ("ta", "en") if engine is not None and engine.supports(lang)]


@router.get("/health", response_model=Health)
def health(request: Request, settings: Settings = Depends(get_settings_dep)) -> Health:
    # `model` is the configured identifier; it says nothing about reachability.
    return Health(status="ok", model_mode=settings.model_mode, model=settings.active_model,
                  tts=_tts_languages(request))


@router.put("/config/mode", response_model=Health)
async def set_mode(body: ModeBody, request: Request) -> Health:
    """Switch between online (Gemini) and offline (local Ollama) for this run of the
    server (PRD feature 14). The switch is in memory only: .env is never changed, and a
    restart returns to the configured MODEL_MODE. A mode that is not fully configured is
    refused with 503, and so is offline when Ollama is not running or the model is not
    installed (the frontend then reverts its toggle); the current mode stays in force.
    Switching to online makes no network call; it sends complaint text and photos to
    Google only when a complaint is analysed afterwards, so the switch must be an explicit
    user action."""
    current: Settings = request.app.state.settings
    wanted = current.model_copy(update={"model_mode": body.mode})
    provider = build_provider(wanted, getattr(request.app.state, "http_transport", None))  # 503 if unconfigured
    if wanted.model_mode == "offline":
        status = await provider.check()  # asks the local Ollama server only; sends no complaint data
        if not status.ok:
            raise model_unavailable(status.detail)
    request.app.state.settings = wanted
    log.info("model mode set to %s", wanted.model_mode)
    return Health(status="ok", model_mode=wanted.model_mode, model=wanted.active_model,
                  tts=_tts_languages(request))
