"""Housekeeping, and the run records that prove it happened.

None of this is glamorous. All of it is the difference between a system that
ages well and one that quietly rots: notices that never close, run tables that
grow forever, sources that stopped being scraped without anyone noticing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.ingestion.adapters.base import TenderIn
from app.ingestion.service import upsert_tender
from app.jobs.runs import JobRun, RunStatus, ScraperRun
from app.jobs.tasks.maintenance import (
    close_expired_tenders,
    mark_source_health,
    purge_old_runs,
)
from app.jobs.tracking import tracked_job
from app.modules.tenders.models import SourceHealth, Tender, TenderSource, TenderStatus


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"maint-{uuid4().hex[:8]}",
        name="Maintenance portal",
        adapter_key="manual",
        base_url="https://portal.invalid",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


async def add_tender(
    source: TenderSource, external_id: str, *, deadline_at: Any, status: TenderStatus
) -> Tender:
    async with session_scope() as session:
        fresh = await session.get(TenderSource, source.id)
        assert fresh is not None
        result = await upsert_tender(
            session,
            source=fresh,
            data=TenderIn(
                external_id=external_id,
                canonical_url=f"https://portal.invalid/{external_id}",
                title=f"Notice {external_id}",
                deadline_at=deadline_at,
                status=status,
            ),
        )
        tender = await session.get(Tender, result.tender_id)
        assert tender is not None
        await session.refresh(tender)
        return tender


async def reload(tender_id: Any) -> Tender | None:
    async with session_scope() as session:
        return await session.get(Tender, tender_id)


#: Job names these tests write. The database outlives a single test run, so
#: without a sweep the counts below would grow with every invocation.
TEST_JOB_NAMES = (
    "ancient",
    "recent",
    "counting_task",
    "exploding_task",
    "degrading_task",
    "lossy_task",
)


@pytest.fixture(autouse=True)
async def clean_job_runs() -> AsyncIterator[None]:
    async def sweep() -> None:
        async with session_scope() as session:
            await session.execute(delete(JobRun).where(JobRun.name.in_(TEST_JOB_NAMES)))

    await sweep()
    yield
    await sweep()


async def runs_named(name: str) -> list[JobRun]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(JobRun).where(JobRun.name == name).order_by(JobRun.started_at.desc())
        )
        return list(rows.all())


class TestClosingExpiredTenders:
    async def test_a_deadline_that_has_passed_closes_the_notice(self, source: TenderSource) -> None:
        """e-GP drops closed notices rather than restating them, so a notice we
        hold would stay open forever on the strength of the last page that
        mentioned it."""
        expired = await add_tender(
            source, "past", deadline_at=utcnow() - timedelta(days=2), status=TenderStatus.OPEN
        )

        await close_expired_tenders({})

        stored = await reload(expired.id)
        assert stored is not None
        assert stored.status is TenderStatus.CLOSED

    async def test_a_live_deadline_is_left_alone(self, source: TenderSource) -> None:
        live = await add_tender(
            source, "future", deadline_at=utcnow() + timedelta(days=5), status=TenderStatus.OPEN
        )

        await close_expired_tenders({})

        stored = await reload(live.id)
        assert stored is not None
        assert stored.status is TenderStatus.OPEN

    async def test_a_notice_without_a_deadline_is_not_expired(self, source: TenderSource) -> None:
        """There is nothing to have passed, so closing it would be an invention."""
        undated = await add_tender(source, "undated", deadline_at=None, status=TenderStatus.OPEN)

        await close_expired_tenders({})

        stored = await reload(undated.id)
        assert stored is not None
        assert stored.status is TenderStatus.OPEN


class TestPurgingRuns:
    async def test_it_deletes_records_past_the_window_and_keeps_the_rest(
        self, source: TenderSource
    ) -> None:
        now = utcnow()
        async with session_scope() as session:
            session.add_all(
                [
                    JobRun(
                        name="ancient",
                        status=RunStatus.SUCCEEDED,
                        started_at=now - timedelta(days=90),
                    ),
                    JobRun(name="recent", status=RunStatus.SUCCEEDED, started_at=now),
                    ScraperRun(
                        source_id=source.id,
                        status=RunStatus.SUCCEEDED,
                        started_at=now - timedelta(days=90),
                    ),
                ]
            )

        result = await purge_old_runs({}, 30)

        assert result["job_runs"] >= 1
        assert result["scraper_runs"] >= 1
        assert [run.name for run in await runs_named("ancient")] == []
        assert len(await runs_named("recent")) == 1


class TestSourceHealthSweep:
    async def test_a_source_that_stopped_being_scraped_is_marked_degraded(
        self, source: TenderSource
    ) -> None:
        """`scrape_source` records health when a run *fails*. This catches the
        other shape: runs that stopped happening at all."""
        stale = utcnow() - timedelta(days=5)
        async with session_scope() as session:
            fresh = await session.get(TenderSource, source.id)
            assert fresh is not None
            fresh.last_run_at = stale
            fresh.last_success_at = stale
            fresh.health = SourceHealth.OK

        result = await mark_source_health({})

        assert source.code in result["stale"]
        async with session_scope() as session:
            reloaded = await session.get(TenderSource, source.id)
        assert reloaded is not None
        assert reloaded.health is SourceHealth.DEGRADED

    async def test_a_source_that_never_ran_is_new_not_broken(self, source: TenderSource) -> None:
        result = await mark_source_health({})

        assert source.code not in result["stale"]
        async with session_scope() as session:
            reloaded = await session.get(TenderSource, source.id)
        assert reloaded is not None
        assert reloaded.health is SourceHealth.OK

    async def test_a_recently_successful_source_is_left_alone(self, source: TenderSource) -> None:
        async with session_scope() as session:
            fresh = await session.get(TenderSource, source.id)
            assert fresh is not None
            fresh.last_run_at = utcnow()
            fresh.last_success_at = utcnow()

        result = await mark_source_health({})

        assert source.code not in result["stale"]


class TestJobTracking:
    async def test_a_successful_run_is_written_down_with_its_result(self) -> None:
        """A job that silently stops running looks exactly like a job with
        nothing to do; the record is what tells them apart."""

        @tracked_job
        async def counting_task(ctx: dict[str, Any]) -> dict[str, Any]:
            return {"processed": 3}

        await counting_task({})

        runs = await runs_named("counting_task")
        assert len(runs) == 1
        assert runs[0].status is RunStatus.SUCCEEDED
        assert runs[0].result == {"processed": 3}
        assert runs[0].finished_at is not None
        assert runs[0].error is None

    async def test_a_task_that_raises_is_recorded_as_failed(self) -> None:
        @tracked_job
        async def exploding_task(ctx: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("the portal hung up")

        with pytest.raises(RuntimeError):
            await exploding_task({})

        runs = await runs_named("exploding_task")
        assert runs[0].status is RunStatus.FAILED
        assert "the portal hung up" in (runs[0].error or "")

    async def test_a_task_that_returns_an_error_is_not_recorded_as_success(self) -> None:
        """These tasks degrade rather than raise, so "returned normally" would
        record the failures that matter most as clean runs."""

        @tracked_job
        async def degrading_task(ctx: dict[str, Any]) -> dict[str, Any]:
            return {"error": "source_not_found"}

        await degrading_task({})

        runs = await runs_named("degrading_task")
        assert runs[0].status is RunStatus.FAILED
        assert runs[0].error == "source_not_found"

    async def test_a_run_that_lost_some_records_is_partial(self) -> None:
        @tracked_job
        async def lossy_task(ctx: dict[str, Any]) -> dict[str, Any]:
            return {"created": 9, "failed": 1}

        await lossy_task({})

        runs = await runs_named("lossy_task")
        assert runs[0].status is RunStatus.PARTIAL

    async def test_the_task_keeps_its_name_so_arq_can_still_enqueue_it(self) -> None:
        """arq registers by ``__name__`` and enqueues by that string; a renamed
        wrapper would make every existing enqueue call miss."""

        @tracked_job
        async def scrape_something(ctx: dict[str, Any]) -> dict[str, Any]:
            return {}

        assert scrape_something.__name__ == "scrape_something"
