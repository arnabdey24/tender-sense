"""Recording what to do about a tender.

Any member may decide — the person who spots a tender is often not the admin —
but every decision is attributed and kept, so the trail shows who changed their
mind and when.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.deps import CurrentOrg, DbSession
from app.core.pagination import Page, PageParams, page_params
from app.modules.decisions import service
from app.modules.decisions.models import Decision
from app.modules.decisions.schemas import (
    DecisionRead,
    DecisionVerdict,
    DecisionWithTender,
    DecisionWrite,
)
from app.modules.tenders.service import to_summary

router = APIRouter(tags=["decisions"])

TenderId = Annotated[UUID, Path(description="Tender identifier")]
Pagination = Annotated[PageParams, Depends(page_params)]


@router.put(
    "/tenders/{tender_id}/decision",
    response_model=DecisionRead,
    summary="Record a decision",
)
async def put_decision(
    tender_id: TenderId, data: DecisionWrite, ctx: CurrentOrg, db: DbSession
) -> DecisionRead:
    """Set bid, hold or skip. The previous decision is kept, not overwritten."""
    decision = await service.record(
        db, org_id=ctx.org_id, tender_id=tender_id, data=data, user_id=ctx.user.id
    )
    return DecisionRead.model_validate(decision)


@router.delete(
    "/tenders/{tender_id}/decision",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Withdraw the decision",
)
async def delete_decision(tender_id: TenderId, ctx: CurrentOrg, db: DbSession) -> None:
    """Withdraw the current decision. The history stays."""
    await service.clear(db, org_id=ctx.org_id, tender_id=tender_id)


@router.get(
    "/tenders/{tender_id}/decisions",
    response_model=list[DecisionRead],
    summary="Decision history",
)
async def list_history(tender_id: TenderId, ctx: CurrentOrg, db: DbSession) -> list[DecisionRead]:
    """Every decision ever recorded for this tender, newest first."""
    return [
        DecisionRead.model_validate(row)
        for row in await service.history(db, org_id=ctx.org_id, tender_id=tender_id)
    ]


@router.get(
    "/decisions",
    response_model=Page[DecisionWithTender],
    summary="Live decisions",
)
async def list_decisions(
    ctx: CurrentOrg,
    db: DbSession,
    params: Pagination,
    decision: Annotated[Decision | None, Query(description="Filter by outcome")] = None,
) -> Page[DecisionWithTender]:
    """Current decisions with their notices, soonest deadline first."""
    rows, total = await service.list_current(
        db, org_id=ctx.org_id, decision=decision, params=params
    )
    return Page[DecisionWithTender].build(
        [
            DecisionWithTender(
                **DecisionRead.model_validate(row).model_dump(),
                tender=to_summary(tender, code),
                # Absent for a tender this organization has never scored, which
                # is the ordinary state before a capability profile exists.
                verdict=DecisionVerdict.model_validate(match) if match else None,
            )
            for row, tender, code, match in rows
        ],
        params,
        total,
    )
