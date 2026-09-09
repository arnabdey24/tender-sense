"""Queries over the shared tender pool."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.core.time import utcnow
from app.modules.tenders.models import (
    Tender,
    TenderExtraction,
    TenderSource,
    TenderStatus,
)
from app.modules.tenders.schemas import TenderFilters

CLOSED_STATUSES = (TenderStatus.CLOSED, TenderStatus.CANCELLED, TenderStatus.AWARDED)


def _apply_filters(stmt: Select[Any], filters: TenderFilters) -> Select[Any]:
    if filters.q:
        # Rank-free matching: the full-text index answers "does this mention it",
        # and trigram similarity catches partial words and misspelt buyer names.
        query = filters.q.strip()
        stmt = stmt.where(
            or_(
                Tender.search_tsv.op("@@")(func.plainto_tsquery("simple", query)),
                Tender.title.ilike(f"%{query}%"),
            )
        )
    if filters.source:
        stmt = stmt.where(TenderSource.code.in_(filters.source))
    if filters.country:
        stmt = stmt.where(Tender.country.in_([code.upper() for code in filters.country]))
    if filters.category:
        stmt = stmt.where(Tender.procurement_category.in_(filters.category))
    if filters.status:
        stmt = stmt.where(Tender.status.in_(filters.status))
    if filters.deadline_from:
        stmt = stmt.where(Tender.deadline_at >= filters.deadline_from)
    if filters.deadline_to:
        stmt = stmt.where(Tender.deadline_at <= filters.deadline_to)
    if filters.deadline_within_days is not None:
        horizon = utcnow() + func.make_interval(0, 0, 0, filters.deadline_within_days)
        stmt = stmt.where(and_(Tender.deadline_at.is_not(None), Tender.deadline_at <= horizon))
    if filters.open_only:
        now = utcnow()
        stmt = stmt.where(
            Tender.status.not_in(CLOSED_STATUSES),
            or_(Tender.deadline_at.is_(None), Tender.deadline_at > now),
        )
    return stmt


def _base_query() -> Select[Any]:
    return select(Tender, TenderSource.code).join(TenderSource, TenderSource.id == Tender.source_id)


async def list_tenders(
    session: AsyncSession, *, filters: TenderFilters, params: PageParams
) -> tuple[list[tuple[Tender, str]], int]:
    stmt = _apply_filters(_base_query(), filters)

    count_stmt = _apply_filters(
        select(func.count(Tender.id)).join(TenderSource, TenderSource.id == Tender.source_id),
        filters,
    )
    total = (await session.scalar(count_stmt)) or 0

    column = getattr(Tender, filters.sort.value)
    # Notices without the sort value belong at the end either way, otherwise a
    # deadline sort leads with every notice that has no deadline at all.
    ordering = column.desc() if filters.descending else column.asc()
    stmt = stmt.order_by(ordering.nulls_last(), Tender.id).offset(params.offset).limit(params.limit)

    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1]) for row in rows], total


async def get_tender(session: AsyncSession, tender_id: UUID) -> tuple[Tender, str] | None:
    row = (await session.execute(_base_query().where(Tender.id == tender_id))).first()
    return (row[0], row[1]) if row else None


async def get_current_extraction(session: AsyncSession, tender_id: UUID) -> TenderExtraction | None:
    result = await session.scalar(
        select(TenderExtraction).where(
            TenderExtraction.tender_id == tender_id, TenderExtraction.is_current.is_(True)
        )
    )
    return result


async def count_by(session: AsyncSession, column: Any, filters: TenderFilters) -> dict[str, int]:
    stmt = _apply_filters(
        select(column, func.count(Tender.id))
        .join(TenderSource, TenderSource.id == Tender.source_id)
        .group_by(column),
        filters,
    )
    rows = (await session.execute(stmt)).all()
    return {str(getattr(key, "value", key)): count for key, count in rows if key is not None}


async def count_closing_within(session: AsyncSession, *, days: int, filters: TenderFilters) -> int:
    horizon = utcnow() + func.make_interval(0, 0, 0, days)
    stmt = _apply_filters(
        select(func.count(Tender.id)).join(TenderSource, TenderSource.id == Tender.source_id),
        filters,
    ).where(
        Tender.deadline_at.is_not(None),
        Tender.deadline_at <= horizon,
        Tender.deadline_at > utcnow(),
    )
    return (await session.scalar(stmt)) or 0


async def list_sources(session: AsyncSession) -> list[TenderSource]:
    rows = await session.execute(select(TenderSource).order_by(TenderSource.code))
    return list(rows.scalars().all())
