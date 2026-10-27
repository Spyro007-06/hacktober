"""POST /api/tts: text -> WAV audio from the offline engine, or 501 when there is none."""
from fastapi import APIRouter, Depends, Request, Response

from backend.config import Settings
from backend.deps import get_settings_dep
from backend.models import TtsBody
from backend.services import tts

router = APIRouter(prefix="/api", tags=["speech"])


@router.post("/tts", responses={200: {"content": {"audio/wav": {}}}})
def text_to_speech(body: TtsBody, request: Request,
                   settings: Settings = Depends(get_settings_dep)) -> Response:
    audio = tts.speak(request.app.state.tts, body.text, body.language, settings.tts_max_chars)
    return Response(content=audio, media_type="audio/wav", headers={
        "Cache-Control": "no-store",  # the text can contain personal details
        "X-Content-Type-Options": "nosniff",
    })
