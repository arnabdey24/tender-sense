"""Fixed-window rate limiting backed by Redis.

Used on the unauthenticated endpoints where guessing is cheap: login, password
reset and verification resends. Redis being unavailable must never lock users
out, so a failure to reach it allows the request and logs a warning.
"""

from __future__ import annotations

from app.core.exceptions import RateLimitedError
from app.core.logging import get_logger
from app.jobs.queue import get_queue

logger = get_logger(__name__)


async def enforce_rate_limit(
    key: str, *, limit: int, window_seconds: int, message: str | None = None
) -> None:
    """Count one hit against ``key`` and raise once the limit is exceeded."""
    redis_key = f"ratelimit:{key}"
    try:
        redis = await get_queue()
        hits = await redis.incr(redis_key)
        if hits == 1:
            await redis.expire(redis_key, window_seconds)
    except Exception as exc:  # pragma: no cover - availability beats enforcement
        logger.warning("rate_limit_unavailable", key=key, error=str(exc))
        return

    if hits > limit:
        logger.info("rate_limited", key=key, hits=hits, limit=limit)
        raise RateLimitedError(message or "Too many attempts. Please try again later.")


def client_ip(forwarded_for: str | None, fallback: str | None) -> str:
    """First address in X-Forwarded-For, else the socket peer.

    Caddy sets the header, so the socket peer would otherwise be the proxy and
    every user would share one bucket.
    """
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return fallback or "unknown"
