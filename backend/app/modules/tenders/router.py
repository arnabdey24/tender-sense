"""Browsing the shared tender pool.

The pool is common to every organization, so these endpoints need a signed-in
user but no organization scope. Per-organization scoring and decisions arrive
with the matching module.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.core.deps import CurrentUser, DbSession
from app.core.pagination import Page, PageParams, page_params
from app.modules.tenders import repository as repo
from app.modules.tenders import service
from app.modules.tenders.schemas import (
    SourceRead,
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
