"""Maintenance tasks. ``ping`` doubles as the worker's own health check."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope

logger = get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> dict[str, Any]:
    """Round-trip check: the worker is consuming jobs and can reach Postgres."""
    async with session_scope() as session:
        database_ok = (await session.execute(text("SELECT 1"))).scalar_one() == 1

    result = {
        "pong": True,
        "database": database_ok,
        "job_id": ctx.get("job_id"),
        "at": utcnow().isoformat(),
    }
    logger.info("worker_ping", **result)
    return result
