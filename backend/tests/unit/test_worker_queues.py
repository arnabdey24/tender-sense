"""Which queue each kind of work runs on.

The arrangement these pin was bought with an outage: invitations and a
verification email sat unsent for hours while a backlog of a few thousand
notices drained ahead of them. Nothing failed, nothing retried, and no error
column had anything in it — arq simply orders a queue by enqueue time, so a
cron firing now sorts behind every bulk job queued earlier.

So the rule is structural rather than a matter of tuning: the schedule does not
share a queue with work that can arrive in bulk.
"""

from __future__ import annotations

from app.jobs.queue import QUEUE_DEFAULT, QUEUE_SCHEDULE, QUEUE_SCRAPE
from app.jobs.worker import (
    ScheduleWorkerSettings,
    ScrapeWorkerSettings,
    WorkerSettings,
)


def _names(settings_cls: type) -> set[str]:
    return {f.__name__ for f in settings_cls.functions}


class TestQueuesAreDistinct:
    def test_each_worker_owns_one_queue(self) -> None:
        queues = {
            WorkerSettings.queue_name,
            ScheduleWorkerSettings.queue_name,
            ScrapeWorkerSettings.queue_name,
        }

        assert queues == {QUEUE_DEFAULT, QUEUE_SCHEDULE, QUEUE_SCRAPE}


class TestTheScheduleIsIsolated:
    def test_only_the_schedule_worker_carries_crons(self) -> None:
        """The whole point. A cron registered on the default worker would be
        queued behind the bulk backlog again."""
        assert ScheduleWorkerSettings.cron_jobs
        assert WorkerSettings.cron_jobs == []
        assert ScrapeWorkerSettings.cron_jobs == []

    def test_every_cron_target_is_registered_on_its_own_worker(self) -> None:
        """arq resolves a cron by name against `functions`. A cron whose target
        is missing there fails at run time, not at import."""
        registered = _names(ScheduleWorkerSettings)
        # arq names a cron job `cron:<function>`; the function itself has to be
        # registered as well, or nothing can enqueue it by name — which is how
        # the operator's "run now" controls reach these.
        missing = [
            job.name
            for job in ScheduleWorkerSettings.cron_jobs
            if job.name.removeprefix("cron:") not in registered
        ]

        assert missing == []

    def test_the_digest_fan_out_stays_on_the_schedule_queue(self) -> None:
        """`digest_dispatcher` enqueues `send_daily_digest`. On the default
        queue that digest would arrive a day late, which is the failure this
        queue exists to prevent."""
        assert "send_daily_digest" in _names(ScheduleWorkerSettings)

    def test_bulk_work_is_not_on_the_schedule_queue(self) -> None:
        """`process_tender` is the job that arrives in thousands. Registering
        it here would rebuild the traffic jam inside the schedule."""
        assert "process_tender" not in _names(ScheduleWorkerSettings)
        assert "process_tender" in _names(WorkerSettings)


class TestSettingsAreDeclaredNotInherited:
    def test_each_class_declares_what_arq_reads(self) -> None:
        """arq reads `settings_cls.__dict__`, so an inherited attribute is
        silently ignored — `redis_settings` falling back to localhost is the
        one that bites."""
        for cls in (WorkerSettings, ScheduleWorkerSettings, ScrapeWorkerSettings):
            for attribute in ("functions", "queue_name", "redis_settings", "max_jobs"):
                assert attribute in cls.__dict__, f"{cls.__name__} must declare {attribute}"
