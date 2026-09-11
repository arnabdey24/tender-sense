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


async def claim_cooldown(key: str, *, seconds: int) -> int:
    """Take a shared cooldown, or report how long until it is free.

    Distinct from :func:`enforce_rate_limit` in what the caller can say
    afterwards. A counter knows only that you are over the line, which makes for
    a button that refuses without explaining; this returns the seconds left, so
    the interface can show a countdown and the person can see the control is
    working as designed rather than broken.

    Returns ``0`` when the cooldown was claimed and the work should go ahead.

    A missing Redis returns ``0`` as well. This is not the usual "availability
    beats enforcement" trade — the queue is Redis too, so whatever the caller
    was about to enqueue is going to fail on its own and say so honestly.
    """
    redis_key = f"cooldown:{key}"
    try:
        redis = await get_queue()
        claimed = await redis.set(redis_key, "1", ex=seconds, nx=True)
        if claimed:
            return 0
        remaining = await redis.ttl(redis_key)
    except Exception as exc:  # pragma: no cover - the enqueue behind this reports it
        logger.warning("cooldown_unavailable", key=key, error=str(exc))
        return 0
    # Redis answers -2 for a key that is gone — it expired in the moment between
    # the failed claim and this read, so the caller may try again at once — and
    # -1 for one with no expiry, which nothing here sets but which must not be
    # reported as a countdown that never ends.
    if remaining is None:
        return seconds
    remaining = int(remaining)
    if remaining == -2:
        return 0
    return seconds if remaining < 0 else remaining


async def cooldown_remaining(key: str) -> int:
    """Seconds until ``key`` is free, without taking it. ``0`` means now."""
    try:
        redis = await get_queue()
        remaining = await redis.ttl(f"cooldown:{key}")
    except Exception as exc:  # pragma: no cover - reading state must never 500
        logger.warning("cooldown_unavailable", key=key, error=str(exc))
        return 0
    return 0 if remaining is None or remaining < 0 else int(remaining)
