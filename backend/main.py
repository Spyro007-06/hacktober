"""Kural backend: FastAPI app factory. Run from the repo root:
    uvicorn backend.main:app --port 8000"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.config import Settings, get_settings
from backend.db import Database
from backend.errors import register_error_handlers
from backend.logging_config import setup_logging
from backend.routers import complaints, drafts, sessions, system, transcribe
from backend.routers import tts as tts_router
from backend.services.draft_flow import PortalFieldsConfig
from backend.services.lookup import DepartmentLookup
from backend.services.render import check_templates, make_env
from backend.services.routing import RulesConfig
from backend.services.stt import build_engine
from backend.services.tts import build_tts

log = logging.getLogger("kural")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        app.state.db = Database(settings.db_path)
        app.state.db.init()
        # Fail fast on missing or invalid data files.
        app.state.lookup = DepartmentLookup.load(settings.data_dir / "departments.json")
        app.state.rules = RulesConfig.load(settings.data_dir / "rules.json")
        app.state.portal = PortalFieldsConfig.load(settings.data_dir / "portal_fields.json")
        app.state.templates = make_env()
        check_templates(app.state.templates)
        # The speech engine is created but NOT loaded here: the model loads on first use.
        app.state.stt_engine = build_engine(settings)
        if app.state.stt_engine is None:
            log.warning("STT_ENGINE=%s is not implemented; /api/transcribe will return 503",
                        settings.stt_engine)
        elif (problem := app.state.stt_engine.check_files()):
            log.warning("speech model not ready: %s (/api/transcribe will return 503)", problem)
        app.state.tts = build_tts(settings)  # None when TTS_ENGINE=none: /api/tts answers 501
        if not app.state.portal.verified:
            log.warning("portal_fields.json labels are UNVERIFIED placeholders")
        unverified = app.state.lookup.unverified_ids()
        if unverified:
            log.warning(
                "%d department records are UNVERIFIED demo placeholders; "
                "replace departments.json before real use", len(unverified))
        log.info("started mode=%s", settings.model_mode)
        yield

    app = FastAPI(title="Kural API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list,
        allow_methods=["*"], allow_headers=["*"],
    )
    register_error_handlers(app)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        # Method, path and status only: no query strings or bodies.
        log.info("%s %s %s %.0fms", request.method, request.url.path,
                 response.status_code, (time.perf_counter() - start) * 1000)
        return response

    for module in (system, sessions, drafts, complaints, transcribe, tts_router):
        app.include_router(module.router)
    return app


app = create_app()
