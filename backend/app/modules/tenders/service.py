"""Presentation logic for the tender pool."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.core.rate_limit import claim_cooldown, cooldown_remaining
from app.core.time import days_between, utcnow
from app.jobs.runs import RunStatus
from app.jobs.tasks.scraping import enqueue_scrape_source
from app.modules.tenders import repository as repo
from app.modules.tenders.models import Tender, TenderSource
from app.modules.tenders.schemas import (
    PortalSyncState,
    SyncState,
    TenderDetail,
    TenderFacets,
    TenderFilters,
    TenderSummary,
)


def _days_left(tender: Tender) -> int | None:
    """Negative once the deadline has passed, so callers can flag it as expired."""
    if tender.deadline_at is None:
        return None
    return days_between(utcnow(), tender.deadline_at)


def to_summary(tender: Tender, source_code: str) -> TenderSummary:
    return TenderSummary(
        id=tender.id,
        source_code=source_code,
        external_id=tender.external_id,
        title=tender.title,
        summary=tender.summary,
        procuring_entity=tender.procuring_entity,
        country=tender.country,
        procurement_method=tender.procurement_method,
        procurement_category=tender.procurement_category,
        published_at=tender.published_at,
        deadline_at=tender.deadline_at,
        currency=tender.currency,
        estimated_value=float(tender.estimated_value) if tender.estimated_value else None,
        status=tender.status,
        canonical_url=tender.canonical_url,
        days_to_deadline=_days_left(tender),
    )


async def list_tenders(
    session: AsyncSession, *, filters: TenderFilters, params: PageParams
) -> Page[TenderSummary]:
    rows, total = await repo.list_tenders(session, filters=filters, params=params)
    return Page[TenderSummary].build(
        [to_summary(tender, code) for tender, code in rows], params, total
    )


async def get_tender_detail(session: AsyncSession, tender_id: UUID) -> TenderDetail:
    row = await repo.get_tender(session, tender_id)
    if row is None:
        raise NotFoundError("Tender not found.", code="tender_not_found")
    tender, source_code = row

    extraction = await repo.get_current_extraction(session, tender_id)
    summary = to_summary(tender, source_code)

    return TenderDetail(
        **summary.model_dump(),
        description=tender.description,
        language=tender.language,
        portal_metadata=tender.portal_metadata,
        version=tender.version,
        first_seen_at=tender.first_seen_at,
        last_seen_at=tender.last_seen_at,
        extraction=(
            {
                "attributes": extraction.attributes,
                "field_confidence": extraction.field_confidence,
                "evidence": extraction.evidence,
                "model": extraction.model,
                "generated_at": extraction.created_at.isoformat(),
            }
            if extraction is not None
            else None
        ),
    )


async def get_facets(session: AsyncSession, filters: TenderFilters) -> TenderFacets:
    """Counts for the filter sidebar.

    Computed under the same filters as the list, so each option shows how many
    results it would leave rather than how many exist overall.
    """
    by_source = await repo.count_by(session, TenderSource.code, filters)
    by_category = await repo.count_by(session, Tender.procurement_category, filters)
    by_country = await repo.count_by(session, Tender.country, filters)
    by_status = await repo.count_by(session, Tender.status, filters)
    closing_soon = await repo.count_closing_within(session, days=7, filters=filters)

    return TenderFacets(
        by_source=by_source,
        by_category=by_category,
        by_country=by_country,
        by_status=by_status,
        closing_within_7_days=closing_soon,
        total=sum(by_source.values()),
    )


#: One cooldown for the whole deployment, because the pool it fills is shared.
SYNC_COOLDOWN_KEY = "portal-sync"


async def _sync_state(session: AsyncSession, *, retry_after: int, queued: list[str]) -> SyncState:
    """Every portal's sync position, from the source rows and their newest run."""
    sources = await repo.list_sources(session)
    latest = await repo.latest_scraper_runs(session, [source.id for source in sources])

    portals: list[PortalSyncState] = []
    for source in sources:
        if not source.enabled:
            # `manual` is a bucket for hand-entered notices, not a portal; a sync
            # control that listed it would be offering to scrape nothing.
            continue
        run = latest.get(source.id)
        running = run is not None and run.status is RunStatus.RUNNING
        finished = None if running else run
        portals.append(
            PortalSyncState(
                id=source.id,
                code=source.code,
                name=source.name,
                enabled=source.enabled,
                health=source.health,
                running=running,
                last_run_at=source.last_run_at,
                last_success_at=source.last_success_at,
                last_status=finished.status if finished else None,
                last_notices_added=finished.created if finished else None,
            )
        )

    return SyncState(
        portals=portals,
        running=any(portal.running for portal in portals),
        retry_after_seconds=retry_after,
        cooldown_seconds=settings.source_sync_cooldown_seconds,
        queued=queued,
    )


async def get_sync_state(session: AsyncSession) -> SyncState:
    """Where the portals stand, without starting anything."""
    return await _sync_state(
        session, retry_after=await cooldown_remaining(SYNC_COOLDOWN_KEY), queued=[]
    )


async def sync_sources(session: AsyncSession) -> SyncState:
    """Queue a pass over every enabled portal, if the cooldown allows it.

    The same dispatch the schedule calls four times a day: one job per portal on
    the scrape queue, which runs one at a time. A hand-started sync is therefore
    exactly as polite to an old portal as the cron is — the only difference is
    who asked for it.

    A refusal is not an error. The button exists so somebody can see the product
    fill up, and telling them to wait nine minutes is a legitimate answer to
    "again, now" — so this returns the state with a countdown rather than
    raising, and the interface shows the wait instead of a failure.
    """
    retry_after = await cooldown_remaining(SYNC_COOLDOWN_KEY)
    if retry_after:
        return await _sync_state(session, retry_after=retry_after, queued=[])

    state = await _sync_state(session, retry_after=0, queued=[])
    ready = [portal for portal in state.portals if not portal.running]
    if not ready:
        # Every portal is already mid-pass. Nothing to start, and no reason to
        # spend the cooldown on a press that queued nothing.
        return state

    retry_after = await claim_cooldown(
        SYNC_COOLDOWN_KEY, seconds=settings.source_sync_cooldown_seconds
    )
    if retry_after:
        # Someone else pressed it in the moment between the check and the claim.
        return await _sync_state(session, retry_after=retry_after, queued=[])

    queued: list[str] = []
    for portal in ready:
        if await enqueue_scrape_source(portal.id, portal.code):
            queued.append(portal.code)

    state.queued = queued
    state.retry_after_seconds = settings.source_sync_cooldown_seconds
    state.running = True if queued else state.running
    for portal in state.portals:
        if portal.code in queued:
            portal.running = True
    return state
