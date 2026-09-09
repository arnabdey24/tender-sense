from __future__ import annotations

from datetime import UTC, datetime

from app.core.time import days_between, local_date, to_timezone


def test_to_timezone_converts_from_utc() -> None:
    moment = datetime(2026, 9, 9, 2, 30, tzinfo=UTC)

    assert to_timezone(moment, "Asia/Dhaka").hour == 8


def test_local_date_rolls_over_before_utc_midnight() -> None:
    """22:00 UTC is already the next day in Dhaka (UTC+6)."""
    moment = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)

    assert local_date(moment, "Asia/Dhaka").isoformat() == "2026-09-10"


def test_days_between_is_negative_for_past_deadlines() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    deadline = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

    assert days_between(now, deadline) == -2


def test_days_between_truncates_partial_days() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    deadline = datetime(2026, 9, 12, 6, 0, tzinfo=UTC)

    assert days_between(now, deadline) == 2
