"""POST /api/transcribe: audio (webm or wav) + language -> text, locally (PRD p.9)."""
from typing import Callable, Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from backend.config import Settings
from backend.deps import get_settings_dep, get_stt_engine_factory
from backend.models import TranscriptResponse
from backend.services import stt

router = APIRouter(prefix="/api", tags=["speech"])


@router.post("/transcribe", response_model=TranscriptResponse)
def transcribe(
    response: Response,
    audio: UploadFile = File(...),
    language: Literal["ta", "en"] = Form(...),
    settings: Settings = Depends(get_settings_dep),
    get_engine: Callable[[], stt.STTEngine] = Depends(get_stt_engine_factory),
) -> TranscriptResponse:
    max_bytes = settings.max_audio_mb * 1024 * 1024
    try:
        data = audio.file.read(max_bytes + 1)  # bounded read; one byte over means too large
    finally:
        audio.file.close()  # removes the temporary spool file Starlette may have created
    result = stt.transcribe_upload(data, audio.content_type, language, get_engine, settings)
    response.headers["Cache-Control"] = "no-store"  # the transcript is personal data
    return TranscriptResponse(transcript=result.text, language=language, engine="whisper")
