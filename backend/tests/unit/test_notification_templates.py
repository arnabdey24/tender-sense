"""The templates customers actually receive.

Rendering happens at enqueue time, so a missing context key raises in the
request that caused it rather than silently shipping a broken message. These
tests pin what each template needs and that nothing renders as an empty shell.
"""

from __future__ import annotations

import pytest

from app.modules.notifications.email.renderer import EmailTemplateError, renderer


def digest_context(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "recipient_name": "Rumana",
        "organization_name": "Dhaka Systems",
        "unsubscribe_url": "https://app.invalid/notifications/unsubscribe?token=abc",
        "digest_date": "10 Sep 2026",
        "total_count": 3,
        "top_count": 2,
        "other_count": 1,
        "picks": [
            {
                "grade": "S",
                "eligibility_label": "Eligible",
                "title": "Supply of network equipment",
                "summary": "Strong overlap with your systems integration work.",
                "procuring_entity": "Ministry of ICT",
                "deadline_label": "24 Sep 2026, 14:00",
                "url": "https://app.invalid/app/tenders/1",
            }
        ],
        "needs_verification": [],
        "upcoming_deadlines": [],
        "setup_nudge": None,
    }
    return base | overrides


class TestInstantMatch:
    def test_it_leads_with_the_grade_and_the_title(self) -> None:
        rendered = renderer.render(
            "instant_match",
            {
                "recipient_name": "Rumana",
                "organization_name": "Dhaka Systems",
                "unsubscribe_url": "https://app.invalid/u?token=abc",
                "grade": "S",
                "eligibility_label": "Eligible",
                "tender_title": "Supply of network equipment",
                "tender_url": "https://app.invalid/app/tenders/1",
                "procuring_entity": "Ministry of ICT",
                "source_name": "e-GP Bangladesh",
                "deadline_label": "24 Sep 2026, 14:00",
                "why_matched": ["You have delivered three similar networks."],
                "gaps": [],
            },
        )

        assert rendered.subject == "S-grade match: Supply of network equipment"
        assert "Supply of network equipment" in rendered.text_body
        assert "You have delivered three similar networks." in rendered.html_body

    def test_every_message_carries_a_way_out(self) -> None:
        """Mail people cannot stop is mail they report as spam."""
        rendered = renderer.render(
            "instant_match",
            {
                "recipient_name": "Rumana",
                "organization_name": "Dhaka Systems",
                "unsubscribe_url": "https://app.invalid/u?token=abc",
                "grade": "A",
                "eligibility_label": "Eligible",
                "tender_title": "A tender",
                "tender_url": "https://app.invalid/app/tenders/1",
                "procuring_entity": None,
                "source_name": "World Bank",
                "deadline_label": "no stated deadline",
                "why_matched": [],
                "gaps": [],
            },
        )

        assert "https://app.invalid/u?token=abc" in rendered.html_body
        assert "https://app.invalid/u?token=abc" in rendered.text_body


class TestDailyDigest:
    def test_it_counts_what_came_in(self) -> None:
        rendered = renderer.render("daily_digest", digest_context())

        assert "3 new matches" in rendered.text_body
        assert "Supply of network equipment" in rendered.html_body

    def test_the_subject_is_singular_for_one_match(self) -> None:
        rendered = renderer.render(
            "daily_digest", digest_context(total_count=1, top_count=1, other_count=0)
        )

        assert rendered.subject.startswith("1 new tender worth a look")

    def test_a_quiet_day_can_still_carry_a_nudge(self) -> None:
        """Said in the place someone will read it, rather than nowhere."""
        rendered = renderer.render(
            "daily_digest",
            digest_context(
                total_count=0,
                top_count=0,
                other_count=0,
                picks=[],
                setup_nudge="Your criteria may be too strict.",
            ),
        )

        assert "Your criteria may be too strict." in rendered.text_body

    def test_verification_items_say_why(self) -> None:
        rendered = renderer.render(
            "daily_digest",
            digest_context(
                needs_verification=[
                    {
                        "title": "Road resurfacing",
                        "reason": "turnover requirement could not be read",
                        "url": "https://app.invalid/app/tenders/2",
                    }
                ]
            ),
        )

        assert "turnover requirement could not be read" in rendered.text_body
        assert "not rejections" in rendered.text_body


class TestDeadlineReminder:
    def test_it_says_how_long_is_left(self) -> None:
        rendered = renderer.render(
            "deadline_reminder",
            {
                "recipient_name": "Rumana",
                "organization_name": "Dhaka Systems",
                "unsubscribe_url": "https://app.invalid/u?token=abc",
                "tender_title": "Supply of network equipment",
                "tender_url": "https://app.invalid/app/tenders/1",
                "days_left": 2,
                "deadline_label": "12 Sep 2026, 14:00",
                "procuring_entity": "Ministry of ICT",
                "source_name": "e-GP Bangladesh",
            },
        )

        assert rendered.subject == "2 days left: Supply of network equipment"
        assert "12 Sep 2026, 14:00" in rendered.text_body

    def test_one_day_left_is_not_pluralised(self) -> None:
        rendered = renderer.render(
            "deadline_reminder",
            {
                "recipient_name": "Rumana",
                "organization_name": "Dhaka Systems",
                "unsubscribe_url": "https://app.invalid/u?token=abc",
                "tender_title": "A tender",
                "tender_url": "https://app.invalid/app/tenders/1",
                "days_left": 1,
                "deadline_label": "tomorrow",
                "procuring_entity": None,
                "source_name": "World Bank",
            },
        )

        assert rendered.subject.startswith("1 day left:")


class TestOperatorAndSetupMail:
    def test_recipient_verification_names_the_organization(self) -> None:
        """The reader has to be able to tell whether they expected this."""
        rendered = renderer.render(
            "recipient_verify",
            {
                "recipient_name": "Rumana",
                "organization_name": "Dhaka Systems",
                "verify_url": "https://app.invalid/notifications/verify?token=abc",
            },
        )

        assert "Dhaka Systems" in rendered.subject
        assert "https://app.invalid/notifications/verify?token=abc" in rendered.text_body
        assert "ignore this message" in rendered.text_body

    def test_source_down_reports_the_streak_and_the_error(self) -> None:
        rendered = renderer.render(
            "source_down",
            {
                "source_name": "e-GP Bangladesh",
                "consecutive_failures": 3,
                "last_success_label": "8 Sep 2026, 02:00 UTC",
                "last_error": "HTTP 503 from the servlet",
            },
        )

        assert "3 failed runs in a row" in rendered.text_body
        assert "HTTP 503 from the servlet" in rendered.text_body

    def test_test_email_says_who_sent_it(self) -> None:
        rendered = renderer.render(
            "test_email",
            {"organization_name": "Dhaka Systems", "triggered_by": "rumana@example.com"},
        )

        assert "rumana@example.com" in rendered.text_body


class TestMissingContext:
    def test_a_missing_value_fails_loudly_at_enqueue(self) -> None:
        """Better than shipping a message with a hole in it."""
        with pytest.raises(EmailTemplateError):
            renderer.render("instant_match", {"grade": "S"})
