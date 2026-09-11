"""Browsing the shared tender pool.

The pool is common to every organization, so these endpoints need a signed-in
user but no organization scope. Per-organization scoring and decisions arrive
with the matching module.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.core.deps import CurrentUser, DbSession, OptionalOrg
from app.core.pagination import Page, PageParams, page_params
from app.modules.tenders import repository as repo
from app.modules.tenders import service
from app.modules.tenders.schemas import (
    SourceRead,
    SyncState,
    TenderDetail,
    TenderFacets,
    TenderFilters,
    TenderSummary,
    tender_filters,
)

router = APIRouter(tags=["tenders"])

Filters = Annotated[TenderFilters, Depends(tender_filters)]
Pagination = Annotated[PageParams, Depends(page_params)]
TenderId = Annotated[UUID, Path(description="Tender identifier")]


@router.get("/tenders", response_model=Page[TenderSummary])
async def list_tenders(
    _: CurrentUser, db: DbSession, filters: Filters, params: Pagination
) -> Page[TenderSummary]:
    """Search and filter the shared pool of notices."""
    return await service.list_tenders(db, filters=filters, params=params)


@router.get("/tenders/facets", response_model=TenderFacets)
async def tender_facets(_: CurrentUser, db: DbSession, filters: Filters) -> TenderFacets:
    """Result counts per filter option, for the sidebar."""
    return await service.get_facets(db, filters)


@router.get("/tenders/{tender_id}", response_model=TenderDetail)
async def get_tender(tender_id: TenderId, _: CurrentUser, db: DbSession) -> TenderDetail:
    """One notice with its extracted requirements, when they exist."""
    return await service.get_tender_detail(db, tender_id)


@router.get("/sources", response_model=list[SourceRead])
async def list_sources(_: CurrentUser, db: DbSession) -> list[SourceRead]:
    """Portals TenderSense ingests from, with their current health."""
    sources = await repo.list_sources(db)
    return [SourceRead.model_validate(source) for source in sources]


@router.get("/sources/sync", response_model=SyncState)
async def sync_status(_: CurrentUser, db: DbSession) -> SyncState:
    """Where each portal stands, and whether a sync can be started now."""
    return await service.get_sync_state(db)


@router.post("/sources/sync", response_model=SyncState)
async def sync_sources(ctx: OptionalOrg, db: DbSession) -> SyncState:
    """Pull every portal now.

    Any signed-in member, deliberately, rather than platform staff only. A
    deployment whose pool has never been filled shows an organization nothing at
    all, and the person looking at that empty screen is exactly the one who
    needs the button — telling them to find an operator, or to come back after
    the next cron pass, is not an answer.

    What it starts is the same work the schedule starts: one job per portal on a
    queue that runs one at a time. A deployment-wide cooldown keeps ten
    organizations from meaning ten times the traffic to a portal that has been
    running since 2011. Pressing inside that window is answered with the wait,
    not an error — see ``service.sync_sources``.
    """
    return await service.sync_sources(db, org_id=ctx.org_id if ctx else None)
