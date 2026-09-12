"""Recording and reading decisions.

Every change writes a new row and demotes the previous one, so the trail is
complete. Reversing a decision is normal and often the point: a "skip" that
became a "bid" two days later, with a note explaining what changed, is the
record someone will want when the same buyer publishes again.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.core.pagination import PageParams
from app.modules.decisions.models import Decision, TenderDecision
from app.modules.decisions.schemas import DecisionWrite
from app.modules.matching.models import TenderMatch
from app.modules.tenders.models import Tender, TenderSource

logger = get_logger(__name__)


async def current_decision(
    session: AsyncSession, *, org_id: UUID, tender_id: UUID
) -> TenderDecision | None:
    result: TenderDecision | None = await session.scalar(
        select(TenderDecision).where(
            TenderDecision.org_id == org_id,
            TenderDecision.tender_id == tender_id,
            TenderDecision.is_current.is_(True),
        )
    )
    return result


async def record(
    session: AsyncSession,
    *,
    org_id: UUID,
    tender_id: UUID,
    data: DecisionWrite,
    user_id: UUID | None = None,
) -> TenderDecision:
    """Record a decision, superseding any previous one."""
    tender = await session.get(Tender, tender_id)
    if tender is None:
        raise NotFoundError("Tender not found.", code="tender_not_found")

    # Demote first: the partial unique index allows only one current row, so
    # inserting before demoting would collide.
    await session.execute(
        update(TenderDecision)
        .where(
            TenderDecision.org_id == org_id,
            TenderDecision.tender_id == tender_id,
            TenderDecision.is_current.is_(True),
        )
        .values(is_current=False)
    )
    await session.flush()

    decision = TenderDecision(
        org_id=org_id,
        tender_id=tender_id,
        decision=data.decision,
        note=data.note,
        decided_by_id=user_id,
        is_current=True,
    )
    session.add(decision)
    await session.flush()
    logger.info(
        "decision_recorded",
        org_id=str(org_id),
        tender_id=str(tender_id),
        decision=data.decision.value,
    )
    return decision


async def clear(session: AsyncSession, *, org_id: UUID, tender_id: UUID) -> None:
    """Withdraw the current decision without deleting the history."""
    await session.execute(
        update(TenderDecision)
        .where(
            TenderDecision.org_id == org_id,
            TenderDecision.tender_id == tender_id,
            TenderDecision.is_current.is_(True),
        )
        .values(is_current=False)
    )
    await session.flush()


async def history(session: AsyncSession, *, org_id: UUID, tender_id: UUID) -> list[TenderDecision]:
    """Every decision ever recorded for this tender, newest first."""
    rows = await session.scalars(
        select(TenderDecision)
        .where(TenderDecision.org_id == org_id, TenderDecision.tender_id == tender_id)
        .order_by(TenderDecision.created_at.desc())
    )
    return list(rows.all())


async def list_current(
    session: AsyncSession,
    *,
    org_id: UUID,
    decision: Decision | None,
    params: PageParams,
) -> tuple[list[tuple[TenderDecision, Tender, str, TenderMatch | None]], int]:
    """Live decisions with their notices, soonest deadline first.

    The match is joined in as an *outer* join and may be ``None``. A decision
    belongs to a tender, not to a match: a company that has recorded a bid
    before finishing its capability profile has decisions and no scores at all,
    and an inner join here would silently drop precisely those rows — which is
    how a recorded bid managed to appear nowhere in the application.
    """
    base = (
        select(TenderDecision, Tender, TenderSource.code, TenderMatch)
        .join(Tender, Tender.id == TenderDecision.tender_id)
        .join(TenderSource, TenderSource.id == Tender.source_id)
        .outerjoin(
            TenderMatch,
            (TenderMatch.tender_id == TenderDecision.tender_id)
            & (TenderMatch.org_id == TenderDecision.org_id),
        )
        .where(TenderDecision.org_id == org_id, TenderDecision.is_current.is_(True))
    )
    counting = (
        select(func.count(TenderDecision.id))
        .join(Tender, Tender.id == TenderDecision.tender_id)
        .where(TenderDecision.org_id == org_id, TenderDecision.is_current.is_(True))
    )
    if decision is not None:
        base = base.where(TenderDecision.decision == decision)
        counting = counting.where(TenderDecision.decision == decision)

    total = (await session.scalar(counting)) or 0
    rows = (
        await session.execute(
            base.order_by(Tender.deadline_at.asc().nulls_last())
            .offset(params.offset)
            .limit(params.limit)
        )
    ).all()
    return [(row[0], row[1], row[2], row[3]) for row in rows], total
