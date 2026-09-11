"""Pulling notices from a portal into the shared pool.

One pass per source. The shape is deliberately conservative, because the failure
that matters is not a crash — it is a portal deciding we are abusive and cutting
us off, which takes the whole product with it.

* Consecutive detail failures abort the run. A portal that has started refusing
  us will not relent because we asked forty more times.
* Every notice is committed on its own, so one unparseable record costs one
  record rather than the whole page.
* Health is derived from consecutive failures, not from the last run alone —
  one timeout is weather, five in a row is a broken portal.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import record_source_health
from app.core.time import utcnow
from app.db.session import session_scope
from app.ingestion.adapters import ADAPTERS, NoticeRef, build_adapter
from app.ingestion.service import UpsertOutcome, upsert_tender
from app.jobs.queue import QUEUE_SCRAPE, get_queue
from app.jobs.runs import RunStatus, ScraperRun
from app.jobs.tasks.matching import enqueue_processing
from app.jobs.tracking import tracked_job
from app.modules.tenders.models import SourceHealth, TenderSource

logger = get_logger(__name__)

#: Consecutive detail failures before a run gives up on the portal.
MAX_CONSECUTIVE_FAILURES = 5

#: Failed runs in a row before a source is called down rather than degraded.
FAILURES_BEFORE_DOWN = 3

#: Re-ask for a day either side of the last success. A notice published moments
#: before the previous run finished would otherwise never be seen.
OVERLAP = timedelta(days=1)


async def _recent_external_ids(
    session: AsyncSession, source_id: UUID, limit: int = 500
) -> list[str]:
    """Identifiers already held, newest first.

    Handed to the adapter so it can stop walking pages the moment it recognises
    one — the only reliable bound on a portal with no trustworthy date filter.
    """
    from app.modules.tenders.models import Tender

    rows = await session.scalars(
        select(Tender.external_id)
        .where(Tender.source_id == source_id)
        .order_by(Tender.first_seen_at.desc())
        .limit(limit)
    )
    return list(rows.all())


async def _record_health(
    session: AsyncSession, source: TenderSource, *, succeeded: bool, ran_at: Any
) -> None:
    source.last_run_at = ran_at
    if succeeded:
        source.last_success_at = ran_at
        source.consecutive_failures = 0
        source.health = SourceHealth.OK
    else:
        source.consecutive_failures += 1
        source.health = (
            SourceHealth.DOWN
            if source.consecutive_failures >= FAILURES_BEFORE_DOWN
            else SourceHealth.DEGRADED
        )
    record_source_health(source.code, source.health.value)
    await session.flush()


async def _fetch_one(adapter: Any, ref: NoticeRef) -> tuple[list[Any], Any]:
    """One notice's detail and its normalised form, for gathering in a batch."""
    documents = await adapter.fetch_detail(ref)
    return documents, adapter.normalize(ref, documents)


async def _store_one(
    *,
    source_id: str,
    source_code: str,
    ref: NoticeRef,
    data: Any,
    documents: list[Any],
    result: dict[str, Any],
    only_org_id: str | None = None,
) -> None:
    """Commit one notice and queue whatever it earns.

    One notice per transaction: an unparseable record must cost one record, not
    the page it arrived on. And the pipeline is queued here, beside the commit
    that created the row, rather than from a list walked after the loop — a
    pass cancelled at the job timeout once left 1,122 committed notices with
    nothing scheduled to extract, embed or match any of them.
    """
    try:
        async with session_scope() as session:
            fresh_source = await session.get(TenderSource, UUID(source_id))
            if fresh_source is None:
                return
            outcome = await upsert_tender(
                session, source=fresh_source, data=data, documents=documents
            )

        if outcome.outcome is UpsertOutcome.CREATED:
            result["created"] += 1
        elif outcome.outcome is UpsertOutcome.UPDATED:
            result["updated"] += 1
            # Only the upsert knows an amendment happened; by the time the
            # pipeline sees the row it looks like any other notice.
            await _enqueue_update_notice(str(outcome.tender_id))
            result["amended"] += 1
        else:
            result["unchanged"] += 1

        if outcome.needs_processing:
            await enqueue_processing(str(outcome.tender_id), only_org_id=only_org_id)
            result["queued"] += 1
    except Exception as exc:
        result["failed"] += 1
        logger.warning(
            "notice_not_stored",
            source=source_code,
            notice_id=ref.external_id,
            error=f"{type(exc).__name__}: {exc}"[:200],
        )


@tracked_job
async def scrape_source(
    ctx: dict[str, Any],
    source_id: str,
    limit_pages: int | None = None,
    only_org_id: str | None = None,
) -> dict[str, Any]:
    """Fetch, store and upsert one portal's recent notices.

    ``only_org_id`` scopes the analysis that follows to one tenant — what a
    manual sync does. The person who pressed the button gets their grades now;
    everyone else is served by the six-hourly sweep, which is what keeps a
    scoped pass from hiding notices from the rest of the deployment.
    """
    started = utcnow()
    result: dict[str, Any] = {
        "source_id": source_id,
        "notices_seen": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
    }

    async with session_scope() as session:
        source = await session.get(TenderSource, UUID(source_id))
        if source is None:
            return result | {"error": "source_not_found"}
        if not source.enabled:
            return result | {"error": "source_disabled"}

        run = ScraperRun(source_id=source.id, started_at=started, status=RunStatus.RUNNING)
        session.add(run)
        await session.flush()
        run_id = run.id

        seen_ids = await _recent_external_ids(session, source.id)
        since = (source.last_success_at - OVERLAP) if source.last_success_at else None
        config = dict(source.config or {})
        adapter_key = source.adapter_key
        source_code = source.code
        base_url = source.base_url

    try:
        adapter = build_adapter(adapter_key, base_url=base_url, config=config)
    except LookupError as exc:
        async with session_scope() as session:
            await _finish(session, run_id, result, status=RunStatus.FAILED, error=str(exc))
            fresh = await session.get(TenderSource, UUID(source_id))
            if fresh:
                await _record_health(session, fresh, succeeded=False, ran_at=started)
        return result | {"error": str(exc)}

    pages = limit_pages or int(config.get("max_pages", 20))
    consecutive_failures = 0
    result["queued"] = 0
    result["amended"] = 0
    fatal: str | None = None

    try:
        refs: list[NoticeRef] = []
        async for ref in adapter.list_notices(
            since=since, cursor={"seen_ids": seen_ids}, limit_pages=pages
        ):
            refs.append(ref)
        result["notices_seen"] = len(refs)

        # Details are fetched in bounded batches rather than one at a time.
        #
        # The cost of a pass is dominated by the politeness delay between
        # requests, not by the portal's latency: two thousand notices at two
        # seconds each is over an hour of deliberate waiting, which is what put
        # e-GP past the job timeout. Fetching `concurrency` of them at once
        # divides that wait without shortening it for any single request.
        #
        # The default is 1, which is exactly the behaviour this replaces. It is
        # opt-in per source because the right number is a property of the
        # portal, not of us — and the failure this whole module is shaped
        # around is a portal deciding we are abusive.
        concurrency = max(1, int(config.get("request_concurrency", 1)))

        for batch_start in range(0, len(refs), concurrency):
            batch = refs[batch_start : batch_start + concurrency]
            fetched = await asyncio.gather(
                *(_fetch_one(adapter, ref) for ref in batch), return_exceptions=True
            )

            # `return_exceptions=True` collects cancellation as a value rather
            # than propagating it, which would quietly turn "the worker stopped
            # this job" into "a few notices failed" and leave the run recorded
            # as a partial success. Cancellation is re-raised before anything
            # else in the batch is considered.
            for outcome_or_error in fetched:
                if isinstance(outcome_or_error, asyncio.CancelledError):
                    raise outcome_or_error

            for ref, outcome_or_error in zip(batch, fetched, strict=True):
                if isinstance(outcome_or_error, BaseException):
                    failure = outcome_or_error
                    consecutive_failures += 1
                    result["failed"] += 1
                    logger.warning(
                        "notice_failed",
                        source=source_code,
                        notice_id=ref.external_id,
                        error=f"{type(failure).__name__}: {failure}"[:200],
                    )
                    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                        fatal = f"Gave up after {consecutive_failures} consecutive failures."
                        break
                    continue

                documents, data = outcome_or_error
                await _store_one(
                    source_id=source_id,
                    source_code=source_code,
                    ref=ref,
                    data=data,
                    documents=documents,
                    result=result,
                    only_org_id=only_org_id,
                )
                consecutive_failures = 0
            if fatal:
                break

    except asyncio.CancelledError:
        # The worker's job timeout cancels the task, and a cancellation that
        # is not handled leaves the run row saying "running" for ever: the
        # health never updates, and the sync control reports a pass in flight
        # that nothing will ever finish. Record the outcome, then re-raise so
        # the worker still sees a cancelled job rather than a completed one.
        async with session_scope() as session:
            await _finish(
                session,
                run_id,
                result,
                status=RunStatus.FAILED,
                error=f"Cancelled after the worker's {settings.scrape_job_timeout_seconds}s "
                "job timeout. Notices already committed were queued for processing.",
            )
            fresh = await session.get(TenderSource, UUID(source_id))
            if fresh is not None:
                await _record_health(session, fresh, succeeded=False, ran_at=started)
        logger.warning("scrape_cancelled", source=source_code, **result)
        raise
    except Exception as exc:
        # `str(exc)` is empty for a bare timeout, which produced failed runs
        # carrying no reason at all — the one thing a run record exists to
        # supply. The type is never empty, so it leads.
        detail = str(exc).strip()
        fatal = f"{type(exc).__name__}: {detail}"[:500] if detail else type(exc).__name__
        logger.warning("scrape_failed", source=source_code, error=fatal)

    succeeded = fatal is None
    status = (
        RunStatus.FAILED
        if not succeeded
        else (RunStatus.PARTIAL if result["failed"] else RunStatus.SUCCEEDED)
    )

    async with session_scope() as session:
        await _finish(session, run_id, result, status=status, error=fatal)
        fresh = await session.get(TenderSource, UUID(source_id))
        if fresh is not None:
            await _record_health(session, fresh, succeeded=succeeded, ran_at=started)
            if succeeded:
                # Remember the newest identifiers so the next run can stop early.
                fresh.cursor = {"last_run_at": started.isoformat()}
                await session.flush()

    result["status"] = status.value
    if fatal:
        result["error"] = fatal
    logger.info("scrape_finished", source=source_code, **result)
    return result


async def _finish(
    session: AsyncSession,
    run_id: UUID,
    result: dict[str, Any],
    *,
    status: RunStatus,
    error: str | None,
) -> None:
    run = await session.get(ScraperRun, run_id)
    if run is None:
        return
    run.status = status
    run.finished_at = utcnow()
    run.notices_seen = int(result.get("notices_seen", 0))
    run.created = int(result.get("created", 0))
    run.updated = int(result.get("updated", 0))
    run.unchanged = int(result.get("unchanged", 0))
    run.failed = int(result.get("failed", 0))
    run.error = error
    await session.flush()


async def enqueue_scrape_source(
    source_id: UUID, code: str, *, only_org_id: str | None = None
) -> str | None:
    """Put one portal on the scrape queue, and say whether it went.

    Deduplicated on the source, so a second request while a pass is queued or
    running is a no-op rather than a second visit to the portal. Every caller
    that starts a scrape goes through here — the cron dispatch, the operator's
    per-source button and the members' sync — so there is one dedupe convention
    rather than three that have to agree.

    Returns the job id, or ``None`` when the job was already queued or Redis is
    unreachable; a caller that reports "queued" must only do so if it was.

    ``only_org_id`` narrows the *analysis* to one tenant, which is what a
    hand-pressed sync wants. Fetching and storing are unchanged: the notices
    land in the shared pool either way.
    """
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(
            "scrape_source",
            str(source_id),
            None,
            only_org_id,
            _queue_name=QUEUE_SCRAPE,
            _job_id=f"scrape:{source_id}",
        )
    except Exception as exc:  # pragma: no cover - Redis down must not 500
        logger.warning("scrape_enqueue_failed", source=code, error=str(exc))
        return None
    return job.job_id if job else None


async def _enqueue_update_notice(tender_id: str) -> None:
    """Tell organizations bidding on this tender that the portal changed it."""
    try:
        queue = await get_queue()
        await queue.enqueue_job("notify_tender_updated", tender_id, _job_id=f"updated:{tender_id}")
    except Exception as exc:  # pragma: no cover - Redis down must not lose the row
        logger.warning("update_notice_enqueue_failed", tender_id=tender_id, error=str(exc))


@tracked_job
async def scrape_all_sources(ctx: dict[str, Any]) -> dict[str, Any]:
    """Queue a scrape for every enabled source.

    Each source is a separate job on the scrape queue, which is capped at one
    at a time — so portals are visited in series rather than all at once.

    Named for what it does. It was ``scrape_due_sources``, which reads as
    though it consults a schedule and skips portals that are not yet due — it
    never has. That mattered on the operator's job list, where someone wanting
    a first pull, or the newest notices before the next cron tick, would fairly
    read "due" as "this will do nothing right now" and go looking for a control
    that does not exist. Nothing else changes: this is the same dispatch the
    cron has always called four times a day.
    """
    async with session_scope() as session:
        sources = list(
            (
                await session.scalars(select(TenderSource).where(TenderSource.enabled.is_(True)))
            ).all()
        )

    queued = 0
    for source in sources:
        if source.adapter_key not in ADAPTERS:
            continue
        if await enqueue_scrape_source(source.id, source.code):
            queued += 1

    logger.info("scrape_dispatch", sources=len(sources), queued=queued)
    return {"sources": len(sources), "queued": queued}


async def scrape_due_sources(ctx: dict[str, Any]) -> dict[str, Any]:
    """Deprecated alias, kept so a job already queued under the old name still
    runs after a deploy that renames it. Remove once the queue has drained."""
    return await scrape_all_sources(ctx)
