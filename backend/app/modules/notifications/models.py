"""Outbound email queue.

Messages are rendered when they are enqueued and stored here, so a later
template edit never rewrites what was already sent. A background pump claims
rows with ``FOR UPDATE SKIP LOCKED`` and retries with exponential backoff.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, Email, TimestampMixin, UUIDPrimaryKeyMixin


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
