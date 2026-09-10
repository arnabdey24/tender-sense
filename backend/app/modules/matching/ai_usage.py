"""Tracking what the language model costs, and refusing to spend past a cap.

The budget is a real product constraint, not a nicety: a free-tier key exhausted
at 09:00 would leave every match for the rest of the day with no explanation and
no clue why. Spending is recorded per day so the guard can answer "have we spent
enough today" with one indexed query, and every match keeps its templated
explanation regardless, so hitting the cap degrades the prose rather than the
product.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Index, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.base import Usage
from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import ai_tokens_spent
from app.core.time import utcnow
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

logger = get_logger(__name__)


class AiUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per model call, so cost can be attributed and capped."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_day_purpose", "day", "purpose"),
        Index("ix_ai_usage_org_id_day", "org_id", "day"),
    )

    #: Null for pool-wide work like extraction, which no single tenant owns.
    org_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), default=None
    )
    day: Mapped[date] = mapped_column(Date)
    purpose: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    calls: Mapped[int] = mapped_column(Integer, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)


async def spent_today(session: AsyncSession, *, day: date | None = None) -> int:
    """Tokens consumed today across every purpose and tenant."""
    target = day or utcnow().date()
    total = await session.scalar(
        select(func.coalesce(func.sum(AiUsage.tokens_in + AiUsage.tokens_out), 0)).where(
            AiUsage.day == target
        )
    )
    return int(total or 0)


async def within_budget(session: AsyncSession, *, headroom: int = 0) -> bool:
    """Whether there is room to spend, leaving ``headroom`` for the call itself.

    A budget of zero or less means unlimited — an operator who has not set one
    should not silently get no explanations.
    """
    budget = settings.ai_daily_token_budget
    if budget <= 0:
        return True
    return (await spent_today(session)) + headroom < budget


async def record(
    session: AsyncSession,
    usage: Usage,
    *,
    purpose: str,
    org_id: UUID | None = None,
) -> None:
    """Log one call. Never raises: losing a usage row must not fail the work."""
    try:
        ai_tokens_spent.labels(purpose=purpose).inc(usage.tokens_in + usage.tokens_out)
        session.add(
            AiUsage(
                org_id=org_id,
                day=utcnow().date(),
                purpose=purpose,
                model=usage.model,
                tokens_in=usage.tokens_in,
                tokens_out=usage.tokens_out,
                latency_ms=usage.latency_ms,
            )
        )
        await session.flush()
    except Exception as exc:  # pragma: no cover - accounting must not break work
        logger.warning("ai_usage_not_recorded", purpose=purpose, error=str(exc))
