"""FastAPI dependencies giving routers access to app-scoped services."""
from typing import Callable

from fastapi import Request
from jinja2 import Environment

from backend.config import Settings
from backend.db import Database
from backend.errors import model_unavailable
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.llm import LLMProvider, build_provider
from backend.services.lookup import DepartmentLookup
from backend.services.routing import RulesConfig
from backend.services.stt import STTEngine


def get_provider_factory(request: Request) -> Callable[[], LLMProvider]:
    """A factory, not a provider: configuration errors (503) must surface only
    after request validation, so building is deferred to the handler.
    `app.state.http_transport` lets tests inject a mock HTTP transport."""
    settings = request.app.state.settings
    transport = getattr(request.app.state, "http_transport", None)
    return lambda: build_provider(settings, transport)


def get_stt_engine_factory(request: Request) -> Callable[[], STTEngine]:
    """A factory, not an engine: like the LLM provider, a configuration error (503)
    must surface only after the upload has been validated (400 comes first)."""
    def get_engine() -> STTEngine:
        engine = request.app.state.stt_engine
        if engine is None:
            raise model_unavailable(
                f"The speech engine '{request.app.state.settings.stt_engine}' is not implemented. "
                "Set STT_ENGINE=whisper.")
        return engine

    return get_engine


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_lookup(request: Request) -> DepartmentLookup:
    return request.app.state.lookup


def get_rules(request: Request) -> RulesConfig:
    return request.app.state.rules


def get_portal(request: Request) -> PortalFieldsConfig:
    return request.app.state.portal


def get_templates(request: Request) -> Environment:
    return request.app.state.templates
