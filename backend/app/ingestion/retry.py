"""Retrying a portal request without becoming the reason it stops answering.

The failure this module exists for is the cheap one: a request that times out,
a 502 from a load balancer, a 429 because we asked twice too quickly. Those are
weather. Treating them as a broken portal costs a notice — and five in a row
costs the whole pass, because the scrape gives up after five consecutive detail
failures on the assumption that a portal refusing us will not relent.

What it deliberately does not retry is a portal answering clearly: a 404 is not
a blip, and a 403 means asking again is the worst available idea.

Backoff is exponential with jitter. The jitter is not decoration — a fixed
schedule means every retry in a batch lands at the same instant, which is the
shape of a request pattern that gets an IP blocked.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

#: Answers worth asking again. 429 is the portal pacing us; 5xx is its problem,
#: not the request's.
RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

#: Transport failures that say nothing about whether the request was valid.
RETRYABLE_ERRORS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.RemoteProtocolError,
)


def retry_after_seconds(response: httpx.Response) -> float | None:
    """The portal's own instruction, when it gives one.

    A `Retry-After` is worth more than any backoff we would compute: it is the
    only number in the exchange that reflects what the portal actually wants.
    """
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        # The header also permits an HTTP date. Not worth parsing for a hint.
        return None


async def with_retry[T](
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    what: str = "request",
) -> T:
    """Run ``call``, retrying only what is worth retrying.

    Raises the last error once the attempts are spent, so a genuinely broken
    portal still fails the notice and still counts toward giving up on the pass.
    """
    last: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS:
                raise
            last = exc
            wait = retry_after_seconds(exc.response) or _backoff(attempt, base_delay, max_delay)
        except RETRYABLE_ERRORS as exc:
            last = exc
            wait = _backoff(attempt, base_delay, max_delay)

        if attempt == attempts:
            break
        logger.info(
            "portal_retry",
            what=what,
            attempt=attempt,
            of=attempts,
            wait_seconds=round(wait, 2),
            error=type(last).__name__,
        )
        await asyncio.sleep(wait)

    assert last is not None
    raise last


def _backoff(attempt: int, base: float, ceiling: float) -> float:
    """Exponential, with full jitter so a batch does not retry in lockstep."""
    window = min(ceiling, base * (2 ** (attempt - 1)))
    return random.uniform(0, window)
