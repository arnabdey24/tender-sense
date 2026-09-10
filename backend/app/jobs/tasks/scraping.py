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

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.ingestion.adapters import ADAPTERS, NoticeRef, build_adapter
from app.ingestion.service import UpsertOutcome, upsert_tender
from app.jobs.queue import get_queue
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
    await session.flush()


@tracked_job
async def scrape_source(
    ctx: dict[str, Any], source_id: str, limit_pages: int | None = None
) -> dict[str, Any]:
    """Fetch, store and upsert one portal's recent notices."""
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
    new_tender_ids: list[str] = []
    fatal: str | None = None

    try:
        refs: list[NoticeRef] = []
        async for ref in adapter.list_notices(
            since=since, cursor={"seen_ids": seen_ids}, limit_pages=pages
        ):
            refs.append(ref)
        result["notices_seen"] = len(refs)

        for ref in refs:
            try:
                documents = await adapter.fetch_detail(ref)
                data = adapter.normalize(ref, documents)
            except Exception as exc:
                consecutive_failures += 1
                result["failed"] += 1
                logger.warning(
                    "notice_failed",
                    source=source_code,
                    notice_id=ref.external_id,
                    error=str(exc)[:200],
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    fatal = f"Gave up after {consecutive_failures} consecutive failures."
                    break
                continue

            consecutive_failures = 0
            try:
                # One notice per transaction: an unparseable record must cost
                # one record, not the page it arrived on.
                async with session_scope() as session:
                    fresh_source = await session.get(TenderSource, UUID(source_id))
                    if fresh_source is None:
                        break
                    outcome = await upsert_tender(
                        session, source=fresh_source, data=data, documents=documents
                    )
                if outcome.outcome is UpsertOutcome.CREATED:
                    result["created"] += 1
                elif outcome.outcome is UpsertOutcome.UPDATED:
                    result["updated"] += 1
                else:
                    result["unchanged"] += 1
                if outcome.needs_processing:
                    new_tender_ids.append(str(outcome.tender_id))
            except Exception as exc:
                result["failed"] += 1
                logger.warning(
                    "notice_not_stored",
                    source=source_code,
                    notice_id=ref.external_id,
                    error=str(exc)[:200],
                )
    except Exception as exc:
        fatal = str(exc)[:500]
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

    # Enqueue rather than process inline: the scrape worker runs one job at a
    # time, and holding it open through extraction would stall the next portal.
    for tender_id in new_tender_ids:
        await enqueue_processing(tender_id)

    result["queued"] = len(new_tender_ids)
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


@tracked_job
async def scrape_due_sources(ctx: dict[str, Any]) -> dict[str, Any]:
    """Queue a scrape for every enabled source.

    Each source is a separate job on the scrape queue, which is capped at one
    at a time — so portals are visited in series rather than all at once.
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
        try:
            queue = await get_queue()
            await queue.enqueue_job(
                "scrape_source",
                str(source.id),
                _queue_name="arq:queue:scrape",
                _job_id=f"scrape:{source.id}",
            )
            queued += 1
        except Exception as exc:
            logger.warning("scrape_enqueue_failed", source=source.code, error=str(exc))

    logger.info("scrape_dispatch", sources=len(sources), queued=queued)
    return {"sources": len(sources), "queued": queued}
