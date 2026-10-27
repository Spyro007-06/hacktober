"""One JSON error shape for every failure (PRD p.12):
{"error": {"code": "...", "message": "..."}}"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("kural.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def bad_input(message: str) -> AppError:
    return AppError(400, "BAD_INPUT", message)


def not_found(what: str) -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found.")


def session_not_ready(message: str) -> AppError:
    return AppError(409, "SESSION_NOT_READY", message)


def model_invalid_output() -> AppError:
    return AppError(
        422, "MODEL_INVALID_OUTPUT",
        "Could not understand the complaint. Please try again or type it.",
    )


def no_department() -> AppError:
    return AppError(
        422, "NO_DEPARTMENT",
        "No department matches this category and area. Please pick one manually.",
    )


def model_unavailable(message: str = "The AI model is unavailable.") -> AppError:
    return AppError(503, "MODEL_UNAVAILABLE", message)


def model_timeout() -> AppError:
    return AppError(504, "MODEL_TIMEOUT", "The AI model took too long to respond.")


def tts_unavailable() -> AppError:
    # PRD p.11 specifies 501 but names no code.
    return AppError(501, "TTS_UNAVAILABLE", "Speech output is not available; showing text only.")


def pdf_unavailable(message: str = "PDF export is not available.") -> AppError:
    # Not in the PRD's error table (decision D3): the PDF engine, its system
    # libraries or the bundled font are missing.
    return AppError(503, "PDF_UNAVAILABLE", message)


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # Field names only; never echo submitted values (may be personal data).
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in exc.errors()})
        return JSONResponse(_body("BAD_INPUT", "Invalid input: " + ", ".join(fields)), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code == 404 else "BAD_INPUT" if exc.status_code < 500 else "INTERNAL_ERROR"
        message = "Resource not found." if exc.status_code == 404 else "Request could not be processed."
        return JSONResponse(_body(code, message), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.error("unhandled error type=%s", type(exc).__name__)
        return JSONResponse(_body("INTERNAL_ERROR", "Unexpected server error."), status_code=500)
