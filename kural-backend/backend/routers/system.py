from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.config import Settings
from backend.deps import get_settings_dep

router = APIRouter(prefix="/api", tags=["system"])


class Health(BaseModel):
    status: str
    model_mode: str
    model: str


@router.get("/health", response_model=Health)
def health(settings: Settings = Depends(get_settings_dep)) -> Health:
    # `model` is the configured identifier; it says nothing about reachability.
    return Health(status="ok", model_mode=settings.model_mode, model=settings.active_model)
