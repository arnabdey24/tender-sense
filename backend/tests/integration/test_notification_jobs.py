"""Instant alerts, the digest dispatcher and the deadline sweep.

These are the jobs that mail real people on a schedule, so the properties under
test are the ones a customer would notice being wrong: an alert that fires for
something it should not, a digest that arrives twice, a reminder that repeats
at three in the morning.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from uuid import uuid4

import pytest
import time_machine
from sqlalchemy import delete, select

from app.core.security import generate_token
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.jobs.tasks.notifications import (
    deadline_reminder_sweep,
    digest_dispatcher,
    notify_instant,
    notify_tender_updated,
    send_daily_digest,
)
from app.modules.decisions.models import Decision, TenderDecision
from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    Recommendation,
    TenderMatch,
    Urgency,
)
from app.modules.notifications.models import (
    EmailOutbox,
    Notification,
    NotificationLedger,
    NotificationRecipient,
    NotificationSettings,
    NotificationType,
)
from app.modules.orgs.models import Organization
from app.modules.tenders.models import Tender, TenderSource, TenderStatus


@dataclass
class Fixture:
    org: Organization
    tender: Tender
    source: TenderSource


@pytest.fixture
async def scene() -> AsyncIterator[Fixture]:
    """One organization, one verified recipient, one open tender."""
    async with session_scope() as session:
        org = Organization(name="Meghna", slug=f"meghna-{uuid4().hex[:8]}", timezone="Asia/Dhaka")
        source = TenderSource(
            code=f"n-{uuid4().hex[:8]}", name="Test portal", adapter_key="manual", base_url=""
        )
        session.add_all([org, source])
        await session.flush()
        tender = Tender(
            source_id=source.id,
            external_id=uuid4().hex,
            canonical_url="https://example.test/n/1",
            title="Supply of enterprise network switches",
            procuring_entity="Ministry of ICT",
            content_hash=uuid4().hex,
            deadline_at=utcnow() + timedelta(days=30),
            status=TenderStatus.OPEN,
        )
        session.add(tender)
        session.add(
            NotificationRecipient(
                org_id=org.id,
                email=f"bids-{uuid4().hex[:8]}@tsense-test.io",
                verified_at=utcnow(),
                unsubscribe_token=generate_token(),
            )
        )
        await session.flush()
        await session.refresh(org)
        await session.refresh(tender)
        await session.refresh(source)
        created = Fixture(org=org, tender=tender, source=source)

    yield created

    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.org_id == created.org.id))
        await session.execute(delete(Organization).where(Organization.id == created.org.id))
        await session.execute(delete(TenderSource).where(TenderSource.id == created.source.id))


async def add_match(
    scene: Fixture,
    *,
    grade: MatchGrade = MatchGrade.S,
    eligibility: EligibilityStatus = EligibilityStatus.ELIGIBLE,
    first_matched_at: datetime | None = None,
) -> TenderMatch:
    async with session_scope() as session:
        match = TenderMatch(
            org_id=scene.org.id,
            tender_id=scene.tender.id,
            similarity=0.82,
            grade=grade,
            eligibility_status=eligibility,
            recommendation=Recommendation.BID,
            urgency=Urgency.NORMAL,
            inputs_fingerprint=uuid4().hex,
            first_matched_at=first_matched_at or utcnow(),
            explanation={"summary": "Strong overlap with your networking work."},
        )
        session.add(match)
        await session.flush()
        await session.refresh(match)
        return match


async def set_preferences(org_id: Any, **values: Any) -> None:
    async with session_scope() as session:
        record = await session.scalar(
            select(NotificationSettings).where(NotificationSettings.org_id == org_id)
        )
        if record is None:
            record = NotificationSettings(org_id=org_id)
            session.add(record)
        for field, value in values.items():
            setattr(record, field, value)
        await session.flush()


async def queued_emails(org_id: Any, template: str | None = None) -> list[EmailOutbox]:
    async with session_scope() as session:
        stmt = select(EmailOutbox).where(EmailOutbox.org_id == org_id)
        if template:
            stmt = stmt.where(EmailOutbox.template_key == template)
        return list((await session.scalars(stmt.order_by(EmailOutbox.created_at))).all())


async def in_app(org_id: Any) -> list[Notification]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(Notification)
            .where(Notification.org_id == org_id)
            .order_by(Notification.created_at)
        )
        return list(rows.all())


async def digest_queued_for(org_id: Any) -> bool:
    """Whether the dispatcher actually queued *this* organization.

    The count it returns is global, and the database an integration run shares
    may hold seeded organizations that are also due — so the assertion has to
    name the tenant rather than count the queue.
    """
    from app.jobs.queue import get_queue

    queue = await get_queue()
    return bool(await queue.exists(f"arq:job:digest:{org_id}"))


async def clear_digest_job(org_id: Any) -> None:
    from app.jobs.queue import get_queue

    queue = await get_queue()
    await queue.delete(f"arq:job:digest:{org_id}")


class TestInstantAlerts:
    async def test_a_strong_eligible_match_is_mailed_and_shown_in_app(self, scene: Fixture) -> None:
        await add_match(scene)

        result = await notify_instant({}, str(scene.tender.id))

        assert result["alerted"] == 1
        emails = await queued_emails(scene.org.id, "instant_match")
        assert len(emails) == 1
        assert "Supply of enterprise network switches" in emails[0].subject
        assert [n.type for n in await in_app(scene.org.id)] == [NotificationType.INSTANT_MATCH]

    async def test_a_weaker_grade_does_not_interrupt_anyone(self, scene: Fixture) -> None:
        """ "Drop what you are doing" is a claim. Making it about a B-grade match
        is how a product gets filtered."""
        await add_match(scene, grade=MatchGrade.B)

        result = await notify_instant({}, str(scene.tender.id))

        assert result["alerted"] == 0
        assert await queued_emails(scene.org.id, "instant_match") == []

    async def test_an_ineligible_match_is_not_mailed_by_default(self, scene: Fixture) -> None:
        """Telling someone to drop everything for a tender they cannot bid on is
        worse than saying nothing."""
        await add_match(scene, eligibility=EligibilityStatus.INELIGIBLE)

        result = await notify_instant({}, str(scene.tender.id))

        assert result["alerted"] == 0

    async def test_lowering_the_bar_lets_a_weaker_match_through(self, scene: Fixture) -> None:
        await set_preferences(scene.org.id, instant_min_grade="B")
        await add_match(scene, grade=MatchGrade.A)

        result = await notify_instant({}, str(scene.tender.id))

        assert result["alerted"] == 1

    async def test_running_twice_alerts_once(self, scene: Fixture) -> None:
        """Jobs retry. A second "drop everything" about the same tender is how
        people learn to ignore the first."""
        await add_match(scene)

        await notify_instant({}, str(scene.tender.id))
        second = await notify_instant({}, str(scene.tender.id))

        assert second["alerted"] == 0
        assert len(await queued_emails(scene.org.id, "instant_match")) == 1

    async def test_a_closed_tender_alerts_nobody(self, scene: Fixture) -> None:
        await add_match(scene)
        async with session_scope() as session:
            tender = await session.get(Tender, scene.tender.id)
            assert tender is not None
            tender.status = TenderStatus.CLOSED

        result = await notify_instant({}, str(scene.tender.id))

        assert result["skipped_reason"] == "tender_not_open"

    async def test_an_unverified_address_receives_nothing(self, scene: Fixture) -> None:
        """The in-app entry still appears — it needs no address to be proven."""
        async with session_scope() as session:
            await session.execute(
                delete(NotificationRecipient).where(NotificationRecipient.org_id == scene.org.id)
            )
            session.add(
                NotificationRecipient(
                    org_id=scene.org.id,
                    email="unproven@tsense-test.io",
                    unsubscribe_token=generate_token(),
                )
            )
        await add_match(scene)

        await notify_instant({}, str(scene.tender.id))

        assert await queued_emails(scene.org.id, "instant_match") == []
        assert len(await in_app(scene.org.id)) == 1

    async def test_an_unsubscribed_address_receives_nothing(self, scene: Fixture) -> None:
        async with session_scope() as session:
            recipient = await session.scalar(
                select(NotificationRecipient).where(NotificationRecipient.org_id == scene.org.id)
            )
            assert recipient is not None
            recipient.unsubscribed_at = utcnow()
        await add_match(scene)

        await notify_instant({}, str(scene.tender.id))

        assert await queued_emails(scene.org.id, "instant_match") == []


class TestTenderUpdates:
    async def test_only_organizations_bidding_are_told(self, scene: Fixture) -> None:
        result = await notify_tender_updated({}, str(scene.tender.id))

        assert result["notified"] == 0

    async def test_a_bidder_is_told_once_per_amendment(self, scene: Fixture) -> None:
        async with session_scope() as session:
            session.add(
                TenderDecision(
                    org_id=scene.org.id,
                    tender_id=scene.tender.id,
                    decision=Decision.BID,
                    is_current=True,
                )
            )

        first = await notify_tender_updated({}, str(scene.tender.id))
        second = await notify_tender_updated({}, str(scene.tender.id))

        assert first["notified"] == 1
        assert second["notified"] == 0
        titles = [n.title for n in await in_app(scene.org.id)]
        assert titles == [f"Updated by the portal: {scene.tender.title}"]


class TestDigest:
    async def test_it_gathers_matches_since_the_last_one(self, scene: Fixture) -> None:
        await add_match(scene)

        result = await send_daily_digest({}, str(scene.org.id))

        assert result["matches"] == 1
        emails = await queued_emails(scene.org.id, "daily_digest")
        assert len(emails) == 1
        assert "Supply of enterprise network switches" in emails[0].html_body

    async def test_a_second_run_the_same_day_sends_nothing(self, scene: Fixture) -> None:
        await add_match(scene)

        await send_daily_digest({}, str(scene.org.id))
        second = await send_daily_digest({}, str(scene.org.id))

        assert second["skipped_reason"] == "already_sent_today"
        assert len(await queued_emails(scene.org.id, "daily_digest")) == 1

    async def test_a_quiet_day_sends_no_email_at_all(self, scene: Fixture) -> None:
        """An empty digest every morning is how a daily email becomes a filter
        rule. Silence says the same thing."""
        result = await send_daily_digest({}, str(scene.org.id))

        assert result["skipped_reason"] == "nothing_to_report"
        assert await queued_emails(scene.org.id, "daily_digest") == []

    async def test_a_weak_match_is_counted_but_not_featured(self, scene: Fixture) -> None:
        await set_preferences(scene.org.id, digest_min_grade="C")
        await add_match(scene, grade=MatchGrade.C)

        result = await send_daily_digest({}, str(scene.org.id))

        assert result["matches"] == 1

    async def test_an_ineligible_match_never_reaches_the_shortlist(self, scene: Fixture) -> None:
        await add_match(scene, eligibility=EligibilityStatus.INELIGIBLE)

        result = await send_daily_digest({}, str(scene.org.id))

        assert result["matches"] == 0


class TestDigestDispatcher:
    async def test_it_waits_until_the_organizations_own_morning(self, scene: Fixture) -> None:
        """08:00 in Dhaka is 02:00 UTC. Dispatching on server time would mail a
        Bangladeshi company its "morning" shortlist in the afternoon."""
        await set_preferences(scene.org.id, digest_time=time(8, 0), digest_timezone="Asia/Dhaka")
        await clear_digest_job(scene.org.id)

        # 23:00 UTC is 05:00 the next day in Dhaka — before the send time.
        with time_machine.travel(datetime(2026, 9, 9, 23, 0, tzinfo=UTC), tick=False):
            await digest_dispatcher({})
        early = await digest_queued_for(scene.org.id)

        # 03:00 UTC is 09:00 in Dhaka, so the send time has passed.
        with time_machine.travel(datetime(2026, 9, 10, 3, 0, tzinfo=UTC), tick=False):
            await digest_dispatcher({})
        due = await digest_queued_for(scene.org.id)

        assert early is False
        assert due is True

    async def test_it_does_not_queue_twice_in_one_local_day(self, scene: Fixture) -> None:
        """The dispatcher wakes four times an hour; the stamp is what stops four
        digests."""
        await set_preferences(
            scene.org.id,
            digest_time=time(8, 0),
            digest_timezone="Asia/Dhaka",
            last_digest_sent_for=datetime(2026, 9, 10, tzinfo=UTC).date(),
        )
        await clear_digest_job(scene.org.id)

        with time_machine.travel(datetime(2026, 9, 10, 3, 0, tzinfo=UTC), tick=False):
            await digest_dispatcher({})

        assert await digest_queued_for(scene.org.id) is False

    async def test_a_disabled_digest_is_never_queued(self, scene: Fixture) -> None:
        await set_preferences(scene.org.id, digest_enabled=False, digest_time=time(0, 1))
        await clear_digest_job(scene.org.id)

        with time_machine.travel(datetime(2026, 9, 10, 12, 0, tzinfo=UTC), tick=False):
            await digest_dispatcher({})

        assert await digest_queued_for(scene.org.id) is False


class TestDeadlineReminders:
    async def _bid_closing_in(self, scene: Fixture, days: int) -> None:
        async with session_scope() as session:
            tender = await session.get(Tender, scene.tender.id)
            assert tender is not None
            # Mid-afternoon, so "days between" is unambiguous either side.
            tender.deadline_at = utcnow() + timedelta(days=days, hours=1)
            session.add(
                TenderDecision(
                    org_id=scene.org.id,
                    tender_id=scene.tender.id,
                    decision=Decision.BID,
                    is_current=True,
                )
            )
        await set_preferences(scene.org.id)

    async def test_a_bid_closing_at_an_offset_is_reminded(self, scene: Fixture) -> None:
        await self._bid_closing_in(scene, 7)

        result = await deadline_reminder_sweep({})

        assert result["reminders"] == 1
        emails = await queued_emails(scene.org.id, "deadline_reminder")
        assert emails and "7 days left" in emails[0].subject

    async def test_a_bid_between_offsets_is_left_alone(self, scene: Fixture) -> None:
        await self._bid_closing_in(scene, 5)

        result = await deadline_reminder_sweep({})

        assert result["reminders"] == 0

    async def test_the_sweep_runs_hourly_and_reminds_once(self, scene: Fixture) -> None:
        """A second "2 days left" at three in the morning teaches people to mute
        the sender."""
        await self._bid_closing_in(scene, 2)

        await deadline_reminder_sweep({})
        await deadline_reminder_sweep({})

        assert len(await queued_emails(scene.org.id, "deadline_reminder")) == 1
        assert len(await in_app(scene.org.id)) == 1

    async def test_the_seven_and_two_day_nudges_are_different_messages(
        self, scene: Fixture
    ) -> None:
        await self._bid_closing_in(scene, 7)
        await deadline_reminder_sweep({})

        async with session_scope() as session:
            tender = await session.get(Tender, scene.tender.id)
            assert tender is not None
            tender.deadline_at = utcnow() + timedelta(days=2, hours=1)
        await deadline_reminder_sweep({})

        subjects = [e.subject for e in await queued_emails(scene.org.id, "deadline_reminder")]
        assert len(subjects) == 2
        assert any("7 days left" in s for s in subjects)
        assert any("2 days left" in s for s in subjects)

    async def test_a_tender_nobody_committed_to_is_not_a_reminder(self, scene: Fixture) -> None:
        async with session_scope() as session:
            tender = await session.get(Tender, scene.tender.id)
            assert tender is not None
            tender.deadline_at = utcnow() + timedelta(days=7, hours=1)
            session.add(
                TenderDecision(
                    org_id=scene.org.id,
                    tender_id=scene.tender.id,
                    decision=Decision.HOLD,
                    is_current=True,
                )
            )
        await set_preferences(scene.org.id)

        result = await deadline_reminder_sweep({})

        assert result["reminders"] == 0

    async def test_turning_reminders_off_stops_them(self, scene: Fixture) -> None:
        await self._bid_closing_in(scene, 7)
        await set_preferences(scene.org.id, reminders_enabled=False)

        result = await deadline_reminder_sweep({})

        assert result["reminders"] == 0


class TestLedger:
    async def test_it_records_what_was_sent(self, scene: Fixture) -> None:
        await add_match(scene)

        await notify_instant({}, str(scene.tender.id))

        async with session_scope() as session:
            rows = list(
                (
                    await session.scalars(
                        select(NotificationLedger).where(NotificationLedger.org_id == scene.org.id)
                    )
                ).all()
            )
        assert [row.type for row in rows] == [NotificationType.INSTANT_MATCH]
        assert rows[0].subject_key == str(scene.tender.id)
        assert rows[0].recipients == 1
