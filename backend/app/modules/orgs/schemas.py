"""Request and response bodies for organizations, members and invitations."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, TypeAdapter
from pydantic import HttpUrl as _HttpUrl
from pydantic import ValidationError as PydanticValidationError

from app.core.time import DEFAULT_TIMEZONE, utcnow
from app.modules.orgs.models import Invitation, Membership, MembershipStatus, OrgRole
from app.modules.users.models import User

InvitationStatus = Literal["pending", "accepted", "revoked", "expired"]

_url_adapter: TypeAdapter[_HttpUrl] = TypeAdapter(_HttpUrl)


def _validate_country(value: str | None) -> str | None:
    """ISO 3166-1 alpha-2, stored uppercase."""
    if value is None:
        return None
    country = value.strip().upper()
    if not country:
        return None
    if len(country) != 2 or not country.isalpha():
        raise ValueError("country must be a 2-letter ISO 3166-1 alpha-2 code")
    return country


def _validate_website(value: str | None) -> str | None:
    if value is None:
        return None
    website = value.strip()
    if not website:
        return None
    try:
        _url_adapter.validate_python(website)
    except PydanticValidationError as exc:
        raise ValueError("website must be a valid http(s) URL") from exc
    return website


def _validate_timezone(value: str | None) -> str | None:
    """Reject anything the standard library cannot resolve as an IANA zone."""
    if value is None:
        return None
    tz_name = value.strip()
    if not tz_name:
        return None
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"'{tz_name}' is not a valid IANA time zone") from exc
    return tz_name


Name = Annotated[str, Field(min_length=2, max_length=200)]
Country = Annotated[str | None, AfterValidator(_validate_country)]
Website = Annotated[str | None, Field(max_length=500), AfterValidator(_validate_website)]
Description = Annotated[str | None, Field(max_length=2000)]
Timezone = Annotated[str | None, Field(max_length=64), AfterValidator(_validate_timezone)]


class OrganizationCreate(BaseModel):
    name: Name
    country: Country = None
    website: Website = None
    description: Description = None
    timezone: Timezone = DEFAULT_TIMEZONE


class OrganizationUpdate(BaseModel):
    """Every field optional; fields left unset are not touched."""

    name: Name | None = None
    country: Country = None
    website: Website = None
    description: Description = None
    timezone: Timezone = None


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    country: str | None
    website: str | None
    description: str | None
    timezone: str
    plan: str
    created_at: datetime


class MemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str
    full_name: str
    avatar_url: str | None
    role: OrgRole
    status: MembershipStatus
    joined_at: datetime

    @classmethod
    def from_row(cls, membership: Membership, user: User) -> MemberRead:
        return cls(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            avatar_url=user.avatar_url,
            role=membership.role,
            status=membership.status,
            joined_at=membership.joined_at,
        )


class MemberUpdate(BaseModel):
    role: OrgRole | None = None
    status: MembershipStatus | None = None


class InvitationCreate(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: OrgRole
    expires_at: datetime
    created_at: datetime
    invited_by_name: str | None
    status: InvitationStatus

    @classmethod
    def from_invitation(
        cls,
        invitation: Invitation,
        *,
        invited_by_name: str | None = None,
        now: datetime | None = None,
    ) -> InvitationRead:
        return cls(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            invited_by_name=invited_by_name,
            status=invitation_status(invitation, now=now),
        )


class InvitationPreview(BaseModel):
    """Public, unauthenticated view of an invitation.

    Deliberately narrow: anyone holding the token can read this, so it exposes
    only what the accept screen needs and nothing else about the organization.
    """

    org_name: str
    inviter_name: str | None
    role: OrgRole
    email: str
    expires_at: datetime
    requires_signup: bool


def invitation_status(invitation: Invitation, *, now: datetime | None = None) -> InvitationStatus:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= (now or utcnow()):
        return "expired"
    return "pending"
