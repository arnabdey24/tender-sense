"""ARQ connection helpers shared by the API (enqueue) and the workers."""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

QUEUE_DEFAULT = "arq:queue"
QUEUE_SCRAPE = "arq:queue:scrape"
#: The schedule runs on its own queue because arq orders a queue by enqueue
#: time. A cron fires *now*, so on a shared queue it sorts behind every bulk
#: job queued earlier — and a backlog of a few thousand notices therefore
#: delays the email pump, the digests and the reminder sweep indefinitely,
#: with no failure, no retry and nothing in any error column to notice.
QUEUE_SCHEDULE = "arq:queue:schedule"

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
    )


async def get_queue() -> ArqRedis:
    """Process-wide ARQ pool used to enqueue jobs from the API."""
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_queue() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None


async def redis_healthcheck() -> bool:
    try:
        pool = await get_queue()
        await pool.ping()
    except Exception as exc:  # pragma: no cover - exercised via integration tests
        logger.warning("readiness_redis_failed", error=str(exc))
        return False
    return True
