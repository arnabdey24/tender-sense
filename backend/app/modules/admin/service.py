"""Superuser operations: portal registration and manual tender entry.

Manual entry and CSV/JSON import both go through the same ingestion upsert the
scrapers use, so a hand-added notice is indistinguishable downstream.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.ingestion.adapters.base import ADAPTERS, TenderIn
from app.ingestion.importer import import_tenders, parse_payload
from app.ingestion.service import upsert_tender
from app.jobs.runs import ScraperRun
from app.modules.admin.schemas import (
    ImportResponse,
    SourceCreate,
    SourceUpdate,
    TenderCreate,
    TenderCreateResponse,
)
from app.modules.tenders.models import TenderSource

# ``manual`` never runs an adapter; the others are registered as their modules
# land across the ingestion milestone but are valid source configuration now.
logger = get_logger(__name__)

_PLANNED_ADAPTERS = frozenset({"manual", "worldbank", "egp_bd", "egp_bd_playwright"})


def _check_adapter(adapter_key: str) -> None:
    if adapter_key not in ADAPTERS and adapter_key not in _PLANNED_ADAPTERS:
        known = ", ".join(sorted(set(ADAPTERS) | _PLANNED_ADAPTERS))
        raise ValidationError(
            f"Unknown adapter {adapter_key!r}. Known: {known}.", code="unknown_adapter"
        )


async def list_sources(session: AsyncSession) -> list[TenderSource]:
    rows = await session.execute(select(TenderSource).order_by(TenderSource.code))
    return list(rows.scalars().all())


async def get_source(session: AsyncSession, source_id: UUID) -> TenderSource:
    source = await session.get(TenderSource, source_id)
    if source is None:
        raise NotFoundError("Source not found.", code="source_not_found")
    return source


async def get_source_by_code(session: AsyncSession, code: str) -> TenderSource:
    source = await session.scalar(select(TenderSource).where(TenderSource.code == code))
    if source is None:
        raise NotFoundError("Source not found.", code="source_not_found")
    return source


async def create_source(session: AsyncSession, data: SourceCreate) -> TenderSource:
    _check_adapter(data.adapter_key)
    clash = await session.scalar(select(TenderSource).where(TenderSource.code == data.code))
    if clash is not None:
        raise ConflictError("A source with this code already exists.", code="source_code_taken")
    source = TenderSource(**data.model_dump())
    session.add(source)
    await session.flush()
    return source


async def update_source(session: AsyncSession, source_id: UUID, data: SourceUpdate) -> TenderSource:
    source = await get_source(session, source_id)
    patch = data.model_dump(exclude_unset=True)
    if "adapter_key" in patch:
        _check_adapter(patch["adapter_key"])
    for field, value in patch.items():
        setattr(source, field, value)
    await session.flush()
    return source


async def delete_source(session: AsyncSession, source_id: UUID) -> None:
    source = await get_source(session, source_id)
    await session.delete(source)
    await session.flush()


async def create_tender(session: AsyncSession, data: TenderCreate) -> TenderCreateResponse:
    source = await get_source_by_code(session, data.source_code)
    notice = TenderIn.model_validate(data.model_dump(exclude={"source_code"}))
    result = await upsert_tender(session, source=source, data=notice)
    return TenderCreateResponse(
        tender_id=result.tender_id,
        outcome=result.outcome.value,
        version=result.version,
    )


async def import_tender_payload(
    session: AsyncSession,
    *,
    raw: bytes,
    content_type: str | None,
    default_source_code: str | None,
) -> ImportResponse:
    rows = parse_payload(raw, content_type=content_type)
    default_source = None
    if default_source_code:
        default_source = await get_source_by_code(session, default_source_code)
    report = await import_tenders(session, rows, default_source=default_source)
    return ImportResponse(**report.as_dict())


async def enqueue_scrape(session: AsyncSession, source_id: UUID) -> str | None:
    """Queue one portal for scraping on the scrape queue.

    Deduplicated by source, so pressing the button twice does not start two
    passes over the same portal — which is exactly the impolite behaviour the
    adapter is careful to avoid.
    """
    from app.jobs.queue import QUEUE_SCRAPE, get_queue

    source = await get_source(session, source_id)
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(
            "scrape_source",
            str(source.id),
            _queue_name=QUEUE_SCRAPE,
            _job_id=f"scrape:{source.id}",
        )
    except Exception as exc:  # pragma: no cover - Redis down must not 500
        logger.warning("scrape_enqueue_failed", source=source.code, error=str(exc))
        return None
    return job.job_id if job else None


async def probe_source(session: AsyncSession, source_id: UUID) -> tuple[str, bool, str | None]:
    """Ask the portal whether it is reachable, right now."""
    from app.jobs.tasks.scraping import build_adapter

    source = await get_source(session, source_id)
    try:
        adapter = build_adapter(
            source.adapter_key, base_url=source.base_url, config=dict(source.config or {})
        )
    except LookupError as exc:
        return source.code, False, str(exc)

    report = await adapter.healthcheck()
    return source.code, report.reachable, report.detail


async def recent_scraper_runs(
    session: AsyncSession, source_id: UUID | None = None, limit: int = 50
) -> list[ScraperRun]:
    stmt = select(ScraperRun).order_by(ScraperRun.started_at.desc()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(ScraperRun.source_id == source_id)
    rows = await session.scalars(stmt)
    return list(rows.all())
