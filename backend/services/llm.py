"""LLM provider abstraction (PRD p.13: one generate() switching Gemini API /
Ollama). `MODEL_MODE` is the only thing that selects a provider:

- online  -> GeminiProvider  (Gemini API, the only external service)
- offline -> OllamaProvider  (a local Ollama endpoint only)

A provider returns the model's raw JSON text. Parsing and validation belong to
services/extraction.py; providers never see routing. Errors map to the PRD's
codes: MODEL_TIMEOUT (504) and MODEL_UNAVAILABLE (503); responses never echo
upstream bodies, prompts or credentials.
"""
import asyncio
import base64
import ipaddress
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

import httpx

from backend.config import Settings
from backend.errors import AppError, model_timeout, model_unavailable

log = logging.getLogger("kural.llm")

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMMA4_PREFIX = "gemma-4"  # these model ids get the minimal documented request body
# Gemma 4 "thinks" by default: ~500 hidden tokens made one extraction take 14-28 s against the
# 30 s timeout (measured on gemma-4-26b-a4b-it). Extraction is a fill-in-the-fields task, so the
# lowest level gives the same answer in about 3 s. Only thinkingConfig is added to the minimal body.
GEMMA4_THINKING_LEVEL = "minimal"


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    model: str
    reachable: bool
    model_available: bool
    detail: str

    @property
    def ok(self) -> bool:
        return self.reachable and self.model_available


class LLMProvider(ABC):
    name: str

    def __init__(self, model: str, timeout_s: float,
                 transport: Optional[httpx.AsyncBaseTransport] = None, trust_env: bool = True):
        self.model = model
        self.timeout_s = timeout_s
        self._transport = transport
        self._trust_env = trust_env

    @abstractmethod
    async def generate_json(self, prompt: str, images: Sequence[ImagePart], schema: dict) -> str:
        """Return the model's raw text reply (expected to be one JSON object)."""

    @abstractmethod
    async def check(self) -> ProviderStatus:
        """Check connectivity and that the configured model exists. Sends no
        complaint data."""

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            # httpx timeouts are per phase; asyncio.timeout bounds the whole call.
            async with asyncio.timeout(self.timeout_s):
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout_s), transport=self._transport,
                    trust_env=self._trust_env,
                ) as client:
                    resp = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, TimeoutError):
            log.warning("provider=%s timeout", self.name)
            raise model_timeout()
        except httpx.HTTPError as exc:
            log.warning("provider=%s unreachable error=%s", self.name, type(exc).__name__)
            raise model_unavailable(f"Could not reach the {self.name} model service.")
        self._raise_for_status(resp)
        return resp

    def _raise_for_status(self, resp: httpx.Response) -> None:
        code = resp.status_code
        if code < 400:
            return
        log.warning("provider=%s http_status=%d", self.name, code)
        if code in (408, 504):
            raise model_timeout()
        if code in (401, 403):
            raise model_unavailable(f"The {self.name} service rejected the credentials.")
        if code == 404:
            raise model_unavailable(f"The configured {self.name} model was not found.")
        if code == 429:
            raise model_unavailable(f"The {self.name} service is rate-limiting requests.")
        if code >= 500:
            raise model_unavailable(f"The {self.name} service reported an error.")
        raise model_unavailable(f"The {self.name} service rejected the request.")

    def _json(self, resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise model_unavailable(f"The {self.name} service returned an unreadable response.")
        if not isinstance(data, dict):
            raise model_unavailable(f"The {self.name} service returned an unreadable response.")
        return data


class GeminiProvider(LLMProvider):
    """Gemini API (generativelanguage.googleapis.com) over REST.

    Uses prompt-enforced JSON rather than responseMimeType/responseSchema: the
    Gemma-on-Gemini-API documentation does not confirm JSON mode for Gemma.
    Strict validation in extraction.py is the safety net. Images are sent as
    inline_data, which the Gemma docs do not show (they show file upload):
    UNVERIFIED against a live key.
    """

    name = "Gemini"

    def __init__(self, api_key: str, model: str, timeout_s: float,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        super().__init__(_strip_models_prefix(model), timeout_s, transport, trust_env=True)
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self._api_key}  # header, never in the URL

    async def generate_json(self, prompt: str, images: Sequence[ImagePart], schema: dict) -> str:
        parts: list[dict] = [{"text": prompt}]
        for img in images:
            parts.append({"inline_data": {
                "mime_type": img.mime_type, "data": base64.b64encode(img.data).decode("ascii")}})
        if self.model.startswith(GEMMA4_PREFIX):
            # Google's documented Gemma 4 single-turn body is contents/parts: no role and no
            # temperature (Kural's role + temperature=0 body got HTTP 500 on gemma-4-31b-it,
            # observed 4x). The only addition is the thinking level, see GEMMA4_THINKING_LEVEL.
            body: dict[str, Any] = {
                "contents": [{"parts": parts}],
                "generationConfig": {"thinkingConfig": {"thinkingLevel": GEMMA4_THINKING_LEVEL}},
            }
        else:
            body = {"contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"temperature": 0}}
        resp = await self._request(
            "POST", f"{GEMINI_BASE}/models/{self.model}:generateContent",
            headers=self._headers(), json=body)
        data = self._json(resp)
        candidates = data.get("candidates") or []
        if not candidates:
            return ""  # blocked or empty: surfaces as invalid output upstream
        parts_out = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts_out
                       if isinstance(p, dict) and not p.get("thought"))

    async def check(self) -> ProviderStatus:
        try:
            await self._request("GET", f"{GEMINI_BASE}/models/{self.model}", headers=self._headers())
        except AppError as exc:
            reachable = exc.status_code == 503 and "not found" in exc.message
            return ProviderStatus(self.name, self.model, reachable, False, exc.message)
        return ProviderStatus(self.name, self.model, True, True,
                              "Model is listed by the Gemini API (generation not tested).")


class OllamaProvider(LLMProvider):
    """Local Ollama (/api/chat). Structured output uses Ollama's `format`
    JSON-schema field. Gemma 4 + `format` is UNVERIFIED against a live server."""

    name = "Ollama"

    def __init__(self, base_url: str, model: str, timeout_s: float,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        # trust_env=False: never route local complaint data through a system proxy.
        super().__init__(model, timeout_s, transport, trust_env=False)
        self._base = base_url.rstrip("/")

    async def generate_json(self, prompt: str, images: Sequence[ImagePart], schema: dict) -> str:
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            message["images"] = [base64.b64encode(i.data).decode("ascii") for i in images]
        body = {"model": self.model, "messages": [message], "stream": False,
                "format": schema, "options": {"temperature": 0}}
        resp = await self._request("POST", f"{self._base}/api/chat", json=body)
        content = (self._json(resp).get("message") or {}).get("content")
        return content if isinstance(content, str) else ""

    async def check(self) -> ProviderStatus:
        try:
            resp = await self._request("GET", f"{self._base}/api/tags")
        except AppError as exc:
            return ProviderStatus(self.name, self.model, False, False, exc.message)
        names = {m.get("name") for m in (self._json(resp).get("models") or []) if isinstance(m, dict)}
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        found = self.model in names or wanted in names
        return ProviderStatus(self.name, self.model, True, found,
                              "Model is installed in Ollama (generation not tested)." if found
                              else "Ollama is running but the configured model is not installed.")


def _strip_models_prefix(model: str) -> str:
    return model[len("models/"):] if model.startswith("models/") else model


def is_local_url(url: str) -> bool:
    """True for loopback/private/link-local addresses, localhost, and
    single-label hostnames (e.g. a Docker service name)."""
    parsed = urlparse(url)
    host = parsed.hostname
    if parsed.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return ip.is_loopback or ip.is_private or ip.is_link_local


def build_provider(
    settings: Settings, transport: Optional[httpx.AsyncBaseTransport] = None
) -> LLMProvider:
    """The single place where MODEL_MODE selects a provider. Offline never
    constructs or references the Gemini provider."""
    if settings.model_mode == "offline":
        if not settings.ollama_model:
            raise model_unavailable("OLLAMA_MODEL is not set.")
        if not is_local_url(settings.ollama_url):
            raise model_unavailable("OLLAMA_URL must point to a local machine in offline mode.")
        return OllamaProvider(settings.ollama_url, settings.ollama_model,
                              settings.model_timeout_s, transport)
    key = settings.gemini_api_key.get_secret_value().strip() if settings.gemini_api_key else ""
    if not key:
        raise model_unavailable("GEMINI_API_KEY is not set.")
    if not settings.gemini_model:
        raise model_unavailable("GEMINI_MODEL is not set.")
    return GeminiProvider(key, settings.gemini_model, settings.model_timeout_s, transport)
