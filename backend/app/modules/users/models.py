"""User accounts and linked social identities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Email, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[Email] = mapped_column(unique=True, index=True)
    #: Null for accounts created through Google that never set a password.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    full_name: Mapped[str] = mapped_column(String(200))
    avatar_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    email_verified_at: Mapped[datetime | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    #: Platform staff, not organization admins.
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class OAuthAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A social identity linked to a :class:`User`."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id"),
        Index("ix_oauth_accounts_user_id_provider", "user_id", "provider"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    #: The provider's stable subject identifier (Google's ``sub``).
    provider_account_id: Mapped[str] = mapped_column(String(255))
    email: Mapped[Email | None] = mapped_column(default=None)
    raw_profile: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
