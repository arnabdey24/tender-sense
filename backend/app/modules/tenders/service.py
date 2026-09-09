"""Presentation logic for the tender pool."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams
from app.core.time import days_between, utcnow
from app.modules.tenders import repository as repo
from app.modules.tenders.models import Tender, TenderSource
from app.modules.tenders.schemas import (
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
