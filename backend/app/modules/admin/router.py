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
    AiUsageRow,
    AiUsageSummary,
    EmailOutboxRead,
    EmailRetryResponse,
    ImportResponse,
    JobRunRead,
    JobTriggerRequest,
    JobTriggerResponse,
    ReparseResponse,
    ReprocessResponse,
    ScraperRunRead,
    SourceAdminRead,
    SourceCreate,
    SourceHealthCheck,
    SourceRunResponse,
    SourceUpdate,
    TenderCreate,
    TenderCreateResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])

SourceId = Annotated[UUID, Path(description="Source identifier")]
TenderId = Annotated[UUID, Path(description="Tender identifier")]


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
    "/sources/{source_id}/run",
    response_model=SourceRunResponse,
    summary="Scrape a source now",
)
async def run_source(source_id: SourceId, _: Superuser, db: DbSession) -> SourceRunResponse:
    """Queue one portal for scraping.

    Deduplicated by source, so pressing this twice does not start two passes
    over the same portal.
    """
    source = await service.get_source(db, source_id)
    job_id = await service.enqueue_scrape(db, source_id)
    return SourceRunResponse(source_code=source.code, job_id=job_id, enqueued=job_id is not None)


@router.post(
    "/sources/{source_id}/check",
    response_model=SourceHealthCheck,
    summary="Probe a source now",
)
async def check_source(source_id: SourceId, _: Superuser, db: DbSession) -> SourceHealthCheck:
    """Ask the portal whether it is reachable, rather than reading the health
    recorded by past runs."""
    code, reachable, detail = await service.probe_source(db, source_id)
    return SourceHealthCheck(source_code=code, reachable=reachable, detail=detail)


@router.get(
    "/scraper-runs",
    response_model=list[ScraperRunRead],
    summary="Recent scrape runs",
)
async def list_scraper_runs(
    _: Superuser,
    db: DbSession,
    source_id: Annotated[UUID | None, Query(description="Filter to one source")] = None,
) -> list[ScraperRunRead]:
    """A scraper that quietly stops returning notices looks exactly like a quiet
    portal. These records are the only way to tell the difference."""
    return [
        ScraperRunRead.model_validate(run)
        for run in await service.recent_scraper_runs(db, source_id)
    ]


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


@router.post(
    "/sources/{source_id}/reparse",
    response_model=ReparseResponse,
    summary="Replay stored payloads through the parser",
)
async def reparse_source(
    source_id: SourceId,
    _: Superuser,
    db: DbSession,
    limit: Annotated[int | None, Query(ge=1, le=5000, description="Cap on notices")] = None,
) -> ReparseResponse:
    """Re-parse this portal's notices from bytes already held.

    This is the repair path for a portal that changed its markup: fix the
    selectors, replay, and every notice ingested by the broken parser is
    corrected without asking the portal for anything.
    """
    source = await service.get_source(db, source_id)
    job_id = await service.enqueue_reparse(db, source_id, limit=limit)
    return ReparseResponse(source_code=source.code, job_id=job_id, enqueued=job_id is not None)


@router.post(
    "/tenders/{tender_id}/reprocess",
    response_model=ReprocessResponse,
    summary="Re-run the pipeline for one notice",
)
async def reprocess_tender(
    tender_id: TenderId,
    _: Superuser,
    db: DbSession,
    reparse: Annotated[
        bool, Query(description="Re-parse stored payloads before extracting")
    ] = False,
) -> ReprocessResponse:
    """Send one notice back through extraction, embedding and matching."""
    job_id = await service.enqueue_reprocess(db, tender_id, reparse=reparse)
    return ReprocessResponse(tender_id=tender_id, job_id=job_id, enqueued=job_id is not None)


@router.get("/jobs/runs", response_model=list[JobRunRead], summary="Recent background runs")
async def list_job_runs(
    _: Superuser,
    db: DbSession,
    name: Annotated[str | None, Query(description="Filter to one job")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[JobRunRead]:
    runs = await service.recent_job_runs(db, name=name, limit=limit)
    return [JobRunRead.model_validate(run) for run in runs]


@router.post("/jobs/trigger", response_model=JobTriggerResponse, summary="Run a job now")
async def trigger_job(data: JobTriggerRequest, _: Superuser) -> JobTriggerResponse:
    """Start one allowlisted job immediately.

    An allowlist rather than an arbitrary function name: this takes a string
    from a request and the worker runs everything from matching to mail.
    """
    job_id = await service.trigger_job(data.job)
    return JobTriggerResponse(job=data.job, job_id=job_id, enqueued=job_id is not None)


@router.get(
    "/email-outbox",
    response_model=list[EmailOutboxRead],
    summary="Mail that has not been delivered",
)
async def list_email_outbox(
    _: Superuser, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[EmailOutboxRead]:
    rows = await service.list_failed_emails(db, limit=limit)
    return [EmailOutboxRead.model_validate(row) for row in rows]


@router.post(
    "/email-outbox/{email_id}/retry",
    response_model=EmailRetryResponse,
    summary="Put a failed message back in the queue",
)
async def retry_email(
    email_id: Annotated[UUID, Path(description="Outbox row identifier")],
    _: Superuser,
    db: DbSession,
) -> EmailRetryResponse:
    """Only a message that gave up is re-queued; a pending one is already due."""
    requeued = await service.retry_email(db, email_id)
    return EmailRetryResponse(email_id=email_id, requeued=requeued)


@router.get("/ai-usage", response_model=AiUsageSummary, summary="Model spend")
async def ai_usage(
    _: Superuser, db: DbSession, days: Annotated[int, Query(ge=1, le=90)] = 14
) -> AiUsageSummary:
    """What the model cost, and how close today is to the cap."""
    from app.core.config import settings
    from app.modules.matching.ai_usage import spent_today

    rows = await service.ai_usage_summary(db, days=days)
    return AiUsageSummary(
        daily_token_budget=settings.ai_daily_token_budget,
        spent_today=await spent_today(db),
        rows=[AiUsageRow.model_validate(row) for row in rows],
    )
