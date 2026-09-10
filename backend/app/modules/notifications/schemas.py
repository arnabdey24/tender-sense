"""Request and response bodies for notification settings, recipients and the centre."""

from __future__ import annotations

from datetime import datetime, time
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.time import DEFAULT_TIMEZONE
from app.modules.notifications.models import NotificationType

Grade = Annotated[str, Field(pattern="^[SABC]$")]

#: Reminder offsets are days before a deadline. Zero would mean "on the day it
#: closes", which is too late to act on and duplicates the digest.
ReminderOffsets = Annotated[list[int], Field(max_length=6)]


def _validate_timezone(value: str) -> str:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"{value!r} is not a known IANA timezone.") from exc
    return value


class NotificationSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    inapp_enabled: bool
    instant_enabled: bool
    instant_min_grade: str
    instant_requires_eligible: bool
    digest_enabled: bool
    digest_time: time
    digest_timezone: str
    digest_min_grade: str
    reminders_enabled: bool
    reminder_offsets: list[int]


class NotificationSettingsUpdate(BaseModel):
    """Every field optional: the form patches what the user actually changed."""

    inapp_enabled: bool | None = None
    instant_enabled: bool | None = None
    instant_min_grade: Grade | None = None
    instant_requires_eligible: bool | None = None
    digest_enabled: bool | None = None
    digest_time: time | None = None
    digest_timezone: str | None = Field(default=None, max_length=64)
    digest_min_grade: Grade | None = None
    reminders_enabled: bool | None = None
    reminder_offsets: ReminderOffsets | None = None

    @field_validator("digest_timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        """A typo here would silently move a company's digest by hours."""
        return None if value is None else _validate_timezone(value)

    @field_validator("reminder_offsets")
    @classmethod
    def _sane_offsets(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        for offset in value:
            if not 1 <= offset <= 60:
                raise ValueError("Reminder offsets must be between 1 and 60 days.")
        # Descending and de-duplicated, so the seven-day nudge precedes the
        # two-day one and a repeated number cannot mail twice.
        return sorted(set(value), reverse=True)


class RecipientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None = None
    types: list[str] = Field(default_factory=list)
    verified_at: datetime | None = None
    unsubscribed_at: datetime | None = None
    created_at: datetime


class RecipientCreate(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=200)
    types: list[NotificationType] = Field(default_factory=list)


class RecipientUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    types: list[NotificationType] | None = None


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: NotificationType
    title: str
    body: str | None = None
    link: str | None = None
    tender_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    read: bool = False


class UnreadCount(BaseModel):
    unread: int


class TestEmailRequest(BaseModel):
    """Send a test message. Defaults to the signed-in user's own address."""

    email: EmailStr | None = None


class TestEmailResponse(BaseModel):
    queued: bool
    to_email: str


class PublicActionResponse(BaseModel):
    """Answer to an unauthenticated verify/unsubscribe link."""

    status: str
    email: str | None = None
    organization: str | None = None


DEFAULT_DIGEST_TIMEZONE = DEFAULT_TIMEZONE
