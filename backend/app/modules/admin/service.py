"""Superuser operations: portal registration and manual tender entry.

Manual entry and CSV/JSON import both go through the same ingestion upsert the
scrapers use, so a hand-added notice is indistinguishable downstream.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.ingestion.adapters import ADAPTERS, build_adapter
from app.ingestion.adapters.base import TenderIn
from app.ingestion.importer import import_tenders, parse_payload
from app.ingestion.service import upsert_tender
from app.jobs.queue import QUEUE_DEFAULT
from app.jobs.runs import JobRun, ScraperRun
from app.modules.admin.schemas import (
    ImportResponse,
    SourceCreate,
    SourceUpdate,
    TenderCreate,
    TenderCreateResponse,
)
from app.modules.matching.ai_usage import AiUsage
from app.modules.notifications.models import EmailOutbox, EmailStatus
from app.modules.tenders.models import Tender, TenderSource

logger = get_logger(__name__)

#: ``manual`` is a real source with no adapter: hand-entered and imported
#: notices land in it, and nothing ever scrapes it.
_ADAPTERLESS = frozenset({"manual"})


def _check_adapter(adapter_key: str) -> None:
    if adapter_key not in ADAPTERS and adapter_key not in _ADAPTERLESS:
        known = ", ".join(sorted(set(ADAPTERS) | _ADAPTERLESS))
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
    from app.jobs.tasks.scraping import enqueue_scrape_source

    source = await get_source(session, source_id)
    return await enqueue_scrape_source(source.id, source.code)


async def probe_source(session: AsyncSession, source_id: UUID) -> tuple[str, bool, str | None]:
    """Ask the portal whether it is reachable, right now."""
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


# --- reprocessing --------------------------------------------------------


async def enqueue_reparse(
    session: AsyncSession, source_id: UUID, *, limit: int | None = None
) -> str | None:
    """Queue a replay of one portal's stored payloads through the parser.

    On the scrape queue despite touching no portal: it is a long, serial job
    over the same rows a live scrape writes, and running the two at once would
    have them fighting over every notice.
    """
    from app.jobs.queue import QUEUE_SCRAPE, get_queue

    source = await get_source(session, source_id)
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(
            "reparse_source",
            str(source.id),
            limit,
            _queue_name=QUEUE_SCRAPE,
            _job_id=f"reparse:{source.id}",
        )
    except Exception as exc:  # pragma: no cover - Redis down must not 500
        logger.warning("reparse_enqueue_failed", source=source.code, error=str(exc))
        return None
    return job.job_id if job else None


async def enqueue_reprocess(
    session: AsyncSession, tender_id: UUID, *, reparse: bool = False
) -> str | None:
    """Queue one notice back through extraction, embedding and matching."""
    from app.jobs.queue import get_queue

    tender = await session.get(Tender, tender_id)
    if tender is None:
        raise NotFoundError("Tender not found.", code="tender_not_found")
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(
            "reprocess_tender",
            str(tender_id),
            reparse,
            _job_id=f"reprocess:{tender_id}",
        )
    except Exception as exc:  # pragma: no cover - Redis down must not 500
        logger.warning("reprocess_enqueue_failed", tender_id=str(tender_id), error=str(exc))
        return None
    return job.job_id if job else None


# --- jobs, mail and spend ------------------------------------------------

#: Jobs an operator may start by hand. An allowlist rather than "any function
#: name", because this endpoint takes a string from a request and the default
#: queue runs everything from matching to mail.
TRIGGERABLE_JOBS: dict[str, str] = {
    "scrape_all_sources": QUEUE_DEFAULT,
    # Retained so an operator's bookmarked call keeps working post-rename.
    "scrape_due_sources": QUEUE_DEFAULT,
    "close_expired_tenders": QUEUE_DEFAULT,
    "age_match_urgency": QUEUE_DEFAULT,
    "purge_old_runs": QUEUE_DEFAULT,
    "purge_old_notifications": QUEUE_DEFAULT,
    "purge_orphan_blobs": QUEUE_DEFAULT,
    "alert_sources_down": QUEUE_DEFAULT,
    "mark_source_health": QUEUE_DEFAULT,
    "refresh_fx_rates": QUEUE_DEFAULT,
    "pump_email_outbox": QUEUE_DEFAULT,
    "digest_dispatcher": QUEUE_DEFAULT,
    "deadline_reminder_sweep": QUEUE_DEFAULT,
    "ping": QUEUE_DEFAULT,
}


async def recent_job_runs(
    session: AsyncSession, *, name: str | None = None, limit: int = 50
) -> list[JobRun]:
    stmt = select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)
    if name:
        stmt = stmt.where(JobRun.name == name)
    return list((await session.scalars(stmt)).all())


async def trigger_job(job_name: str) -> str | None:
    """Run one allowlisted job now."""
    from app.jobs.queue import get_queue

    queue_name = TRIGGERABLE_JOBS.get(job_name)
    if queue_name is None:
        known = ", ".join(sorted(TRIGGERABLE_JOBS))
        raise ValidationError(
            f"Unknown job {job_name!r}. Triggerable: {known}.", code="unknown_job"
        )
    try:
        queue = await get_queue()
        job = await queue.enqueue_job(job_name, _queue_name=queue_name)
    except Exception as exc:  # pragma: no cover - Redis down must not 500
        logger.warning("job_trigger_failed", job=job_name, error=str(exc))
        return None
    return job.job_id if job else None


async def list_failed_emails(session: AsyncSession, limit: int = 50) -> list[EmailOutbox]:
    stmt = (
        select(EmailOutbox)
        .where(EmailOutbox.status.in_((EmailStatus.FAILED, EmailStatus.PENDING)))
        .order_by(EmailOutbox.created_at.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


async def retry_email(session: AsyncSession, email_id: UUID) -> bool:
    from app.modules.notifications.email.outbox import requeue

    return await requeue(session, email_id)


async def ai_usage_summary(session: AsyncSession, days: int = 14) -> list[dict[str, object]]:
    """Tokens and calls per day and purpose, newest first."""
    since = utcnow().date() - timedelta(days=days)
    rows = await session.execute(
        select(
            AiUsage.day,
            AiUsage.purpose,
            AiUsage.model,
            func.count().label("calls"),
            func.coalesce(func.sum(AiUsage.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(AiUsage.tokens_out), 0).label("tokens_out"),
        )
        .where(AiUsage.day >= since)
        .group_by(AiUsage.day, AiUsage.purpose, AiUsage.model)
        .order_by(AiUsage.day.desc(), AiUsage.purpose)
    )
    return [
        {
            "day": row.day,
            "purpose": row.purpose,
            "model": row.model,
            "calls": row.calls,
            "tokens_in": row.tokens_in,
            "tokens_out": row.tokens_out,
        }
        for row in rows.all()
    ]
