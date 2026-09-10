"""What a company decided to do about a tender.

Kept as an append-only log with a "current" flag rather than a single mutable
row, because the interesting question months later is not "what did we decide"
but "when did we change our mind, and why". The note attached to a reversal is
usually the most valuable text in the system.
"""

from __future__ import annotations

import enum
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Decision(enum.StrEnum):
    BID = "bid"
    """We are going for it. Deadline reminders start from here."""
    HOLD = "hold"
    """Interested but not committed."""
    SKIP = "skip"
    """Not for us."""


class TenderDecision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One decision, superseded rather than overwritten."""

    __tablename__ = "tender_decisions"
    __table_args__ = (
        # At most one live decision per tenant per tender. A partial unique
        # index rather than a plain one, so superseded rows can pile up freely.
        Index(
            "uq_tender_decisions_current",
            "org_id",
            "tender_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_tender_decisions_org_id_tender_id", "org_id", "tender_id"),
        Index("ix_tender_decisions_org_id_decision", "org_id", "decision"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))
    decision: Mapped[Decision] = mapped_column(
        Enum(
            Decision,
            name="tender_decision",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    note: Mapped[str | None] = mapped_column(Text, default=None)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    decided_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
