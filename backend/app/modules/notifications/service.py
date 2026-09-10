"""Deciding who gets told what, and making sure they are told exactly once.

Two rules run through everything here.

**Nothing is mailed to an unproven address.** Without verification, one admin
could route a competitor's shortlist anywhere by typing an address into a form.
An address receives nothing until someone holding it clicks a link, and an
unsubscribe is honoured permanently.

**Nothing is mailed twice.** Jobs retry, matches are re-scored, and two workers
can wake on the same minute. Every outbound piece of organization mail passes
through the ledger first, whose unique constraint is what turns "probably once"
into "once".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.security import generate_token, hash_token
from app.core.time import utcnow
from app.modules.notifications import repository as repo
from app.modules.notifications.email import outbox
from app.modules.notifications.models import (
    Notification,
    NotificationLedger,
    NotificationRead,
    NotificationRecipient,
    NotificationSettings,
    NotificationType,
)
from app.modules.notifications.schemas import (
    NotificationSettingsUpdate,
    RecipientCreate,
    RecipientUpdate,
)
from app.modules.orgs.models import Organization

logger = get_logger(__name__)

#: Grades from best to worst, so "at least A" is a slice rather than a lookup.
GRADE_ORDER = ("S", "A", "B", "C")


def grade_at_least(grade: str, minimum: str) -> bool:
    """Whether ``grade`` is as good as ``minimum`` or better."""
    try:
        return GRADE_ORDER.index(grade) <= GRADE_ORDER.index(minimum)
    except ValueError:
        return False


def app_link(path: str) -> str:
    return f"{app_settings.app_url.rstrip('/')}{path}"


# --- settings ------------------------------------------------------------


async def settings_for(session: AsyncSession, org: Organization) -> NotificationSettings:
    """This organization's preferences, created with sane defaults if absent.

    The digest timezone starts as the organization's own, because a Dhaka
    company being mailed at 08:00 UTC would get its "morning" shortlist in the
    afternoon — and would have no idea why.
    """
    existing = await repo.get_settings(session, org.id)
    if existing is not None:
        return existing

    created = NotificationSettings(org_id=org.id, digest_timezone=org.timezone)
    session.add(created)
    try:
        await session.flush()
    except IntegrityError:
        # Two requests raced to create the row; whoever lost re-reads the winner.
        await session.rollback()
        found = await repo.get_settings(session, org.id)
        if found is None:  # pragma: no cover - the constraint guarantees one exists
            raise
        return found
    return created


async def update_settings(
    session: AsyncSession, org: Organization, data: NotificationSettingsUpdate
) -> NotificationSettings:
    record = await settings_for(session, org)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    await session.flush()
    logger.info("notification_settings_updated", org_id=str(org.id))
    return record


# --- recipients ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RecipientWithToken:
    recipient: NotificationRecipient
    #: Raw verification token. Exists only long enough to be put in an email.
    verify_token: str


async def add_recipient(
    session: AsyncSession,
    *,
    org: Organization,
    data: RecipientCreate,
    added_by_id: UUID | None,
) -> RecipientWithToken:
    """Register an address and send it a verification link.

    Adding an address that is already registered is a conflict rather than a
    silent no-op: the admin who typed it needs to know it is already there, and
    quietly re-sending a verification email would let this endpoint be used to
    mail someone repeatedly.
    """
    clash = await session.scalar(
        select(NotificationRecipient).where(
            NotificationRecipient.org_id == org.id,
            NotificationRecipient.email == str(data.email),
        )
    )
    if clash is not None:
        raise ConflictError("That address is already a recipient.", code="recipient_exists")

    verify_token = generate_token()
    recipient = NotificationRecipient(
        org_id=org.id,
        email=str(data.email),
        name=data.name,
        types=[item.value for item in data.types],
        verify_token_hash=hash_token(verify_token),
        unsubscribe_token=generate_token(),
        added_by_id=added_by_id,
    )
    session.add(recipient)
    await session.flush()

    await _enqueue_verification(session, org=org, recipient=recipient, token=verify_token)
    return RecipientWithToken(recipient=recipient, verify_token=verify_token)


async def _enqueue_verification(
    session: AsyncSession, *, org: Organization, recipient: NotificationRecipient, token: str
) -> None:
    await outbox.enqueue(
        session,
        template_key="recipient_verify",
        to_email=recipient.email,
        to_name=recipient.name,
        org_id=org.id,
        context={
            "recipient_name": recipient.name or recipient.email,
            "organization_name": org.name,
            "verify_url": app_link(f"/notifications/verify?token={token}"),
        },
    )


async def resend_verification(
    session: AsyncSession, *, org: Organization, recipient_id: UUID
) -> NotificationRecipient:
    recipient = await _get_recipient(session, org.id, recipient_id)
    if recipient.verified_at is not None:
        raise ConflictError("That address is already verified.", code="already_verified")

    # A fresh token, so an old link in an inbox cannot be replayed later.
    token = generate_token()
    recipient.verify_token_hash = hash_token(token)
    await session.flush()
    await _enqueue_verification(session, org=org, recipient=recipient, token=token)
    return recipient


async def update_recipient(
    session: AsyncSession, *, org_id: UUID, recipient_id: UUID, data: RecipientUpdate
) -> NotificationRecipient:
    recipient = await _get_recipient(session, org_id, recipient_id)
    patch = data.model_dump(exclude_unset=True)
    if "types" in patch and patch["types"] is not None:
        patch["types"] = [
            item.value if hasattr(item, "value") else str(item) for item in patch["types"]
        ]
    for field, value in patch.items():
        setattr(recipient, field, value)
    await session.flush()
    return recipient


async def remove_recipient(session: AsyncSession, *, org_id: UUID, recipient_id: UUID) -> None:
    recipient = await _get_recipient(session, org_id, recipient_id)
    await session.delete(recipient)
    await session.flush()


async def _get_recipient(
    session: AsyncSession, org_id: UUID, recipient_id: UUID
) -> NotificationRecipient:
    recipient = await session.scalar(
        select(NotificationRecipient).where(
            NotificationRecipient.id == recipient_id,
            NotificationRecipient.org_id == org_id,
        )
    )
    if recipient is None:
        raise NotFoundError("Recipient not found.", code="recipient_not_found")
    return recipient


async def verify_recipient(session: AsyncSession, token: str) -> NotificationRecipient:
    """Confirm an address from an emailed link.

    The token is single-use: it is cleared on success, so a link forwarded to
    someone else later confirms nothing.
    """
    recipient = await repo.find_by_verify_token(session, hash_token(token))
    if recipient is None:
        raise NotFoundError("That verification link is not valid.", code="invalid_token")

    recipient.verified_at = utcnow()
    recipient.verify_token_hash = None
    # Verifying is an act of consent, so it also revives an unsubscribe.
    recipient.unsubscribed_at = None
    await session.flush()
    logger.info("recipient_verified", recipient_id=str(recipient.id))
    return recipient


async def unsubscribe_recipient(session: AsyncSession, token: str) -> NotificationRecipient:
    """Honour an unsubscribe link, permanently and without asking anything.

    The token is *not* consumed: a second click on the same link in an old
    message has to keep working, or someone who unsubscribed will believe it
    failed and mark the next message as spam.
    """
    recipient = await repo.find_by_unsubscribe_token(session, token)
    if recipient is None:
        raise NotFoundError("That unsubscribe link is not valid.", code="invalid_token")

    if recipient.unsubscribed_at is None:
        recipient.unsubscribed_at = utcnow()
        await session.flush()
    logger.info("recipient_unsubscribed", recipient_id=str(recipient.id))
    return recipient


def unsubscribe_url(recipient: NotificationRecipient) -> str:
    """The link every message carries, and that ``List-Unsubscribe`` points at."""
    return app_link(f"/notifications/unsubscribe?token={recipient.unsubscribe_token}")


# --- the in-app centre ---------------------------------------------------


async def notify(
    session: AsyncSession,
    *,
    org_id: UUID,
    notification_type: NotificationType,
    title: str,
    body: str | None = None,
    link: str | None = None,
    tender_id: UUID | None = None,
    user_id: UUID | None = None,
    data: dict[str, Any] | None = None,
) -> Notification:
    """Add one entry to the in-app centre."""
    notification = Notification(
        org_id=org_id,
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        link=link,
        tender_id=tender_id,
        data=data or {},
    )
    session.add(notification)
    await session.flush()
    return notification


async def mark_read(
    session: AsyncSession, *, org_id: UUID, user_id: UUID, notification_id: UUID
) -> None:
    notification = await repo.get_notification(session, org_id, user_id, notification_id)
    if notification is None:
        raise NotFoundError("Notification not found.", code="notification_not_found")
    await _record_read(session, notification_id=notification.id, user_id=user_id)


async def mark_all_read(session: AsyncSession, *, org_id: UUID, user_id: UUID) -> int:
    ids = await repo.unread_ids(session, org_id, user_id)
    for notification_id in ids:
        await _record_read(session, notification_id=notification_id, user_id=user_id)
    return len(ids)


async def _record_read(session: AsyncSession, *, notification_id: UUID, user_id: UUID) -> None:
    """Idempotent: reading something twice is not an error."""
    await session.execute(
        pg_insert(NotificationRead)
        .values(notification_id=notification_id, user_id=user_id, read_at=utcnow())
        .on_conflict_do_nothing(index_elements=["notification_id", "user_id"])
    )
    await session.flush()


async def clear_read_state(session: AsyncSession, notification_ids: list[UUID]) -> None:
    """Used when a notification is regenerated rather than duplicated."""
    if not notification_ids:
        return
    await session.execute(
        delete(NotificationRead).where(NotificationRead.notification_id.in_(notification_ids))
    )


# --- the ledger ----------------------------------------------------------


async def claim(
    session: AsyncSession,
    *,
    org_id: UUID,
    notification_type: NotificationType,
    subject_key: str,
    channel: str = "email",
    recipients: int = 0,
) -> bool:
    """Reserve the right to send one specific thing, once.

    Returns ``True`` the first time and ``False`` for every repeat, so callers
    read as ``if not await claim(...): return``. The uniqueness lives in the
    database rather than in a check-then-send, because two workers waking on the
    same minute would both pass a check.
    """
    result = await session.execute(
        pg_insert(NotificationLedger)
        .values(
            org_id=org_id,
            type=notification_type,
            subject_key=subject_key,
            channel=channel,
            recipients=recipients,
        )
        .on_conflict_do_nothing(index_elements=["org_id", "type", "subject_key"])
        .returning(NotificationLedger.id)
    )
    claimed = result.scalar_one_or_none() is not None
    if not claimed:
        logger.info(
            "notification_already_sent",
            org_id=str(org_id),
            type=notification_type.value,
            subject=subject_key,
        )
    return claimed


# --- sending -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Delivery:
    queued: int
    skipped_reason: str | None = None


async def send_to_recipients(
    session: AsyncSession,
    *,
    org: Organization,
    notification_type: NotificationType,
    template_key: str,
    context: dict[str, Any],
    subject_key: str,
) -> Delivery:
    """Queue one message to every deliverable address for this organization.

    The ledger is claimed *before* anything is enqueued. Claiming afterwards
    would leave a crash between the two able to send the whole thing again.
    """
    recipients = await repo.deliverable_recipients(session, org.id, notification_type)
    if not recipients:
        return Delivery(queued=0, skipped_reason="no_verified_recipients")

    if not await claim(
        session,
        org_id=org.id,
        notification_type=notification_type,
        subject_key=subject_key,
        recipients=len(recipients),
    ):
        return Delivery(queued=0, skipped_reason="already_sent")

    queued = 0
    for recipient in recipients:
        # Per-recipient dedupe as well as the ledger: the ledger stops the whole
        # send repeating, this stops one address being added twice to a batch.
        stored = await outbox.enqueue(
            session,
            template_key=template_key,
            to_email=recipient.email,
            to_name=recipient.name,
            org_id=org.id,
            dedupe_key=f"{notification_type.value}:{subject_key}:{recipient.id}",
            context=context
            | {
                "recipient_name": recipient.name or recipient.email,
                "organization_name": org.name,
                "unsubscribe_url": app_link(f"/notifications/unsubscribe?token={recipient.id}"),
            },
        )
        if stored is not None:
            queued += 1

    logger.info(
        "notification_queued",
        org_id=str(org.id),
        type=notification_type.value,
        subject=subject_key,
        queued=queued,
    )
    return Delivery(queued=queued)
