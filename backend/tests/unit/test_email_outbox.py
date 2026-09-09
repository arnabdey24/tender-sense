"""Pure outbox logic: the retry schedule and the message we hand to SMTP."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.core.config import settings
from app.modules.notifications.email.outbox import MAX_ERROR_LENGTH, backoff_delay
from app.modules.notifications.email.sender import build_message
from app.modules.notifications.models import RETRY_BACKOFF_MINUTES, EmailOutbox

EXPECTED_MINUTES = [1, 5, 30, 120, 720]


@pytest.mark.parametrize(("attempts", "minutes"), list(enumerate(EXPECTED_MINUTES, start=1)))
def test_backoff_follows_the_configured_schedule(attempts: int, minutes: int) -> None:
    assert backoff_delay(attempts) == timedelta(minutes=minutes)


def test_backoff_repeats_its_last_step_forever() -> None:
    last = timedelta(minutes=EXPECTED_MINUTES[-1])

    assert backoff_delay(len(EXPECTED_MINUTES) + 1) == last
    assert backoff_delay(99) == last


def test_backoff_is_defensive_about_a_zero_attempt_count() -> None:
    assert backoff_delay(0) == timedelta(minutes=EXPECTED_MINUTES[0])


def test_schedule_matches_the_model_constant() -> None:
    assert list(RETRY_BACKOFF_MINUTES) == EXPECTED_MINUTES


def test_the_schedule_outlasts_the_attempt_budget() -> None:
    """A message must never exhaust its retries in under a few hours."""
    total = sum(
        backoff_delay(attempt).total_seconds() for attempt in range(1, settings.email_max_attempts)
    )

    assert total >= timedelta(hours=2).total_seconds()


def _outbox_row(**overrides: object) -> EmailOutbox:
    values: dict[str, object] = {
        "to_email": "recipient@example.test",
        "template_key": "verify_email",
        "subject": "Confirm your email address",
        "html_body": "<p>Hello</p>",
        "text_body": "Hello",
        "context": {},
    }
    values.update(overrides)
    return EmailOutbox(**values)


def test_message_carries_both_alternatives() -> None:
    message = build_message(_outbox_row())

    assert message.get_content_type() == "multipart/alternative"
    assert message["To"] == "recipient@example.test"
    assert message["From"] == settings.email_from
    assert message["Message-ID"]
    parts = [part.get_content_type() for part in message.iter_parts()]  # type: ignore[union-attr]
    assert parts == ["text/plain", "text/html"]


def test_display_name_is_used_when_present() -> None:
    message = build_message(_outbox_row(to_name="Ayesha Rahman"))

    assert message["To"] == "Ayesha Rahman <recipient@example.test>"


def test_list_unsubscribe_is_only_added_when_the_context_has_a_url() -> None:
    assert build_message(_outbox_row())["List-Unsubscribe"] is None

    with_url = build_message(
        _outbox_row(context={"unsubscribe_url": "https://app.test/unsubscribe/abc"})
    )

    assert with_url["List-Unsubscribe"] == "<https://app.test/unsubscribe/abc>"


def test_error_truncation_bound_is_sane() -> None:
    assert 0 < MAX_ERROR_LENGTH <= 10_000
