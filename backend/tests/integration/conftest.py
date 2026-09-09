"""Integration fixtures. Tests skip when Postgres/Redis are not reachable."""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import pytest

from app.core.config import settings
from app.db.session import dispose_engine
from app.jobs.queue import close_queue, get_queue


def _reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def require_services() -> None:
    missing = []
    if not _reachable(settings.postgres_host, settings.postgres_port):
        missing.append(f"postgres({settings.postgres_host}:{settings.postgres_port})")
    if not _reachable(settings.redis_host, settings.redis_port):
        missing.append(f"redis({settings.redis_host}:{settings.redis_port})")
    if missing:
        pytest.skip(
            f"integration services unavailable: {', '.join(missing)}; "
            "run `make dev` or set POSTGRES_HOST/REDIS_HOST",
            allow_module_level=True,
        )


@pytest.fixture(autouse=True)
async def isolate_connections() -> AsyncIterator[None]:
    """Give every test its own database engine and Redis pool.

    Both are cached at module level for the lifetime of a process, but pytest
    runs each async test on a fresh event loop. Reusing a pool bound to a
    closed loop fails with confusing "Event loop is closed" errors, so the
    caches are dropped after each test.

    Being autouse, this is set up first and therefore torn down last, after any
    client fixture has finished with the connections.
    """
    yield
    await close_queue()
    await dispose_engine()


@pytest.fixture(autouse=True)
async def reset_rate_limits() -> AsyncIterator[None]:
    """Clear rate-limit counters so one test's attempts cannot throttle the next.

    Every test shares a client address. The limiters themselves are exercised
    deliberately in the rate-limiting tests.
    """
    await _clear_rate_limits()
    yield


async def _clear_rate_limits() -> None:
    redis = await get_queue()
    keys = [key async for key in redis.scan_iter("ratelimit:*")]
    if keys:
        await redis.delete(*keys)
