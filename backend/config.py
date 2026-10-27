"""Application settings, loaded from environment variables / .env (PRD p.13)."""
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR.parent / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    model_mode: Literal["online", "offline"] = "online"
    gemini_api_key: Optional[SecretStr] = None
    gemini_model: str = ""
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = ""
    # Only "whisper" (local faster-whisper) is implemented; "gemma" and "indic" are
    # accepted values (PRD p.13) that the API reports as unavailable.
    stt_engine: Literal["gemma", "whisper", "indic"] = "whisper"
    stt_model_dir: Path = Path("./data/models/whisper/small")  # relative to backend/
    stt_cpu_threads: int = Field(0, ge=0, le=64)  # 0 = auto (physical cores, max 8)
    stt_beam_size: int = Field(5, ge=1, le=10)
    stt_timeout_s: int = Field(120, ge=1)  # per transcription request (MODEL_TIMEOUT_S is too short for CPU STT)
    max_audio_mb: int = Field(10, ge=1)
    max_audio_s: int = Field(300, ge=1)
    # "none" = no speech output (POST /api/tts answers 501 and the UI shows text only).
    # "piper" = run the Piper CLI as a separate local process (see services/tts.py).
    tts_engine: Literal["none", "piper"] = "none"
    tts_piper_python: Optional[Path] = None  # python.exe of the separate venv that has piper-tts
    tts_voice_ta: Optional[Path] = None  # Piper .onnx voice (its .onnx.json sits beside it)
    tts_voice_en: Optional[Path] = None
    tts_timeout_s: int = Field(30, ge=1, le=300)
    tts_max_chars: int = Field(1500, ge=1, le=5000)
    audio_chunk_s: int = Field(30, ge=1, le=30)  # Whisper/Gemma window is 30 s (PRD p.5)
    model_timeout_s: int = Field(30, ge=1)
    max_photos: int = Field(3, ge=0, le=3)
    max_photo_mb: int = Field(8, ge=1)
    data_dir: Path = Path("./data")
    ward_boundaries: Path = Path("./data/wards.geojson")
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    log_level: str = "INFO"

    @field_validator("data_dir", "ward_boundaries", "stt_model_dir")
    @classmethod
    def _resolve_against_backend(cls, v: Path) -> Path:
        # PRD writes DATA_DIR=./data; relative paths mean backend/data.
        return v if v.is_absolute() else (BACKEND_DIR / v).resolve()

    @field_validator("tts_engine", mode="before")
    @classmethod
    def _blank_engine_is_none(cls, v):
        return "none" if isinstance(v, str) and not v.strip() else v

    @field_validator("tts_piper_python", "tts_voice_ta", "tts_voice_en", mode="before")
    @classmethod
    def _blank_is_unset(cls, v):
        return None if isinstance(v, str) and not v.strip() else v  # `TTS_VOICE_EN=` in .env

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kural.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def active_model(self) -> str:
        name = self.gemini_model if self.model_mode == "online" else self.ollama_model
        return name or "unconfigured"


@lru_cache
def get_settings() -> Settings:
    return Settings()
