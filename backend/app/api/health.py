"""Liveness and readiness endpoints.

The distinction matters: ``/healthz`` says the process is alive, ``/readyz`` says
it can actually serve traffic. A process with a dead database is live but not
ready, and conflating the two hides real outages.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app import __version__
from app.config import get_settings
from app.db import check_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool]


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    """Liveness. Deliberately touches no dependency."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        app=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
    )


@router.get("/readyz", response_model=ReadinessResponse)
def readyz(response: Response) -> ReadinessResponse:
    """Readiness. Returns 503 when a required dependency is unavailable."""
    checks = {"database": check_connection()}

    if all(checks.values()):
        return ReadinessResponse(status="ready", checks=checks)

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="not_ready", checks=checks)
