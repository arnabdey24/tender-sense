"""Liveness and readiness probes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.jobs.queue import redis_healthcheck

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: bool
    redis: bool


@router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReadinessResponse:
    database_ok = True
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via integration tests
        database_ok = False
        logger.warning("readiness_database_failed", error=str(exc))

    redis_ok = await redis_healthcheck()
    healthy = database_ok and redis_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if healthy else "degraded",
        database=database_ok,
        redis=redis_ok,
    )
