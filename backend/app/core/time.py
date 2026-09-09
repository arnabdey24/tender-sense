"""Time helpers. Everything stored is timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Dhaka"


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_timezone(moment: datetime, tz_name: str) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(ZoneInfo(tz_name))


def local_date(moment: datetime, tz_name: str) -> date:
    return to_timezone(moment, tz_name).date()


def days_between(start: datetime, end: datetime) -> int:
    """Whole days from ``start`` to ``end``; negative when ``end`` is in the past."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return (end - start) // timedelta(days=1)
