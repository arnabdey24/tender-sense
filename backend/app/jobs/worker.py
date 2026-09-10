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

# Importing the package registers every adapter, so `adapter_key` resolves.
from app.ingestion import adapters as _adapters  # noqa: F401
from app.jobs.queue import QUEUE_DEFAULT, QUEUE_SCRAPE, redis_settings
from app.jobs.tasks.email import PUMP_CRON_SECOND, pump_email_outbox
from app.jobs.tasks.explanations import generate_explanations
from app.jobs.tasks.maintenance import (
    age_match_urgency,
    close_expired_tenders,
    mark_source_health,
    ping,
    purge_old_runs,
    refresh_fx_rates,
)
from app.jobs.tasks.matching import process_tender, rematch_org
from app.jobs.tasks.notifications import (
    alert_sources_down,
    deadline_reminder_sweep,
    digest_dispatcher,
    notify_instant,
    notify_tender_updated,
    send_daily_digest,
)
from app.jobs.tasks.reprocessing import reparse_source, reprocess_tender
from app.jobs.tasks.scraping import scrape_due_sources, scrape_source

logger = get_logger(__name__)

#: Tasks available on every queue.
COMMON_FUNCTIONS: list[Any] = [ping]

#: Only the scrape worker runs these. It is capped at one job at a time, so
#: portals are visited in series and a slow one cannot fan out into a burst.
#: Reparsing sits here too: it touches no portal, but it walks the same rows a
#: live scrape writes, and the two running at once would fight over every notice.
SCRAPE_QUEUE_FUNCTIONS: list[Any] = [*COMMON_FUNCTIONS, scrape_source, reparse_source]

#: Tasks only the default worker runs. The scrape worker must not drain the
#: outbox: it is capped at one job at a time and long scrapes would stall mail.
DEFAULT_QUEUE_FUNCTIONS: list[Any] = [
    *COMMON_FUNCTIONS,
    pump_email_outbox,
    process_tender,
    rematch_org,
    reprocess_tender,
    generate_explanations,
    scrape_due_sources,
    close_expired_tenders,
    age_match_urgency,
    mark_source_health,
    purge_old_runs,
    refresh_fx_rates,
    notify_instant,
    notify_tender_updated,
    digest_dispatcher,
    send_daily_digest,
    deadline_reminder_sweep,
    alert_sources_down,
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
        # Four passes a day, off-peak in Dhaka, to stay polite to an old portal.
        cron(scrape_due_sources, hour={2, 8, 14, 20}, minute=0, run_at_startup=False),
        # Housekeeping in the quiet hour, each a few minutes apart so a slow
        # one does not delay the next.
        cron(close_expired_tenders, hour={2}, minute=10, run_at_startup=False),
        cron(refresh_fx_rates, hour={2}, minute=15, run_at_startup=False),
        cron(purge_old_runs, hour={2}, minute=20, run_at_startup=False),
        cron(mark_source_health, hour={2}, minute=25, run_at_startup=False),
        # Urgency moves with the clock rather than with any input, so it is
        # re-derived hourly instead of waiting for a re-match that never comes.
        cron(age_match_urgency, minute={5}, run_at_startup=False),
        # Digests are due at each organization's own local time, so the
        # dispatcher wakes four times an hour and decides per tenant.
        cron(digest_dispatcher, minute={0, 15, 30, 45}, run_at_startup=False),
        # Reminders are checked hourly but sent once per offset per tender,
        # which the ledger — not this schedule — is what guarantees.
        cron(deadline_reminder_sweep, minute={35}, run_at_startup=False),
        cron(alert_sources_down, hour={2}, minute=30, run_at_startup=False),
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

    functions: list[Any] = SCRAPE_QUEUE_FUNCTIONS
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
