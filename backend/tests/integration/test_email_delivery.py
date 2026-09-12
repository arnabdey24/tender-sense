"""Outbox behaviour against real Postgres: enqueue, dedupe, claim, retry, pump."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ExternalServiceError
from app.core.time import utcnow

# Imported from the registry module so every table the FKs reference is mapped.
from app.db.models import EmailOutbox, EmailStatus
from app.db.session import dispose_engine, session_scope
from app.jobs.tasks.email import pump_email_outbox
from app.modules.notifications.email.outbox import (
    backoff_delay,
    claim_batch,
    enqueue,
    mark_failed,
    reclaim_stalled,
    requeue,
)

#: Every row this module creates carries this domain so cleanup can find it.
TEST_DOMAIN = "email-outbox-it.test"

VERIFY_CONTEXT = {
    "user_name": "Ayesha Rahman",
    "verify_url": "https://app.tendersense.test/verify/tok-integration",
    "expires_in_hours": 24,
}


class RecordingSender:
    """Stands in for SMTP; remembers what the pump handed it."""

    def __init__(self) -> None:
        self.sent: list[EmailOutbox] = []

    async def send(self, email: EmailOutbox) -> str | None:
        self.sent.append(email)
        return f"<{email.id}@recording.test>"


class ExplodingSender:
    async def send(self, email: EmailOutbox) -> str | None:
        raise ExternalServiceError("relay refused the recipient")


def _address() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@{TEST_DOMAIN}"


async def _enqueue_verify(session: AsyncSession, **kwargs: object) -> EmailOutbox:
    email = await enqueue(
        session,
        template_key="verify_email",
        to_email=_address(),
        context=dict(VERIFY_CONTEXT),
        **kwargs,  # type: ignore[arg-type]
    )
    assert email is not None
    return email


@pytest.fixture(autouse=True)
async def _cleanup_rows() -> AsyncIterator[None]:
    yield
    async with session_scope() as session:
        await session.execute(
            delete(EmailOutbox).where(EmailOutbox.to_email.like(f"%@{TEST_DOMAIN}"))
        )
    await dispose_engine()


async def test_enqueue_stores_a_pending_row_with_rendered_bodies() -> None:
    async with session_scope() as session:
        email = await _enqueue_verify(session, to_name="Ayesha Rahman")
        email_id = email.id

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.PENDING
    assert stored.attempts == 0
    assert stored.to_name == "Ayesha Rahman"
    assert stored.subject == f"Confirm your email address for {settings.project_name}"
    assert VERIFY_CONTEXT["verify_url"] in stored.html_body
    assert VERIFY_CONTEXT["verify_url"] in stored.text_body
    assert stored.context["user_name"] == "Ayesha Rahman"


async def test_the_same_dedupe_key_never_produces_a_second_row() -> None:
    dedupe_key = f"verify:{uuid.uuid4()}"

    async with session_scope() as session:
        first = await _enqueue_verify(session, dedupe_key=dedupe_key)

    async with session_scope() as session:
        second = await enqueue(
            session,
            template_key="verify_email",
            to_email=_address(),
            context=dict(VERIFY_CONTEXT),
            dedupe_key=dedupe_key,
        )

    assert second is None

    async with session_scope() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(EmailOutbox)
            .where(EmailOutbox.dedupe_key == dedupe_key)
        )

    assert count == 1
    assert first.dedupe_key == dedupe_key


async def test_claim_batch_locks_due_rows_and_flips_them_to_sending() -> None:
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id

    async with session_scope() as session:
        claimed = await claim_batch(session, limit=50)
        claimed_ids = {row.id for row in claimed}

    assert email_id in claimed_ids
    assert all(row.status is EmailStatus.SENDING for row in claimed)

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.SENDING


async def test_a_future_attempt_time_keeps_a_row_out_of_the_batch() -> None:
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email.next_attempt_at = utcnow() + timedelta(hours=1)
        await session.flush()
        email_id = email.id

    async with session_scope() as session:
        claimed = await claim_batch(session, limit=50)

    assert email_id not in {row.id for row in claimed}


async def test_failures_reschedule_with_backoff_then_give_up() -> None:
    now = utcnow()

    async with session_scope() as session:
        email = await _enqueue_verify(session)

        await mark_failed(session, email, error="connection refused", now=now)

        assert email.status is EmailStatus.PENDING
        assert email.attempts == 1
        assert email.last_error == "connection refused"
        assert email.next_attempt_at == now + backoff_delay(1)

        await mark_failed(session, email, error="connection refused", now=now)

        assert email.attempts == 2
        assert email.next_attempt_at == now + backoff_delay(2)

        while email.attempts < settings.email_max_attempts:
            await mark_failed(session, email, error="connection refused", now=now)

        assert email.status is EmailStatus.FAILED
        assert email.attempts == settings.email_max_attempts
        email_id = email.id

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)
        assert stored is not None
        assert stored.status is EmailStatus.FAILED

        assert await requeue(session, email_id) is True
        assert stored.status is EmailStatus.PENDING
        assert stored.attempts == 0
        assert stored.last_error is None

        # Only failed rows can be requeued.
        assert await requeue(session, email_id) is False
        assert await requeue(session, uuid.uuid4()) is False


async def test_the_pump_delivers_pending_rows_and_marks_them_sent() -> None:
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id

    sender = RecordingSender()

    result = await pump_email_outbox({"email_sender": sender})

    assert result["claimed"] >= 1
    assert result["sent"] >= 1
    assert result["failed"] == 0
    assert email_id in {row.id for row in sender.sent}

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.SENT
    assert stored.sent_at is not None
    assert stored.message_id == f"<{email_id}@recording.test>"


async def test_a_transport_failure_reschedules_instead_of_raising() -> None:
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id

    result = await pump_email_outbox({"email_sender": ExplodingSender()})

    assert result["failed"] >= 1
    assert result["sent"] == 0

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.PENDING
    assert stored.attempts == 1
    assert stored.last_error is not None
    assert "relay refused" in stored.last_error
    assert stored.next_attempt_at > utcnow()


async def test_a_row_abandoned_mid_send_is_put_back() -> None:
    """The bug behind "the verification email simply never arrived".

    `claim_batch` commits the flip to SENDING before the slow part, so a worker
    killed between the claim and the outcome leaves a row nothing rescues: the
    pump claims only PENDING, so it is never retried; the console lists only
    PENDING and FAILED, so nobody can see it; and `requeue` reset only FAILED,
    so the retry button did not apply either.
    """
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id
        claimed = await claim_batch(session)
        assert email_id in {row.id for row in claimed}

    # The worker dies here. Wind the row's clock back past the stall window.
    async with session_scope() as session:
        stranded = await session.get(EmailOutbox, email_id)
        assert stranded is not None
        assert stranded.status is EmailStatus.SENDING
        stranded.updated_at = utcnow() - timedelta(minutes=settings.email_stalled_after_minutes + 1)

    sender = RecordingSender()
    result = await pump_email_outbox({"email_sender": sender})

    assert result["reclaimed"] >= 1
    # Reclaimed and delivered on the same pass, not the one after it.
    assert email_id in {row.id for row in sender.sent}

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.SENT


async def test_a_row_still_in_flight_is_left_alone() -> None:
    """A slow relay is not a dead worker, and must never be sent twice."""
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id
        await claim_batch(session)

    async with session_scope() as session:
        reclaimed = await reclaim_stalled(session)

    assert reclaimed == 0

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.SENDING


async def test_reclaiming_counts_as_an_attempt() -> None:
    """So a message that kills its worker every time cannot loop forever.

    It walks the same backoff as any other failure and eventually lands in
    FAILED, where the console shows it and a person can decide.
    """
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id
        await claim_batch(session)

    async with session_scope() as session:
        stranded = await session.get(EmailOutbox, email_id)
        assert stranded is not None
        stranded.updated_at = utcnow() - timedelta(minutes=settings.email_stalled_after_minutes + 1)

    async with session_scope() as session:
        assert await reclaim_stalled(session) == 1

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.PENDING
    assert stored.attempts == 1
    assert stored.last_error is not None


async def test_an_operator_can_retry_a_stuck_row_by_hand() -> None:
    """The console's retry button is the obvious thing to press; it now works."""
    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id
        await claim_batch(session)

    async with session_scope() as session:
        assert await requeue(session, email_id) is True

    async with session_scope() as session:
        stored = await session.get(EmailOutbox, email_id)

    assert stored is not None
    assert stored.status is EmailStatus.PENDING


async def test_the_console_lists_a_stuck_row() -> None:
    """Invisible was half the bug: there was nothing to press the button on."""
    from app.modules.admin.service import list_failed_emails

    async with session_scope() as session:
        email = await _enqueue_verify(session)
        email_id = email.id
        await claim_batch(session)

    async with session_scope() as session:
        listed = await list_failed_emails(session, limit=200)

    assert email_id in {row.id for row in listed}
