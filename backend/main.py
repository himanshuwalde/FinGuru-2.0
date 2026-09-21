"""FinGuru FastAPI application.

Run from the repository root:

    python -m uvicorn backend.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routers import ai_cfo, auth, grow, learn, protect, track
from backend.schemas.common import ErrorBody, ErrorResponse, HealthResponse

log = logging.getLogger("finguru.api")

app = FastAPI(title="FinGuru API", version="0.1.0")
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATUS_TO_CODE = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "service_unavailable",
}


def _error_response(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    code = _STATUS_TO_CODE.get(exc.status_code, "error")
    return _error_response(exc.status_code, code, message)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error_response(
        422,
        "validation_error",
        "Invalid request payload.",
        details=jsonable_encoder(exc.errors()),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(500, "internal_error", "Internal server error.")


for _router in (track.router, grow.router, learn.router, protect.router, ai_cfo.router, auth.router):
    app.include_router(_router, prefix=settings.api_prefix)


@app.get(f"{settings.api_prefix}/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse()
