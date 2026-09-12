"""Superuser operations: portal registration and manual tender entry.

Manual entry and CSV/JSON import both go through the same ingestion upsert the
scrapers use, so a hand-added notice is indistinguishable downstream.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.platform_settings import get_limits
from app.core.time import utcnow
from app.ingestion.adapters import ADAPTERS, build_adapter
from app.ingestion.adapters.base import TenderIn
from app.ingestion.importer import import_tenders, parse_payload
from app.ingestion.service import upsert_tender
from app.jobs.queue import QUEUE_DEFAULT
from app.jobs.runs import JobRun, RunStatus, ScraperRun
from app.modules.admin.schemas import (
    ImportResponse,
    IntakeDay,
    JobDay,
    OrganizationAdminRead,
    Overview,
    SourceCreate,
    SourceHealthCount,
    SourceUpdate,
    TenderCreate,
    TenderCreateResponse,
    Trends,
    UserAdminRead,
    UserAdminUpdate,
)
from app.modules.matching.ai_usage import AiUsage
from app.modules.notifications.models import EmailOutbox, EmailStatus
from app.modules.tenders.models import Tender, TenderSource, TenderStatus

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
    # The repair for notices that reached the pool but never the pipeline.
    "process_unprocessed_tenders": QUEUE_DEFAULT,
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
        # `SENDING` belongs here: a row abandoned by a worker that died
        # mid-send is stuck, and listing only pending and failed is what made
        # it invisible to the one person who could have done something.
        .where(
            EmailOutbox.status.in_((EmailStatus.FAILED, EmailStatus.PENDING, EmailStatus.SENDING))
        )
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


async def _count(session: AsyncSession, stmt: Any) -> int:
    """A count that is an int, so callers stop writing `or 0` seven times."""
    return int(await session.scalar(stmt) or 0)


async def overview(session: AsyncSession) -> Overview:
    """One read of everything the console's front page asserts.

    A single endpoint rather than six, because the question it answers is "is
    anything wrong right now" — and six requests means six chances to render a
    page that is half stale and disagrees with itself.
    """
    from app.modules.matching.ai_usage import spent_today
    from app.modules.notifications.email.diagnostics import email_config_problems
    from app.modules.orgs.models import Organization
    from app.modules.users.models import User

    since = utcnow() - timedelta(hours=24)

    per_source = {
        row.source_id: row.total
        for row in await session.execute(
            select(Tender.source_id, func.count(Tender.id).label("total")).group_by(
                Tender.source_id
            )
        )
    }
    sources = [
        SourceHealthCount(
            code=source.code,
            name=source.name,
            health=source.health.value,
            enabled=source.enabled,
            last_success_at=source.last_success_at,
            tenders=int(per_source.get(source.id, 0)),
        )
        for source in (await session.scalars(select(TenderSource).order_by(TenderSource.code)))
    ]

    return Overview(
        tenders=await _count(session, select(func.count(Tender.id))),
        tenders_open=await _count(
            session, select(func.count(Tender.id)).where(Tender.status == TenderStatus.OPEN)
        ),
        tenders_added_today=await _count(
            session,
            select(func.count(Tender.id)).where(
                Tender.first_seen_at >= utcnow() - timedelta(days=1)
            ),
        ),
        organizations=await _count(session, select(func.count(Organization.id))),
        organizations_active=await _count(
            session,
            select(func.count(Organization.id)).where(Organization.is_active.is_(True)),
        ),
        users=await _count(session, select(func.count(User.id))),
        users_active=await _count(
            session, select(func.count(User.id)).where(User.is_active.is_(True))
        ),
        sources=sources,
        jobs_failed_24h=await _count(
            session,
            select(func.count(JobRun.id)).where(
                JobRun.status == RunStatus.FAILED, JobRun.started_at >= since
            ),
        ),
        scrapes_failed_24h=await _count(
            session,
            select(func.count(ScraperRun.id)).where(
                ScraperRun.status == RunStatus.FAILED, ScraperRun.started_at >= since
            ),
        ),
        email_queued=await _count(
            session,
            select(func.count(EmailOutbox.id)).where(EmailOutbox.status == EmailStatus.PENDING),
        ),
        email_failed=await _count(
            session,
            select(func.count(EmailOutbox.id)).where(EmailOutbox.status == EmailStatus.FAILED),
        ),
        email_stuck=await _count(
            session,
            select(func.count(EmailOutbox.id)).where(EmailOutbox.status == EmailStatus.SENDING),
        ),
        email_config_problems=[p.as_text() for p in email_config_problems(settings)],
        ai_tokens_today=await spent_today(session),
        ai_daily_token_budget=(await get_limits(session)).ai_daily_token_budget,
    )


async def list_organizations(
    session: AsyncSession, *, q: str | None = None, limit: int = 100
) -> list[OrganizationAdminRead]:
    """Every tenant, with the two facts that say whether it is real: how many
    people are in it, and when it last did anything."""
    from app.modules.decisions.models import TenderDecision
    from app.modules.orgs.models import Membership, MembershipStatus, Organization

    members = (
        select(Membership.org_id, func.count(Membership.id).label("total"))
        .where(Membership.status == MembershipStatus.ACTIVE)
        .group_by(Membership.org_id)
        .subquery()
    )
    activity = (
        select(
            TenderDecision.org_id,
            func.max(TenderDecision.created_at).label("last_at"),
        )
        .group_by(TenderDecision.org_id)
        .subquery()
    )

    stmt = (
        select(Organization, members.c.total, activity.c.last_at)
        .outerjoin(members, members.c.org_id == Organization.id)
        .outerjoin(activity, activity.c.org_id == Organization.id)
        .order_by(Organization.created_at.desc())
        .limit(limit)
    )
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(Organization.name.ilike(term) | Organization.slug.ilike(term))

    return [
        OrganizationAdminRead(
            id=org.id,
            name=org.name,
            slug=org.slug,
            country=org.country,
            plan=org.plan,
            is_active=org.is_active,
            created_at=org.created_at,
            members=int(total or 0),
            last_activity_at=last_at,
        )
        for org, total, last_at in await session.execute(stmt)
    ]


async def list_users(
    session: AsyncSession, *, q: str | None = None, limit: int = 100
) -> list[UserAdminRead]:
    """Accounts, with the organizations each one belongs to."""
    from app.modules.orgs.models import Membership, MembershipStatus, Organization
    from app.modules.users.models import User

    stmt = select(User).order_by(User.created_at.desc()).limit(limit)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(User.email.ilike(term) | User.full_name.ilike(term))
    users = list((await session.scalars(stmt)).all())
    if not users:
        return []

    names: dict[UUID, list[str]] = {}
    for user_id, org_name in await session.execute(
        select(Membership.user_id, Organization.name)
        .join(Organization, Organization.id == Membership.org_id)
        .where(
            Membership.user_id.in_([user.id for user in users]),
            Membership.status == MembershipStatus.ACTIVE,
        )
    ):
        names.setdefault(user_id, []).append(org_name)

    return [
        UserAdminRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            email_verified=user.email_verified,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            organizations=sorted(names.get(user.id, [])),
        )
        for user in users
    ]


async def update_user(
    session: AsyncSession, user_id: UUID, data: UserAdminUpdate, *, acting_user_id: UUID
) -> UserAdminRead:
    """Suspend an account, or grant and revoke platform staff.

    A caller cannot do either to themselves. Revoking your own last superuser
    flag, or deactivating the account you are signed in as, is the one mistake
    here that nobody can undo from the console afterwards — it would need
    somebody with database access, which on a single-VM deployment may be the
    same person now locked out.
    """
    from app.modules.users.models import User

    if user_id == acting_user_id:
        raise ValidationError("Change another operator's access, not your own.")

    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found.")

    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_superuser is not None:
        user.is_superuser = data.is_superuser
    await session.flush()

    logger.info(
        "admin_user_updated",
        user_id=str(user_id),
        by=str(acting_user_id),
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )
    return (await list_users(session, q=user.email, limit=1))[0]


async def trends(session: AsyncSession, days: int = 14) -> Trends:
    """Daily intake per portal, and daily job outcomes.

    Two aggregate queries rather than one row per notice: the pool is the
    largest table in the product and the console is opened while something is
    already wrong, which is the worst moment to ask Postgres for 50,000 rows so
    the browser can count them.

    Days with nothing are filled in rather than omitted. A chart drawn only from
    days that had arrivals closes the gap that is the entire signal — a portal
    silent since Tuesday looks identical to one that reports every day.
    """
    window = max(1, min(int(days), 90))
    # Bucket by calendar day in UTC, which is what the labels say. A local
    # timezone here would make "today" disagree with `tenders_added_today`.
    today = utcnow().date()
    since = today - timedelta(days=window - 1)
    calendar = [since + timedelta(days=offset) for offset in range(window)]

    portals = [
        source
        for source in (await session.scalars(select(TenderSource).order_by(TenderSource.code)))
        if source.enabled
    ]
    codes = [source.code for source in portals]
    by_id = {source.id: source.code for source in portals}

    intake: dict[date, dict[str, int]] = {day: dict.fromkeys(codes, 0) for day in calendar}
    rows = await session.execute(
        select(
            func.date(Tender.first_seen_at).label("day"),
            Tender.source_id,
            func.count(Tender.id).label("total"),
        )
        .where(func.date(Tender.first_seen_at) >= since)
        .group_by("day", Tender.source_id)
    )
    for day, source_id, total in rows:
        code = by_id.get(source_id)
        if code and day in intake:
            intake[day][code] = int(total)

    jobs: dict[date, dict[str, int]] = {
        day: {"succeeded": 0, "failed": 0, "partial": 0} for day in calendar
    }
    rows = await session.execute(
        select(
            func.date(JobRun.started_at).label("day"),
            JobRun.status,
            func.count(JobRun.id).label("total"),
        )
        .where(func.date(JobRun.started_at) >= since)
        .group_by("day", JobRun.status)
    )
    for day, status, total in rows:
        # `running` is a job in flight, not an outcome, so it is not drawn as
        # one — a bar counting it would fall as the run finished.
        bucket = jobs.get(day)
        if bucket is not None and status.value in bucket:
            bucket[status.value] = int(total)

    return Trends(
        days=window,
        sources=codes,
        source_names={source.code: source.name for source in portals},
        intake=[IntakeDay(day=day, by_source=intake[day]) for day in calendar],
        jobs=[JobDay(day=day, **jobs[day]) for day in calendar],
    )
