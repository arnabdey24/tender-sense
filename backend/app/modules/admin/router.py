"""Superuser admin surface.

Every route here requires ``is_superuser``. These are platform-operator tools,
not organization-admin features.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request, status

from app.core.deps import DbSession, Superuser
from app.modules.admin import service
from app.modules.admin.schemas import (
    ImportResponse,
    SourceAdminRead,
    SourceCreate,
    SourceUpdate,
    TenderCreate,
    TenderCreateResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])

SourceId = Annotated[UUID, Path(description="Source identifier")]


@router.get("/sources", response_model=list[SourceAdminRead])
async def list_sources(_: Superuser, db: DbSession) -> list[SourceAdminRead]:
    """Every ingestion source with its full scraping configuration."""
    return [SourceAdminRead.model_validate(s) for s in await service.list_sources(db)]


@router.post("/sources", response_model=SourceAdminRead, status_code=status.HTTP_201_CREATED)
async def create_source(data: SourceCreate, _: Superuser, db: DbSession) -> SourceAdminRead:
    """Register a portal. ``adapter_key`` must match a known adapter."""
    return SourceAdminRead.model_validate(await service.create_source(db, data))


@router.get("/sources/{source_id}", response_model=SourceAdminRead)
async def get_source(source_id: SourceId, _: Superuser, db: DbSession) -> SourceAdminRead:
    return SourceAdminRead.model_validate(await service.get_source(db, source_id))


@router.patch("/sources/{source_id}", response_model=SourceAdminRead)
async def update_source(
    source_id: SourceId, data: SourceUpdate, _: Superuser, db: DbSession
) -> SourceAdminRead:
    """Patch a source. Selector and endpoint changes are data, not a deploy."""
    return SourceAdminRead.model_validate(await service.update_source(db, source_id, data))


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(source_id: SourceId, _: Superuser, db: DbSession) -> None:
    """Remove a source and, by cascade, its tenders and raw documents."""
    await service.delete_source(db, source_id)


@router.post(
    "/tenders",
    response_model=TenderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tender(data: TenderCreate, _: Superuser, db: DbSession) -> TenderCreateResponse:
    """Add one notice by hand, through the same upsert path the scrapers use."""
    return await service.create_tender(db, data)


@router.post("/tenders/import", response_model=ImportResponse)
async def import_tenders(
    request: Request,
    _: Superuser,
    db: DbSession,
    source_code: Annotated[
        str | None,
        Query(description="Source code for rows that omit their own"),
    ] = None,
) -> ImportResponse:
    """Bulk import notices from a JSON array or a CSV document in the request body.

    A malformed row is reported and skipped rather than failing the batch.
    """
    raw = await request.body()
    return await service.import_tender_payload(
        db,
        raw=raw,
        content_type=request.headers.get("content-type"),
        default_source_code=source_code,
    )
