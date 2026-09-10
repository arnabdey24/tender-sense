"""Queries behind the notification centre, settings and recipients.

Every read is scoped by ``org_id`` from the auth context. A notification names
a tender the whole company can see, so cross-tenant leakage here would hand one
customer another's shortlist.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import (
    Notification,
    NotificationRead,
    NotificationRecipient,
    NotificationSettings,
    NotificationType,
)


async def get_settings(session: AsyncSession, org_id: UUID) -> NotificationSettings | None:
    result: NotificationSettings | None = await session.scalar(
        select(NotificationSettings).where(NotificationSettings.org_id == org_id)
    )
    return result


async def list_recipients(
    session: AsyncSession, org_id: UUID, *, include_unsubscribed: bool = True
) -> list[NotificationRecipient]:
    stmt = (
        select(NotificationRecipient)
        .where(NotificationRecipient.org_id == org_id)
        .order_by(NotificationRecipient.created_at)
    )
    if not include_unsubscribed:
        stmt = stmt.where(NotificationRecipient.unsubscribed_at.is_(None))
    return list((await session.scalars(stmt)).all())


async def deliverable_recipients(
    session: AsyncSession, org_id: UUID, notification_type: NotificationType
) -> list[NotificationRecipient]:
    """Verified, still-subscribed addresses that asked for this type.

    The filtering happens here rather than at each call site because "only
    verified, only subscribed" is the rule that must hold for *every* piece of
    organization mail, and a caller that forgot it would not fail visibly.
    """
    rows = await session.scalars(
        select(NotificationRecipient).where(
            NotificationRecipient.org_id == org_id,
            NotificationRecipient.verified_at.is_not(None),
            NotificationRecipient.unsubscribed_at.is_(None),
        )
    )
    return [row for row in rows.all() if row.wants(notification_type)]


async def find_by_verify_token(
    session: AsyncSession, token_hash: str
) -> NotificationRecipient | None:
    result: NotificationRecipient | None = await session.scalar(
        select(NotificationRecipient).where(NotificationRecipient.verify_token_hash == token_hash)
    )
    return result


async def find_by_unsubscribe_token(
    session: AsyncSession, token: str
) -> NotificationRecipient | None:
    result: NotificationRecipient | None = await session.scalar(
        select(NotificationRecipient).where(NotificationRecipient.unsubscribe_token == token)
    )
    return result


def _visible_to(org_id: UUID, user_id: UUID) -> Select[tuple[Notification]]:
    """Org-wide notifications plus the ones addressed to this user alone."""
    return select(Notification).where(
        Notification.org_id == org_id,
        (Notification.user_id.is_(None)) | (Notification.user_id == user_id),
    )


async def list_notifications(
    session: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    *,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[tuple[Notification, bool]]:
    """Recent notifications, each paired with whether *this* user has read it."""
    read_at = (
        select(NotificationRead.notification_id)
        .where(NotificationRead.user_id == user_id)
        .subquery()
    )
    stmt = (
        select(Notification, read_at.c.notification_id.is_not(None).label("is_read"))
        .select_from(Notification)
        .outerjoin(read_at, read_at.c.notification_id == Notification.id)
        .where(
            Notification.org_id == org_id,
            (Notification.user_id.is_(None)) | (Notification.user_id == user_id),
        )
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if unread_only:
        stmt = stmt.where(read_at.c.notification_id.is_(None))
    rows = await session.execute(stmt)
    return [(notification, bool(is_read)) for notification, is_read in rows.all()]


async def unread_count(session: AsyncSession, org_id: UUID, user_id: UUID) -> int:
    read_ids = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)
    total = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.org_id == org_id,
            (Notification.user_id.is_(None)) | (Notification.user_id == user_id),
            Notification.id.not_in(read_ids),
        )
    )
    return int(total or 0)


async def get_notification(
    session: AsyncSession, org_id: UUID, user_id: UUID, notification_id: UUID
) -> Notification | None:
    result: Notification | None = await session.scalar(
        _visible_to(org_id, user_id).where(Notification.id == notification_id)
    )
    return result


async def unread_ids(session: AsyncSession, org_id: UUID, user_id: UUID) -> list[UUID]:
    read_ids = select(NotificationRead.notification_id).where(NotificationRead.user_id == user_id)
    rows = await session.scalars(
        select(Notification.id).where(
            Notification.org_id == org_id,
            (Notification.user_id.is_(None)) | (Notification.user_id == user_id),
            Notification.id.not_in(read_ids),
        )
    )
    return list(rows.all())
