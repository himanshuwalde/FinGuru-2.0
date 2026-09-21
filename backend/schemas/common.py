from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class PillarStatus(BaseModel):
    pillar: str
    phase: Literal["scaffolded"] = "scaffolded"
    modules: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "finguru-api"
