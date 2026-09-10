"""Nightly housekeeping: closing stale notices, purging runs, refreshing rates.

None of this is glamorous and all of it is the difference between a system that
ages well and one that quietly rots. A notice whose deadline passed a month ago
still showing as open wastes a bidder's attention; run records kept forever turn
a small table into the largest one in the database; a missing exchange rate
makes every cross-currency rule undecidable.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

import httpx
from sqlalchemy import CursorResult, delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.jobs.runs import JobRun, ScraperRun
from app.jobs.tracking import tracked_job
from app.modules.matching.models import TenderMatch
from app.modules.matching.scoring import urgency_for
from app.modules.orgs.models import Organization
from app.modules.rules.models import FxRate
from app.modules.tenders.models import SourceHealth, Tender, TenderSource, TenderStatus

logger = get_logger(__name__)


async def ping(ctx: dict[str, Any]) -> dict[str, Any]:
    """Round-trip check: the worker is consuming jobs and can reach Postgres."""
    async with session_scope() as session:
        database_ok = (await session.execute(text("SELECT 1"))).scalar_one() == 1

    result = {
        "pong": True,
        "database": database_ok,
        "job_id": ctx.get("job_id"),
        "at": utcnow().isoformat(),
    }
    logger.info("worker_ping", **result)
    return result


@tracked_job
async def close_expired_tenders(ctx: dict[str, Any]) -> dict[str, Any]:
    """Mark notices closed once their deadline has passed.

    Portals are inconsistent about doing this themselves — e-GP drops closed
    notices from the listing rather than restating them, so a notice we hold
    would stay "open" forever on the strength of the last page that mentioned
    it. Only tenders that carry a deadline are touched: without one there is
    nothing to have expired.
    """
    now = utcnow()
    async with session_scope() as session:
        result = cast(
            CursorResult[Any],
            await session.execute(
                update(Tender)
                .where(
                    Tender.status == TenderStatus.OPEN,
                    Tender.deadline_at.is_not(None),
                    Tender.deadline_at < now,
                )
                .values(status=TenderStatus.CLOSED)
            ),
        )
        closed = result.rowcount or 0

    logger.info("tenders_closed", closed=closed)
    return {"closed": closed}


@tracked_job
async def age_match_urgency(ctx: dict[str, Any]) -> dict[str, Any]:
    """Re-derive urgency for open matches as the clock moves.

    Urgency is the one part of a match that changes with nothing but time, so
    it is the one thing a fingerprint guard cannot catch. Without this sweep a
    tender scored three weeks ago still reads "normal" on the morning it is due.
    Recomputed in the organization's own timezone, because "closes tomorrow" is
    a local statement.
    """
    updated = 0
    async with session_scope() as session:
        rows = await session.execute(
            select(TenderMatch, Tender.deadline_at, Organization.timezone)
            .join(Tender, Tender.id == TenderMatch.tender_id)
            .join(Organization, Organization.id == TenderMatch.org_id)
            .where(Tender.status == TenderStatus.OPEN)
        )
        for match, deadline_at, timezone in rows.all():
            urgency = urgency_for(deadline_at, timezone=timezone)
            if match.urgency is not urgency:
                match.urgency = urgency
                updated += 1

    logger.info("match_urgency_aged", updated=updated)
    return {"updated": updated}


@tracked_job
async def purge_old_runs(ctx: dict[str, Any], retention_days: int | None = None) -> dict[str, Any]:
    """Delete run records past the retention window.

    The runs worth keeping are the recent ones: they answer "is ingestion
    working right now". A year of them answers nothing anyone asks and costs a
    table scan on every admin page.
    """
    days = retention_days or settings.job_run_retention_days
    cutoff = utcnow() - timedelta(days=days)

    async with session_scope() as session:
        jobs = cast(
            CursorResult[Any],
            await session.execute(delete(JobRun).where(JobRun.started_at < cutoff)),
        ).rowcount
        scrapes = cast(
            CursorResult[Any],
            await session.execute(delete(ScraperRun).where(ScraperRun.started_at < cutoff)),
        ).rowcount

    result = {"job_runs": jobs or 0, "scraper_runs": scrapes or 0, "retention_days": days}
    logger.info("runs_purged", **result)
    return result


@tracked_job
async def mark_source_health(ctx: dict[str, Any]) -> dict[str, Any]:
    """Flag sources that have gone quiet.

    ``scrape_source`` records health when a run *fails*. This catches the other
    shape of failure: runs that stopped happening at all — a crashed cron, a
    disabled queue, a source whose adapter was renamed — where the last run on
    record succeeded and nothing ever contradicted it.
    """
    now = utcnow()
    cutoff = now - timedelta(hours=settings.source_stale_hours)
    stale: list[str] = []

    async with session_scope() as session:
        sources = list(
            (
                await session.scalars(select(TenderSource).where(TenderSource.enabled.is_(True)))
            ).all()
        )
        for source in sources:
            last_success = source.last_success_at
            if last_success is not None and last_success >= cutoff:
                continue
            # Never scraped and never tried is a new source, not a broken one.
            if last_success is None and source.last_run_at is None:
                continue
            if source.health is SourceHealth.OK:
                source.health = SourceHealth.DEGRADED
            stale.append(source.code)

    logger.info("source_health_swept", stale=stale, cutoff_hours=settings.source_stale_hours)
    return {"checked": len(stale), "stale": stale}


@tracked_job
async def refresh_fx_rates(ctx: dict[str, Any]) -> dict[str, Any]:
    """Pull today's exchange rates so money rules can compare across currencies.

    A failure leaves yesterday's rates in place rather than clearing them: a
    stale rate is a small error in a comparison, while no rate at all makes
    every cross-currency rule undecidable and floods a customer's feed with
    "needs verification".
    """
    base = settings.fx_base_currency.upper()
    if not settings.fx_rates_url:
        return {"skipped": "fx_rates_url is not configured", "base": base}

    url = f"{settings.fx_rates_url.rstrip('/')}/{base}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            response = await client.get(url, headers={"User-Agent": settings.scraper_user_agent})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("fx_refresh_failed", url=url, error=str(exc)[:200])
        return {"base": base, "error": str(exc)[:200]}

    rates = payload.get("rates") or payload.get("conversion_rates") or {}
    if not isinstance(rates, dict) or not rates:
        return {"base": base, "error": "The rates endpoint returned no rates."}

    as_of = date.today()
    stored = 0
    async with session_scope() as session:
        for currency, rate in rates.items():
            if not isinstance(rate, int | float) or rate <= 0:
                continue
            await session.execute(
                pg_insert(FxRate)
                .values(
                    base=base,
                    currency=str(currency).upper()[:3],
                    rate=float(rate),
                    as_of=as_of,
                    source="er-api",
                    fetched_at=utcnow(),
                )
                .on_conflict_do_update(
                    index_elements=[FxRate.base, FxRate.currency, FxRate.as_of],
                    set_={"rate": float(rate), "fetched_at": utcnow(), "source": "er-api"},
                )
            )
            stored += 1

    logger.info("fx_refreshed", base=base, currencies=stored)
    return {"base": base, "currencies": stored, "as_of": as_of.isoformat()}
