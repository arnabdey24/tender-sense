"""Everything TenderSense sends, and the record of having sent it.

Four concerns live here, in the order a message travels through them:

* **Settings** — what an organization wants to be told about, and when.
* **Recipients** — proven addresses that organization mail may go to.
* **Notifications** — the in-app centre, which needs no address at all.
* **Outbox** — rendered messages waiting for the SMTP pump.

Plus a **ledger**, which is the part that stops a retried job, a re-scored
match or a second worker from mailing someone the same thing twice. Getting
that wrong is not a cosmetic bug: a duplicate deadline reminder at 3 a.m. is
how a product teaches people to filter it into a folder they never open.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import DEFAULT_TIMEZONE, utcnow
from app.db.base import Base, Email, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class EmailStatus(enum.StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Minutes to wait before each retry; the last value repeats if it runs out.
RETRY_BACKOFF_MINUTES = (1, 5, 30, 120, 720)


class EmailOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_status_next_attempt_at", "status", "next_attempt_at"),
        Index("ix_email_outbox_org_id", "org_id"),
    )

    org_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), default=None
    )
    to_email: Mapped[Email] = mapped_column()
    to_name: Mapped[str | None] = mapped_column(String(200), default=None)
    template_key: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(500))
    html_body: Mapped[str] = mapped_column(Text)
    text_body: Mapped[str] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    #: Set to make an enqueue idempotent, e.g. ``invite:<id>``.
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True, default=None)
    status: Mapped[EmailStatus] = mapped_column(
        Enum(
            EmailStatus,
            name="email_status",
            native_enum=True,
            values_callable=lambda e: [member.value for member in e],
        ),
        default=EmailStatus.PENDING,
        server_default=EmailStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=text("now()"))
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(default=None)
    message_id: Mapped[str | None] = mapped_column(String(400), default=None)


class NotificationType(enum.StrEnum):
    """What a message is about. Recipients subscribe per type."""

    INSTANT_MATCH = "instant_match"
    """A strong, eligible match, mailed as soon as it is scored."""
    DAILY_DIGEST = "daily_digest"
    DEADLINE_REMINDER = "deadline_reminder"
    """Only for tenders the organization decided to bid on."""
    TENDER_UPDATED = "tender_updated"
    """A notice we are bidding on was amended by the portal."""
    SOURCE_DOWN = "source_down"
    """A portal stopped answering. In-app only, for admins."""
    SYSTEM = "system"


class NotificationSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organization's answer to "tell me about what, and when".

    Digest time is stored as a wall-clock time plus a timezone rather than as
    UTC, because "eight in the morning" has to survive daylight saving and a
    company that moves. The dispatcher converts at send time instead.
    """

    __tablename__ = "notification_settings"
    __table_args__ = (UniqueConstraint("org_id"),)

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))

    inapp_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    instant_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    #: Grades at or above this letter qualify. Default S: an instant alert that
    #: fires for a merely decent match is one nobody reads instantly.
    instant_min_grade: Mapped[str] = mapped_column(String(1), default="S", server_default="S")
    #: Instant alerts require an eligible verdict by default. Mailing someone
    #: "drop everything" about a tender they cannot legally bid on is worse
    #: than saying nothing.
    instant_requires_eligible: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    digest_time: Mapped[time] = mapped_column(
        Time(timezone=False), default=time(8, 0), server_default="08:00"
    )
    digest_timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    digest_min_grade: Mapped[str] = mapped_column(String(1), default="B", server_default="B")
    #: The local date the last digest covered. Guards against a dispatcher that
    #: runs every fifteen minutes sending fifteen-minute digests.
    last_digest_sent_for: Mapped[date | None] = mapped_column(Date, default=None)

    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    #: Days before the deadline to remind, for tenders marked "bid".
    reminder_offsets: Mapped[list[Any]] = mapped_column(
        default=lambda: [7, 2], server_default="[7, 2]"
    )


class NotificationRecipient(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An address an organization's mail may be sent to.

    Verification is not ceremony. Without it, one admin could route a
    competitor's tender shortlist to any address they liked by typing it into a
    settings form — so an address receives nothing until someone holding it
    clicks a link, and unsubscribing is honoured for good.
    """

    __tablename__ = "notification_recipients"
    __table_args__ = (
        UniqueConstraint("org_id", "email"),
        Index("ix_notification_recipients_org_id", "org_id"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[Email] = mapped_column()
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    #: Which notification types this address wants. Empty means all of them.
    types: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")

    #: SHA-256 of the verification token; the raw value only ever exists in the
    #: email, exactly as for invitations and password resets.
    verify_token_hash: Mapped[str | None] = mapped_column(String(64), index=True, default=None)
    verified_at: Mapped[datetime | None] = mapped_column(default=None)
    #: Goes into the unsubscribe link of every message, so unlike the
    #: verification token it is stored raw rather than hashed: it has to be
    #: reproducible at every send, and it is a capability to *stop* mail, not
    #: to read anything. A link that stopped working after a key rotation is
    #: how a product earns a spam complaint.
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(default=None)
    added_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )

    @property
    def is_deliverable(self) -> bool:
        return self.verified_at is not None and self.unsubscribed_at is None

    def wants(self, notification_type: NotificationType) -> bool:
        """An empty subscription list means everything, not nothing."""
        return not self.types or notification_type.value in self.types


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One entry in the in-app notification centre.

    Org-wide by default (``user_id`` null): a match belongs to the company, not
    to whoever happened to be looking. Read state is per user, tracked in
    ``notification_reads``, so one person clearing the badge does not hide the
    news from their colleagues.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_org_id_created_at", "org_id", "created_at"),
        Index("ix_notifications_org_id_type", "org_id", "type"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    #: Set only when a message concerns one person rather than the company.
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None
    )
    type: Mapped[NotificationType] = mapped_column(_pg_enum(NotificationType, "notification_type"))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str | None] = mapped_column(Text, default=None)
    #: Where clicking it should go, relative to the app root.
    link: Mapped[str | None] = mapped_column(String(500), default=None)
    tender_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenders.id", ondelete="CASCADE"), default=None
    )
    data: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")


class NotificationRead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Which user has read which notification.

    A row rather than a flag, because notifications are org-wide: one person
    marking the badge clear must not hide a new match from their colleagues.
    """

    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id"),
        Index("ix_notification_reads_user_id", "user_id"),
    )

    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE")
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    read_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=text("now()"))


class NotificationLedger(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Proof that one organization was already told one specific thing.

    The unique constraint is the whole feature. Jobs retry, matches get
    re-scored, and two workers can wake on the same minute — any of which would
    otherwise mail the same reminder twice. ``subject_key`` names the thing
    precisely enough to be idempotent: ``"<tender_id>:7"`` is the seven-day
    reminder for one tender, and there can only ever be one.
    """

    __tablename__ = "notification_ledger"
    __table_args__ = (
        UniqueConstraint("org_id", "type", "subject_key"),
        Index("ix_notification_ledger_org_id_created_at", "org_id", "created_at"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    type: Mapped[NotificationType] = mapped_column(_pg_enum(NotificationType, "notification_type"))
    subject_key: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20), default="email", server_default="email")
    recipients: Mapped[int] = mapped_column(Integer, default=0)
