"""Queries over one organization's matches.

Every statement here is filtered by ``org_id`` before anything else. That is the
tenancy boundary: the tender pool is shared, but a match, its grade and its
reasoning belong to exactly one customer.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.core.time import utcnow
from app.modules.decisions.models import Decision, TenderDecision
from app.modules.matching.models import TenderMatch
from app.modules.matching.schemas import MatchFilters, MatchSortField
from app.modules.tenders.models import Tender, TenderSource, TenderStatus

CLOSED_STATUSES = (TenderStatus.CLOSED, TenderStatus.CANCELLED, TenderStatus.AWARDED)

#: Sort fields that live on the tender rather than the match.
_TENDER_SORTS = {MatchSortField.DEADLINE, MatchSortField.PUBLISHED}


def _base(org_id: UUID) -> Select[Any]:
    """Match, notice, portal code, and this organization's own decision.

    The decision is an outer join and usually null — most of the feed has not
    been acted on. It travels with the row because a feed that cannot show
    what you already decided keeps offering you the choice: the Bid button on
    a match row wrote a record the same row then rendered no differently, so
    pressing it looked like it had done nothing at all.
    """
    return (
        select(TenderMatch, Tender, TenderSource.code, TenderDecision.decision)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .join(TenderSource, TenderSource.id == Tender.source_id)
        .outerjoin(
            TenderDecision,
            (TenderDecision.tender_id == TenderMatch.tender_id)
            & (TenderDecision.org_id == TenderMatch.org_id)
            & TenderDecision.is_current.is_(True),
        )
        .where(TenderMatch.org_id == org_id)
    )


def _counting(org_id: UUID) -> Select[Any]:
    return (
        select(func.count(TenderMatch.id))
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(TenderMatch.org_id == org_id)
    )


def _apply(stmt: Select[Any], filters: MatchFilters) -> Select[Any]:
    if filters.grade:
        stmt = stmt.where(TenderMatch.grade.in_(filters.grade))
    if filters.eligibility:
        stmt = stmt.where(TenderMatch.eligibility_status.in_(filters.eligibility))
    if filters.recommendation:
        stmt = stmt.where(TenderMatch.recommendation.in_(filters.recommendation))
    if filters.urgency:
        stmt = stmt.where(TenderMatch.urgency.in_(filters.urgency))
    if filters.q:
        query = filters.q.strip()
        stmt = stmt.where(
            or_(
                Tender.title.ilike(f"%{query}%"),
                Tender.procuring_entity.ilike(f"%{query}%"),
            )
        )
    if filters.deadline_within_days is not None:
        horizon = utcnow() + func.make_interval(0, 0, 0, filters.deadline_within_days)
        stmt = stmt.where(and_(Tender.deadline_at.is_not(None), Tender.deadline_at <= horizon))
    if filters.since is not None:
        stmt = stmt.where(TenderMatch.first_matched_at >= filters.since)
    if filters.open_only:
        now = utcnow()
        stmt = stmt.where(
            Tender.status.not_in(CLOSED_STATUSES),
            or_(Tender.deadline_at.is_(None), Tender.deadline_at > now),
        )
    return stmt


def _ordering(filters: MatchFilters) -> Any:
    # `model_copy(update=...)` skips validation, so a caller building a preset
    # view can leave a plain string here. Coerce rather than trust it: the
    # value reaches ORDER BY, and an unknown one must fail as a bad request
    # rather than as an attribute error deep in the query.
    sort = MatchSortField(filters.sort)
    if sort in _TENDER_SORTS:
        column = getattr(Tender, sort.value)
    else:
        column = getattr(TenderMatch, sort.value)
    ordered = column.desc() if filters.descending else column.asc()
    # Notices missing the sort value belong at the end either way; otherwise a
    # deadline sort leads with everything that has no deadline at all.
    return ordered.nulls_last()


async def list_matches(
    session: AsyncSession, *, org_id: UUID, filters: MatchFilters, params: PageParams
) -> tuple[list[tuple[TenderMatch, Tender, str, Decision | None]], int]:
    total = (await session.scalar(_apply(_counting(org_id), filters))) or 0
    stmt = (
        _apply(_base(org_id), filters)
        .order_by(_ordering(filters), TenderMatch.id)
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows], total


async def get_match(
    session: AsyncSession, *, org_id: UUID, tender_id: UUID
) -> tuple[TenderMatch, Tender, str, Decision | None] | None:
    row = (await session.execute(_base(org_id).where(TenderMatch.tender_id == tender_id))).first()
    return (row[0], row[1], row[2], row[3]) if row else None


async def count_by(
    session: AsyncSession, *, org_id: UUID, column: Any, filters: MatchFilters
) -> dict[str, int]:
    stmt = _apply(
        select(column, func.count(TenderMatch.id))
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(TenderMatch.org_id == org_id)
        .group_by(column),
        filters,
    )
    rows = (await session.execute(stmt)).all()
    return {str(getattr(key, "value", key)): count for key, count in rows if key is not None}


async def count_closing_within(
    session: AsyncSession, *, org_id: UUID, days: int, filters: MatchFilters
) -> int:
    horizon = utcnow() + func.make_interval(0, 0, 0, days)
    stmt = _apply(_counting(org_id), filters).where(
        Tender.deadline_at.is_not(None),
        Tender.deadline_at <= horizon,
        Tender.deadline_at > utcnow(),
    )
    return (await session.scalar(stmt)) or 0


async def count_since(
    session: AsyncSession, *, org_id: UUID, moment: Any, filters: MatchFilters
) -> int:
    """Matches first seen since a moment — the "new today" figure."""
    stmt = _apply(_counting(org_id), filters).where(TenderMatch.first_matched_at >= moment)
    return (await session.scalar(stmt)) or 0
