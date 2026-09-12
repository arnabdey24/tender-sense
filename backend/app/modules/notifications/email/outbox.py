"""Outbox operations: enqueue, claim, and record the outcome of a send.

Callers never talk to SMTP. They render and persist a message here; the
``pump_email_outbox`` job claims rows and delivers them, so an email survives a
crash and a transient SMTP outage costs a retry rather than a lost signup.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import emails_delivered, notifications_queued
from app.core.time import utcnow
from app.modules.notifications.email.renderer import renderer
from app.modules.notifications.models import RETRY_BACKOFF_MINUTES, EmailOutbox, EmailStatus

logger = get_logger(__name__)

#: `last_error` is diagnostic; keep it from growing without bound.
MAX_ERROR_LENGTH = 2000


def backoff_delay(attempts: int) -> timedelta:
    """Wait before retry number ``attempts`` (1 = the first failure).

    The last entry of :data:`RETRY_BACKOFF_MINUTES` repeats once the schedule
    runs out, so a long outage keeps retrying twice a day rather than stopping.
    """
    index = min(max(attempts, 1) - 1, len(RETRY_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=RETRY_BACKOFF_MINUTES[index])


async def enqueue(
    session: AsyncSession,
    *,
    template_key: str,
    to_email: str,
    context: dict[str, Any],
    to_name: str | None = None,
    org_id: UUID | None = None,
    dedupe_key: str | None = None,
) -> EmailOutbox | None:
    """Render now, store the result, and let the pump deliver it.

    Rendering happens here on purpose: a template bug raises
    :class:`~app.modules.notifications.email.renderer.EmailTemplateError` in the
    request that caused it instead of silently failing in a worker.

    Args:
        dedupe_key: When given, a second enqueue with the same key is a no-op.

    Returns:
        The stored row, or ``None`` when ``dedupe_key`` already existed.
    """
    rendered = renderer.render(template_key, context)
    values: dict[str, Any] = {
        "org_id": org_id,
        "to_email": to_email,
        "to_name": to_name,
        "template_key": template_key,
        "subject": rendered.subject,
        "html_body": rendered.html_body,
        "text_body": rendered.text_body,
        "context": context,
        "dedupe_key": dedupe_key,
    }

    if dedupe_key is None:
        email = EmailOutbox(**values)
        session.add(email)
        await session.flush()
    else:
        stmt = (
            pg_insert(EmailOutbox)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[EmailOutbox.dedupe_key])
            .returning(EmailOutbox)
        )
        result = await session.execute(stmt)
        existing = result.scalars().first()
        if existing is None:
            logger.info("email_enqueue_deduplicated", template=template_key, dedupe=dedupe_key)
            return None
        email = existing

    notifications_queued.labels(type=template_key).inc()
    logger.info(
        "email_enqueued",
        email_id=str(email.id),
        template=template_key,
        to=to_email,
        dedupe=dedupe_key,
    )
    return email


async def claim_batch(
    session: AsyncSession,
    *,
    limit: int = 50,
    now: datetime | None = None,
) -> list[EmailOutbox]:
    """Lock up to ``limit`` due rows and flip them to ``SENDING``.

    ``SKIP LOCKED`` lets several pumps run at once without handing the same
    message to two of them.
    """
    moment = now or utcnow()
    stmt = (
        select(EmailOutbox)
        .where(
            EmailOutbox.status == EmailStatus.PENDING,
            EmailOutbox.next_attempt_at <= moment,
        )
        .order_by(EmailOutbox.next_attempt_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    emails = list((await session.execute(stmt)).scalars().all())
    for email in emails:
        email.status = EmailStatus.SENDING
    await session.flush()
    return emails


async def reclaim_stalled(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stalled_after: timedelta | None = None,
) -> int:
    """Return rows abandoned mid-send to the queue.

    ``claim_batch`` flips a row to ``SENDING`` and commits before the slow part,
    so a worker that dies between the claim and the outcome leaves the row in a
    state nothing rescues: the pump only claims ``PENDING``, the console only
    lists ``PENDING`` and ``FAILED``, and the admin retry only resets ``FAILED``.
    The row is invisible and permanently stuck, and the reader is left with a
    verification email that simply never came.

    Workers restart on every deploy, so this is not a rare crash path — it is
    the ordinary cost of shipping while the queue has anything in it.

    The re-send is deliberate, and it can duplicate: a process killed *after*
    the relay accepted the message but *before* the commit will send it twice.
    Two verification emails are a papercut and none is a person who cannot get
    into their account, so the ambiguity is resolved towards delivering.

    Attempts is incremented, so a message that strands the worker every time
    walks the same backoff as any other failure and eventually lands in
    ``FAILED`` where somebody can see it, rather than looping forever.
    """
    moment = now or utcnow()
    cutoff = moment - (stalled_after or timedelta(minutes=settings.email_stalled_after_minutes))
    stmt = (
        update(EmailOutbox)
        .where(EmailOutbox.status == EmailStatus.SENDING, EmailOutbox.updated_at < cutoff)
        .values(
            status=EmailStatus.PENDING,
            attempts=EmailOutbox.attempts + 1,
            next_attempt_at=moment,
            last_error="Delivery was interrupted before its outcome was recorded.",
        )
    )
    result = await session.execute(stmt)
    reclaimed = int(getattr(result, "rowcount", 0) or 0)
    if reclaimed:
        logger.warning("email_reclaimed_stalled", count=reclaimed)
    return reclaimed


async def mark_sent(
    session: AsyncSession,
    email: EmailOutbox,
    *,
    message_id: str | None = None,
    now: datetime | None = None,
) -> None:
    emails_delivered.labels(outcome="sent").inc()
    email.status = EmailStatus.SENT
    email.sent_at = now or utcnow()
    email.message_id = message_id
    email.last_error = None
    await session.flush()


async def mark_failed(
    session: AsyncSession,
    email: EmailOutbox,
    *,
    error: str,
    now: datetime | None = None,
) -> None:
    """Record a delivery failure and either reschedule or give up."""
    moment = now or utcnow()
    emails_delivered.labels(outcome="failed").inc()
    email.attempts += 1
    email.last_error = error[:MAX_ERROR_LENGTH]
    if email.attempts >= settings.email_max_attempts:
        email.status = EmailStatus.FAILED
    else:
        email.status = EmailStatus.PENDING
        email.next_attempt_at = moment + backoff_delay(email.attempts)
    await session.flush()


async def requeue(session: AsyncSession, email_id: UUID) -> bool:
    """Admin retry: put a ``FAILED`` row back in the queue for immediate send.

    Returns:
        ``True`` when a failed row was reset, ``False`` when the id is unknown
        or the row is in any other state.
    """
    email = await session.get(EmailOutbox, email_id)
    # `SENDING` is rescuable too: a row abandoned by a dead worker is exactly
    # the one an operator watching the queue most wants to push through, and
    # refusing it left the only visible stuck state with no button that worked.
    if email is None or email.status not in (EmailStatus.FAILED, EmailStatus.SENDING):
        return False
    email.status = EmailStatus.PENDING
    email.attempts = 0
    email.last_error = None
    email.next_attempt_at = utcnow()
    await session.flush()
    logger.info("email_requeued", email_id=str(email_id))
    return True
