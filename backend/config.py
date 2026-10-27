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
    tts_engine: str = "none"
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
