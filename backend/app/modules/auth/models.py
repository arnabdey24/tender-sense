"""Single-use action tokens and refresh-token sessions.

No raw token value is ever stored: every column below holds a SHA-256 digest,
so a database leak cannot be replayed against the API.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TokenPurpose(enum.StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"


class AuthToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A one-shot, emailed token: verify address, reset password."""

    __tablename__ = "auth_tokens"
    __table_args__ = (Index("ix_auth_tokens_user_id_purpose", "user_id", "purpose"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[TokenPurpose] = mapped_column(
        Enum(
            TokenPurpose,
            name="auth_token_purpose",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(default=None)

    def is_usable(self, *, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.used_at is None and self.expires_at > now


class RefreshSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One issued refresh token.

    Rotation: each refresh revokes the presented row and inserts a successor
    sharing its ``family_id``. Presenting an already-revoked token means the
    value leaked, so the whole family is revoked at once.
    """

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user_id_revoked_at", "user_id", "revoked_at"),
        Index("ix_refresh_sessions_family_id", "family_id"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    #: Organization the paired access token was scoped to, if any.
    org_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), default=None
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    #: Shared by every token descended from one login.
    family_id: Mapped[UUID]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    replaced_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"), default=None
    )
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)

    def is_active(self, *, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.revoked_at is None and self.expires_at > now
