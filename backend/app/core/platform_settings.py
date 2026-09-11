"""Operator-tunable limits, stored rather than deployed.

Rate limits arrived as environment variables, which makes every adjustment a
redeploy — and the moments that call for one are exactly the moments nobody
wants to redeploy: a portal being hammered on a demo day, a tenant burning the
model budget, a login throttle turning out to be tighter than a real office of
forty people sharing one address. So the numbers that an operator might need to
move at three in the afternoon live in the database, editable from the admin
console, with the environment providing the default.

The environment is still the floor: an unset key means "whatever the deployment
was configured with", so a fresh database behaves exactly as it does today and
removing an override restores that rather than some remembered number.

Reads are cached for a few seconds. These are consulted on the login path, so a
database round trip per attempt would be a poor trade for a value that changes
a handful of times a year — and a few seconds of staleness after an edit is not
a property anyone can observe on a ten-minute cooldown.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import String, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base

logger = get_logger(__name__)

#: Seconds a resolved set of limits is reused before the row is read again.
CACHE_TTL = 5.0

_cache: tuple[float, Limits] | None = None


class PlatformSetting(Base):
    """One stored override. Key-per-row so an edit touches only what it names."""

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")


class Limits(BaseModel):
    """Every limit an operator can move, with the deployment's value as default."""

    source_sync_cooldown_seconds: int = Field(
        ge=0,
        le=86_400,
        description="Shortest gap between hand-started portal syncs, deployment-wide.",
    )
    ai_daily_token_budget: int = Field(
        ge=0, description="Model tokens per day across every tenant. 0 disables the cap."
    )
    assistant_daily_turn_limit: int = Field(
        ge=0, description="Assistant messages per organization per day. 0 is unlimited."
    )
    assistant_daily_voice_seconds: int = Field(
        ge=0, description="Live voice seconds per organization per day. 0 is unlimited."
    )
    login_attempts_per_ip: int = Field(
        ge=1, le=1000, description="Sign-in attempts allowed from one address per window."
    )
    login_attempts_per_email: int = Field(
        ge=1, le=1000, description="Sign-in attempts allowed against one account per window."
    )
    login_window_seconds: int = Field(
        ge=60, le=86_400, description="The window both sign-in limits are counted over."
    )

    @classmethod
    def from_environment(cls) -> Limits:
        return cls(
            source_sync_cooldown_seconds=settings.source_sync_cooldown_seconds,
            ai_daily_token_budget=settings.ai_daily_token_budget,
            assistant_daily_turn_limit=settings.assistant_daily_turn_limit,
            assistant_daily_voice_seconds=settings.assistant_daily_voice_seconds,
            login_attempts_per_ip=settings.login_attempts_per_ip,
            login_attempts_per_email=settings.login_attempts_per_email,
            login_window_seconds=settings.login_window_seconds,
        )


#: The one stored key. Grouped rather than a row per field, because these are
#: read together on every request that checks any of them.
LIMITS_KEY = "limits"


async def get_limits(session: AsyncSession, *, fresh: bool = False) -> Limits:
    """The limits in force, environment defaults with any stored override applied."""
    global _cache
    now = time.monotonic()
    if not fresh and _cache is not None and now - _cache[0] < CACHE_TTL:
        return _cache[1]

    stored = await session.scalar(
        select(PlatformSetting.value).where(PlatformSetting.key == LIMITS_KEY)
    )
    limits = Limits.from_environment()
    if stored:
        try:
            limits = Limits(**{**limits.model_dump(), **stored})
        except Exception as exc:  # pragma: no cover - a bad row must not lock anyone out
            logger.warning("platform_limits_invalid", error=str(exc))
            limits = Limits.from_environment()

    _cache = (now, limits)
    return limits


async def set_limits(session: AsyncSession, limits: Limits) -> Limits:
    """Store the full set, and make the next read see it rather than the cache."""
    await session.execute(
        insert(PlatformSetting)
        .values(key=LIMITS_KEY, value=limits.model_dump())
        .on_conflict_do_update(index_elements=["key"], set_={"value": limits.model_dump()})
    )
    await session.flush()
    invalidate()
    return limits


async def reset_limits(session: AsyncSession) -> Limits:
    """Drop the override so the deployment's own configuration applies again."""
    await session.execute(delete(PlatformSetting).where(PlatformSetting.key == LIMITS_KEY))
    await session.flush()
    invalidate()
    return Limits.from_environment()


def invalidate() -> None:
    """Forget the cached limits. Called after a write, and by tests."""
    global _cache
    _cache = None
