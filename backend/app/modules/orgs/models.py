"""Organizations (tenants), their members, and pending invitations."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint, text
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


class OrgRole(enum.StrEnum):
    ADMIN = "admin"
    """Manages the profile, rules, sources, notifications and members."""

    MEMBER = "member"
    """Reads matches and records bid/hold/skip decisions."""


class MembershipStatus(enum.StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[Email] = mapped_column(unique=True, index=True)
    country: Mapped[str | None] = mapped_column(String(2), default=None)
    website: Mapped[str | None] = mapped_column(String(500), default=None)
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    timezone: Mapped[str] = mapped_column(
        String(64), default=DEFAULT_TIMEZONE, server_default=DEFAULT_TIMEZONE
    )
    #: Reserved for future billing tiers; every organization is "free" today.
    plan: Mapped[str] = mapped_column(String(50), default="free", server_default="free")
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    created_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        Index("ix_memberships_user_id_status", "user_id", "status"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[OrgRole] = mapped_column(_pg_enum(OrgRole, "org_role"))
    status: Mapped[MembershipStatus] = mapped_column(
        _pg_enum(MembershipStatus, "membership_status"),
        default=MembershipStatus.ACTIVE,
        server_default=MembershipStatus.ACTIVE.value,
    )
    joined_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=text("now()"))

    @property
    def is_admin(self) -> bool:
        return self.role is OrgRole.ADMIN

    @property
    def is_active(self) -> bool:
        return self.status is MembershipStatus.ACTIVE


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An emailed invitation to join an organization.

    The partial unique index allows re-inviting an address after the previous
    invitation was accepted or revoked, while preventing two live invitations
    for the same address.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        Index(
            "uq_invitations_org_id_email_pending",
            "org_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        Index("ix_invitations_org_id", "org_id"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[Email]
    role: Mapped[OrgRole] = mapped_column(_pg_enum(OrgRole, "org_role"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    invited_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None] = mapped_column(default=None)
    accepted_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)

    @property
    def is_pending(self) -> bool:
        return self.accepted_at is None and self.revoked_at is None

    def is_usable(self, *, now: datetime | None = None) -> bool:
        return self.is_pending and self.expires_at > (now or utcnow())
