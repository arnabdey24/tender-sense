"""Guards on the ARQ worker settings classes.

arq builds its Worker from ``settings_cls.__dict__``, which ignores inherited
attributes. A subclass therefore silently loses anything it does not redeclare —
most damagingly ``redis_settings``, which then defaults to localhost and makes
the worker crash-loop in Docker. These tests assert what arq actually reads.
"""

from __future__ import annotations

import pytest
from arq.worker import get_kwargs

from app.core.config import settings
from app.jobs.queue import QUEUE_DEFAULT, QUEUE_SCRAPE
from app.jobs.worker import ScrapeWorkerSettings, WorkerSettings

SETTINGS_CLASSES = [WorkerSettings, ScrapeWorkerSettings]


@pytest.mark.parametrize("settings_cls", SETTINGS_CLASSES, ids=["default", "scrape"])
def test_arq_receives_redis_settings(settings_cls: type) -> None:
    redis = get_kwargs(settings_cls).get("redis_settings")

    assert redis is not None, f"{settings_cls.__name__} would fall back to localhost"
    assert redis.host == settings.redis_host
    assert redis.port == settings.redis_port


@pytest.mark.parametrize("settings_cls", SETTINGS_CLASSES, ids=["default", "scrape"])
def test_arq_receives_lifecycle_hooks_and_functions(settings_cls: type) -> None:
    kwargs = get_kwargs(settings_cls)

    assert kwargs["functions"], f"{settings_cls.__name__} registers no tasks"
    assert kwargs["on_startup"] is not None
    assert kwargs["on_shutdown"] is not None


def test_the_two_workers_consume_different_queues() -> None:
    default_queue = get_kwargs(WorkerSettings)["queue_name"]
    scrape_queue = get_kwargs(ScrapeWorkerSettings)["queue_name"]

    assert (default_queue, scrape_queue) == (QUEUE_DEFAULT, QUEUE_SCRAPE)


@pytest.mark.parametrize(
    ("settings_cls", "expected_queue"),
    [(WorkerSettings, QUEUE_DEFAULT), (ScrapeWorkerSettings, QUEUE_SCRAPE)],
    ids=["default", "scrape"],
)
def test_job_context_names_the_queue(settings_cls: type, expected_queue: str) -> None:
    """Tasks and log lines need to know which queue they ran on."""
    assert get_kwargs(settings_cls)["ctx"] == {"queue": expected_queue}


def test_scrape_worker_runs_one_job_at_a_time() -> None:
    """Chromium is memory-hungry; concurrent scrapes would exhaust the VM."""
    assert get_kwargs(ScrapeWorkerSettings)["max_jobs"] == 1


def test_settings_classes_do_not_inherit_from_each_other() -> None:
    assert not issubclass(ScrapeWorkerSettings, WorkerSettings)
    assert not issubclass(WorkerSettings, ScrapeWorkerSettings)


def test_worker_import_configures_every_model() -> None:
    """A task touching one module's models must still resolve foreign keys into
    another module's tables. The worker entrypoint imports the aggregator to
    guarantee that; without it the outbox pump fails on `email_outbox.org_id`.
    """
    from sqlalchemy.orm import configure_mappers

    import app.jobs.worker  # noqa: F401  (import is the thing under test)
    from app.db.base import Base

    configure_mappers()

    assert {"users", "organizations", "memberships", "email_outbox"} <= set(Base.metadata.tables)
