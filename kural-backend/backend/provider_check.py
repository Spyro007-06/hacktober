"""Manual provider connectivity check:  python -m backend.provider_check

Uses the same MODEL_MODE / .env settings as the server. Contacts only the
selected provider (Gemini in online mode, local Ollama in offline mode), sends
no complaint data, and prints no secrets. Exit code: 0 ok, 1 provider problem,
2 not configured.
"""
import asyncio
import sys

from backend.config import get_settings
from backend.errors import AppError
from backend.services.llm import build_provider


async def run() -> int:
    settings = get_settings()
    print(f"MODEL_MODE={settings.model_mode}")
    try:
        provider = build_provider(settings)
    except AppError as exc:
        print(f"NOT CONFIGURED: {exc.message}")
        return 2
    print(f"Provider: {provider.name}  model: {provider.model}")
    status = await provider.check()
    print(f"reachable={status.reachable}  model_available={status.model_available}")
    print(status.detail)
    return 0 if status.ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
