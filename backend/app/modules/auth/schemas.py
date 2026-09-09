"""Request and response bodies for authentication."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.config import settings
from app.modules.orgs.models import OrgRole


def _validate_password_strength(value: str) -> str:
    """Length is the control that matters; a character-class rule mostly pushes
    people towards predictable substitutions."""
    if len(value) < settings.password_min_length:
        raise ValueError(f"Password must be at least {settings.password_min_length} characters")
    if len(value) > 200:
        raise ValueError("Password must be at most 200 characters")
    if value.strip() == "":
        raise ValueError("Password must not be blank")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1, max_length=200)

    _check_password = field_validator("password")(_validate_password_strength)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name must not be blank")
        return stripped


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=1)


class EmailRequest(BaseModel):
    """Used by resend-verification and forgot-password."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1)
    password: str

    _check_password = field_validator("password")(_validate_password_strength)


class ChangePasswordRequest(BaseModel):
    current_password: str | None = None
    """Omitted only by accounts that have no password yet (Google sign-in)."""
    new_password: str

    _check_password = field_validator("new_password")(_validate_password_strength)


class SwitchOrgRequest(BaseModel):
    org_id: UUID


class MembershipSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    org_id: UUID
    org_name: str
    org_slug: str
    role: OrgRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    avatar_url: str | None = None
    email_verified: bool
    has_password: bool = True
    """False for accounts created through Google that never set a password.

    The account page uses this to decide whether to ask for the current
    password before setting a new one.
    """
    is_superuser: bool = False
    created_at: datetime


class SessionResponse(BaseModel):
    """Returned by login, refresh, verify-email, reset-password and switch-org.

    The refresh token is not in the body — it is set as an HttpOnly cookie.
    """

    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead
    memberships: list[MembershipSummary] = Field(default_factory=list)
    active_org_id: UUID | None = None


class RegisterResponse(BaseModel):
    """Registration does not sign the user in; they must verify first."""

    user: UserRead
    verification_email_sent: bool = True


class MessageResponse(BaseModel):
    message: str
