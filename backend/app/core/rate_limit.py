"""Fixed-window rate limiting backed by Redis.

Two distinct jobs share one mechanism.

**Guessing** is cheap on the unauthenticated endpoints — login, password reset,
verification resends — so those are capped per address and per IP.

**Work** is expensive on a handful of authenticated ones. A rule preview scans
hundreds of tenders, a re-match re-scores the whole open pool, and an
explanation costs model tokens from a shared daily budget. None of those is an
attack; a customer holding down a button is enough to make a single VM
unresponsive for everyone else on it.

Redis being unavailable must never lock users out, so a failure to reach it
allows the request and logs a warning. Availability beats enforcement: the
worst case of allowing is a slow minute, the worst case of denying is an
outage nobody can sign in to fix.
"""

from __future__ import annotations

from uuid import UUID

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


async def limit_org_work(
    org_id: UUID, *, operation: str, limit: int, window_seconds: int = 3600
) -> None:
    """Cap an expensive operation per organization.

    Keyed by organization rather than by user, because the cost lands on the
    shared machine and five colleagues each pressing a button once is exactly
    the same load as one person pressing it five times.
    """
    await enforce_rate_limit(
        f"{operation}:{org_id}",
        limit=limit,
        window_seconds=window_seconds,
        message=(
            f"That is a lot of {operation.replace('-', ' ')} requests in a short time. "
            "Give the last one a moment to finish."
        ),
    )
