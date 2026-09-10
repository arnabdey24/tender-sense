"""ARQ worker entrypoints.

Two worker processes run from the same codebase:

* ``arq app.jobs.worker.WorkerSettings``       — default queue, owns the cron schedule
* ``arq app.jobs.worker.ScrapeWorkerSettings`` — scrape queue, one job at a time

Note: arq reads settings from ``settings_cls.__dict__``, so **inherited
attributes are ignored**. Each class must therefore declare every attribute it
needs; subclassing one settings class from the other silently drops whatever it
does not redeclare (including ``redis_settings``, which then falls back to
localhost). ``_shared()`` keeps the common values in one place instead.
"""

from __future__ import annotations

from typing import Any

from arq import cron

from app.core.logging import configure_logging, get_logger

# Importing the aggregator configures the whole SQLAlchemy registry. Without it
# a task that touches only one module's models cannot resolve foreign keys into
# another module's tables.
from app.db import models as _models  # noqa: F401
from app.db.session import dispose_engine
from app.jobs.queue import QUEUE_DEFAULT, QUEUE_SCRAPE, redis_settings
from app.jobs.tasks.email import PUMP_CRON_SECOND, pump_email_outbox
from app.jobs.tasks.explanations import generate_explanations
from app.jobs.tasks.maintenance import ping
from app.jobs.tasks.matching import process_tender, rematch_org

logger = get_logger(__name__)

#: Tasks available on every queue.
COMMON_FUNCTIONS: list[Any] = [ping]

#: Tasks only the default worker runs. The scrape worker must not drain the
#: outbox: it is capped at one job at a time and long scrapes would stall mail.
DEFAULT_QUEUE_FUNCTIONS: list[Any] = [
    *COMMON_FUNCTIONS,
    pump_email_outbox,
    process_tender,
    rematch_org,
    generate_explanations,
]


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    logger.info("worker_started", queue=ctx.get("queue"))


async def shutdown(ctx: dict[str, Any]) -> None:
    await dispose_engine()
    logger.info("worker_stopped", queue=ctx.get("queue"))


class WorkerSettings:
    """Default queue: AI, matching, notifications, maintenance."""

    functions: list[Any] = DEFAULT_QUEUE_FUNCTIONS
    cron_jobs: list[Any] = [
        cron(pump_email_outbox, second=set(PUMP_CRON_SECOND), run_at_startup=False),
    ]
    queue_name = QUEUE_DEFAULT
    #: Seeds arq's job context so tasks and log lines know which queue they ran on.
    ctx: dict[str, Any] = {"queue": QUEUE_DEFAULT}
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 600
    max_tries = 5
    keep_result = 3600
    health_check_interval = 30


class ScrapeWorkerSettings:
    """Scrape queue: portal ingestion, one run at a time.

    Deliberately not a subclass of :class:`WorkerSettings` — see module docstring.
    """

    functions: list[Any] = COMMON_FUNCTIONS
    cron_jobs: list[Any] = []
    queue_name = QUEUE_SCRAPE
    ctx: dict[str, Any] = {"queue": QUEUE_SCRAPE}
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 1
    job_timeout = 3600
    max_tries = 3
    keep_result = 3600
    health_check_interval = 30
