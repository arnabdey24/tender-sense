"""Telling people about their matches, exactly once.

Three shapes of message, each with a different failure that matters:

* **Instant alerts** must not fire for anything less than the thing they claim
  to be. "Drop what you are doing" is a claim, and a product that makes it
  about a mediocre match gets filtered.
* **The digest** must arrive in the reader's morning, not the server's, and
  must not arrive twice because a dispatcher woke twice in the same hour.
* **Deadline reminders** exist only for tenders someone actually committed to,
  and must never repeat — a second "2 days left" at 3 a.m. teaches people to
  mute the sender.

Every one of them claims the ledger before enqueuing anything, so a crash
between deciding and sending costs a message rather than duplicating one.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import days_between, local_date, to_timezone, utcnow
from app.db.session import session_scope
from app.jobs.tracking import tracked_job
from app.modules.decisions.models import Decision, TenderDecision
from app.modules.matching.models import EligibilityStatus, TenderMatch
from app.modules.notifications import service as notif
from app.modules.notifications.models import NotificationSettings, NotificationType
from app.modules.orgs.models import Organization
from app.modules.tenders.models import Tender, TenderSource, TenderStatus

logger = get_logger(__name__)

#: Picks shown in full in a digest. Beyond this the reader is scanning, not
#: reading, and the point of a shortlist is that it is short.
DIGEST_PICKS = 5
DIGEST_VERIFY_ITEMS = 5
DIGEST_UPCOMING_ITEMS = 5

#: How far ahead the digest lists bids already in flight.
UPCOMING_WINDOW_DAYS = 14


def deadline_label(deadline_at: datetime | None, tz_name: str) -> str:
    """A deadline in the reader's own timezone, not the server's."""
    if deadline_at is None:
        return "no stated deadline"
    local = to_timezone(deadline_at, tz_name)
    return local.strftime("%-d %b %Y, %H:%M")


def tender_url(tender_id: UUID) -> str:
    return notif.app_link(f"/app/tenders/{tender_id}")


ELIGIBILITY_LABELS = {
    EligibilityStatus.ELIGIBLE: "Eligible",
    EligibilityStatus.NEEDS_VERIFICATION: "Needs checking",
    EligibilityStatus.INELIGIBLE: "Not eligible",
}


def _explanation_list(match: TenderMatch, key: str) -> list[str]:
    value = (match.explanation or {}).get(key)
    return [str(item) for item in value][:3] if isinstance(value, list) else []


def _first_blocker(match: TenderMatch) -> str:
    """Why a match needs checking, in the reader's words rather than a status."""
    for result in match.rule_results or []:
        if isinstance(result, dict) and result.get("status") == "unknown":
            reason = result.get("reason") or result.get("label")
            if reason:
                return str(reason)
    return "a requirement could not be read from the notice"


# --- instant alerts ------------------------------------------------------


@tracked_job
async def notify_instant(ctx: dict[str, Any], tender_id: str) -> dict[str, Any]:
    """Alert every organization whose verdict on this notice clears their bar.

    Runs after matching rather than inside it, so a mail outage cannot cost
    anyone their match — and so an alert is never sent for a verdict that was
    then rolled back.
    """
    result: dict[str, Any] = {"tender_id": tender_id, "alerted": 0, "skipped": 0}

    async with session_scope() as session:
        tender = await session.get(Tender, UUID(tender_id))
        if tender is None:
            return result | {"error": "tender_not_found"}
        if tender.status is not TenderStatus.OPEN:
            # An alert about a closed notice is an interruption with nothing
            # on the other end of it.
            return result | {"skipped_reason": "tender_not_open"}

        source = await session.get(TenderSource, tender.source_id)
        matches = list(
            (
                await session.scalars(
                    select(TenderMatch).where(
                        TenderMatch.tender_id == tender.id,
                        TenderMatch.instant_notified_at.is_(None),
                    )
                )
            ).all()
        )

        for match in matches:
            org = await session.get(Organization, match.org_id)
            if org is None or not org.is_active:
                continue
            preferences = await notif.settings_for(session, org)
            if not _qualifies_for_instant(match, preferences):
                result["skipped"] += 1
                continue

            # Stamped whether or not anyone is reachable by email: the point is
            # that this verdict has been announced, and the in-app entry counts.
            match.instant_notified_at = utcnow()

            if preferences.inapp_enabled:
                await notif.notify(
                    session,
                    org_id=org.id,
                    notification_type=NotificationType.INSTANT_MATCH,
                    title=f"Grade {match.grade.value} match: {tender.title}",
                    body=(match.explanation or {}).get("summary"),
                    link=f"/app/tenders/{tender.id}",
                    tender_id=tender.id,
                    data={"grade": match.grade.value, "similarity": round(match.similarity, 4)},
                )

            await notif.send_to_recipients(
                session,
                org=org,
                notification_type=NotificationType.INSTANT_MATCH,
                template_key="instant_match",
                subject_key=str(tender.id),
                context={
                    "grade": match.grade.value,
                    "eligibility_label": ELIGIBILITY_LABELS[match.eligibility_status],
                    "tender_title": tender.title,
                    "tender_url": tender_url(tender.id),
                    "procuring_entity": tender.procuring_entity,
                    "source_name": source.name if source else "a portal",
                    "deadline_label": deadline_label(tender.deadline_at, org.timezone),
                    "why_matched": _explanation_list(match, "why_matched"),
                    "gaps": _explanation_list(match, "gaps"),
                },
            )
            result["alerted"] += 1

    logger.info("instant_alerts_sent", **result)
    return result


def _qualifies_for_instant(match: TenderMatch, preferences: NotificationSettings) -> bool:
    if not preferences.instant_enabled:
        return False
    if not notif.grade_at_least(match.grade.value, preferences.instant_min_grade):
        return False
    if preferences.instant_requires_eligible:
        return match.eligibility_status is EligibilityStatus.ELIGIBLE
    return match.eligibility_status is not EligibilityStatus.INELIGIBLE


@tracked_job
async def notify_tender_updated(ctx: dict[str, Any], tender_id: str) -> dict[str, Any]:
    """Tell organizations that are bidding when a portal amends the notice.

    Only those with a current *bid* decision. A changed deadline or scope on a
    tender someone is actively writing a proposal for is the one amendment
    worth interrupting them about; the rest is noise.
    """
    result: dict[str, Any] = {"tender_id": tender_id, "notified": 0}

    async with session_scope() as session:
        tender = await session.get(Tender, UUID(tender_id))
        if tender is None:
            return result | {"error": "tender_not_found"}

        decisions = list(
            (
                await session.scalars(
                    select(TenderDecision).where(
                        TenderDecision.tender_id == tender.id,
                        TenderDecision.is_current.is_(True),
                        TenderDecision.decision == Decision.BID,
                    )
                )
            ).all()
        )

        for decision in decisions:
            # Keyed by version, so each amendment announces itself once and a
            # re-run of this job announces nothing.
            if not await notif.claim(
                session,
                org_id=decision.org_id,
                notification_type=NotificationType.TENDER_UPDATED,
                subject_key=f"{tender.id}:v{tender.version}",
                channel="inapp",
            ):
                continue
            await notif.notify(
                session,
                org_id=decision.org_id,
                notification_type=NotificationType.TENDER_UPDATED,
                title=f"Updated by the portal: {tender.title}",
                body=(
                    "You are bidding on this tender and the notice changed. "
                    "Check the dates and scope."
                ),
                link=f"/app/tenders/{tender.id}",
                tender_id=tender.id,
                data={"version": tender.version},
            )
            result["notified"] += 1

    logger.info("tender_update_notified", **result)
    return result


# --- the daily digest ----------------------------------------------------


@tracked_job
async def digest_dispatcher(ctx: dict[str, Any]) -> dict[str, Any]:
    """Queue a digest for every organization whose local send time has passed.

    Runs every fifteen minutes and decides per organization in *their* timezone.
    ``last_digest_sent_for`` holds the local date already covered, which is what
    stops four wake-ups an hour from sending four digests.
    """
    now = utcnow()
    queued: list[str] = []

    async with session_scope() as session:
        rows = await session.execute(
            select(Organization, NotificationSettings)
            .join(NotificationSettings, NotificationSettings.org_id == Organization.id)
            .where(
                Organization.is_active.is_(True),
                NotificationSettings.digest_enabled.is_(True),
            )
        )
        for org, preferences in rows.all():
            if _digest_is_due(preferences, now):
                queued.append(str(org.id))

    for org_id in queued:
        await _enqueue_digest(org_id)

    logger.info("digest_dispatch", queued=len(queued))
    return {"queued": len(queued)}


def _digest_is_due(preferences: NotificationSettings, now: datetime) -> bool:
    """Whether this organization's send time has passed today, unsent."""
    try:
        today = local_date(now, preferences.digest_timezone)
        local_now = to_timezone(now, preferences.digest_timezone)
    except Exception:  # pragma: no cover - a bad timezone must not stall others
        logger.warning("digest_timezone_invalid", timezone=preferences.digest_timezone)
        return False

    if preferences.last_digest_sent_for == today:
        return False
    return local_now.time() >= preferences.digest_time


async def _enqueue_digest(org_id: str) -> None:
    from app.jobs.queue import get_queue

    try:
        queue = await get_queue()
        await queue.enqueue_job("send_daily_digest", org_id, _job_id=f"digest:{org_id}")
    except Exception as exc:  # pragma: no cover - Redis down must not lose the day
        logger.warning("digest_enqueue_failed", org_id=org_id, error=str(exc))


@tracked_job
async def send_daily_digest(ctx: dict[str, Any], org_id: str) -> dict[str, Any]:
    """Build and queue one organization's shortlist.

    ``last_digest_sent_for`` is stamped even when there is nothing to send, so
    a quiet day is not retried every fifteen minutes until midnight.
    """
    result: dict[str, Any] = {"org_id": org_id, "matches": 0, "queued": 0}

    async with session_scope() as session:
        org = await session.get(Organization, UUID(org_id))
        if org is None:
            return result | {"error": "org_not_found"}
        preferences = await notif.settings_for(session, org)
        today = local_date(utcnow(), preferences.digest_timezone)
        if preferences.last_digest_sent_for == today:
            return result | {"skipped_reason": "already_sent_today"}

        since = _digest_window_start(preferences, today)
        digest = await _build_digest(session, org=org, preferences=preferences, since=since)
        result["matches"] = digest["total_count"]

        preferences.last_digest_sent_for = today
        await session.flush()

        if not digest["total_count"] and not digest["upcoming_deadlines"]:
            # An empty digest every morning is how a daily email becomes a rule
            # in someone's mail client. Silence says the same thing.
            return result | {"skipped_reason": "nothing_to_report"}

        if preferences.inapp_enabled and digest["total_count"]:
            await notif.notify(
                session,
                org_id=org.id,
                notification_type=NotificationType.DAILY_DIGEST,
                title=f"{digest['total_count']} new match"
                + ("es" if digest["total_count"] != 1 else "")
                + " today",
                body="Open today's shortlist to see what came in.",
                link="/app/today",
                data={"count": digest["total_count"]},
            )

        delivery = await notif.send_to_recipients(
            session,
            org=org,
            notification_type=NotificationType.DAILY_DIGEST,
            template_key="daily_digest",
            subject_key=today.isoformat(),
            context=digest,
        )
        result["queued"] = delivery.queued
        if delivery.skipped_reason:
            result["skipped_reason"] = delivery.skipped_reason

    logger.info("digest_sent", **result)
    return result


def _digest_window_start(preferences: NotificationSettings, today: date) -> datetime:
    """Matches "since the last digest", or the last day if there was none."""
    previous = preferences.last_digest_sent_for or (today - timedelta(days=1))
    return datetime.combine(previous, preferences.digest_time).replace(
        tzinfo=to_timezone(utcnow(), preferences.digest_timezone).tzinfo
    )


async def _build_digest(
    session: AsyncSession,
    *,
    org: Organization,
    preferences: NotificationSettings,
    since: datetime,
) -> dict[str, Any]:
    """Assemble the digest context: picks, questions, and bids in flight."""
    rows = await session.execute(
        select(TenderMatch, Tender)
        .join(Tender, Tender.id == TenderMatch.tender_id)
        .where(
            TenderMatch.org_id == org.id,
            TenderMatch.first_matched_at.is_not(None),
            TenderMatch.first_matched_at >= since,
            Tender.status == TenderStatus.OPEN,
        )
        .order_by(TenderMatch.similarity.desc())
    )
    scored = [
        (match, tender)
        for match, tender in rows.all()
        if notif.grade_at_least(match.grade.value, preferences.digest_min_grade)
        and match.eligibility_status is not EligibilityStatus.INELIGIBLE
    ]

    picks = [
        {
            "grade": match.grade.value,
            "eligibility_label": ELIGIBILITY_LABELS[match.eligibility_status],
            "title": tender.title,
            "summary": (match.explanation or {}).get("summary")
            or (tender.summary or "")[:200]
            or "No summary available.",
            "procuring_entity": tender.procuring_entity,
            "deadline_label": deadline_label(tender.deadline_at, preferences.digest_timezone),
            "url": tender_url(tender.id),
        }
        for match, tender in scored[:DIGEST_PICKS]
    ]

    verify = [
        {
            "title": tender.title,
            "reason": _first_blocker(match),
            "url": tender_url(tender.id),
        }
        for match, tender in scored
        if match.eligibility_status is EligibilityStatus.NEEDS_VERIFICATION
    ][:DIGEST_VERIFY_ITEMS]

    upcoming = await _upcoming_bids(session, org=org, preferences=preferences)

    return {
        "digest_date": local_date(utcnow(), preferences.digest_timezone).strftime("%-d %b %Y"),
        "total_count": len(scored),
        "top_count": len(picks),
        "other_count": max(len(scored) - len(picks), 0),
        "picks": picks,
        "needs_verification": verify,
        "upcoming_deadlines": upcoming,
        "setup_nudge": _setup_nudge(len(scored)),
    }


def _setup_nudge(match_count: int) -> str | None:
    """Said once, in the place someone will read it, rather than nowhere."""
    if match_count:
        return None
    return (
        "No matches cleared your grade threshold today. If that keeps happening, "
        "your capability profile may be too narrow — or your bidding criteria too strict."
    )


async def _upcoming_bids(
    session: AsyncSession, *, org: Organization, preferences: NotificationSettings
) -> list[dict[str, Any]]:
    now = utcnow()
    horizon = now + timedelta(days=UPCOMING_WINDOW_DAYS)
    rows = await session.execute(
        select(Tender)
        .join(TenderDecision, TenderDecision.tender_id == Tender.id)
        .where(
            TenderDecision.org_id == org.id,
            TenderDecision.is_current.is_(True),
            TenderDecision.decision == Decision.BID,
            Tender.deadline_at.is_not(None),
            Tender.deadline_at > now,
            Tender.deadline_at <= horizon,
        )
        .order_by(Tender.deadline_at)
        .limit(DIGEST_UPCOMING_ITEMS)
    )
    return [
        {
            "title": tender.title,
            "deadline_label": deadline_label(tender.deadline_at, preferences.digest_timezone),
            "url": tender_url(tender.id),
        }
        for tender in rows.scalars().all()
    ]


# --- deadline reminders --------------------------------------------------


@tracked_job
async def deadline_reminder_sweep(ctx: dict[str, Any]) -> dict[str, Any]:
    """Remind organizations about bids closing at their configured offsets.

    Only tenders with a current *bid* decision: a reminder about something
    nobody committed to is an interruption, and the offsets exist so that a
    company chooses how far ahead it wants to be nudged.
    """
    now = utcnow()
    result: dict[str, Any] = {"reminders": 0, "queued": 0}

    async with session_scope() as session:
        rows = await session.execute(
            select(TenderDecision, Tender, Organization, NotificationSettings)
            .join(Tender, Tender.id == TenderDecision.tender_id)
            .join(Organization, Organization.id == TenderDecision.org_id)
            .join(NotificationSettings, NotificationSettings.org_id == TenderDecision.org_id)
            .where(
                TenderDecision.is_current.is_(True),
                TenderDecision.decision == Decision.BID,
                NotificationSettings.reminders_enabled.is_(True),
                Tender.deadline_at.is_not(None),
                Tender.deadline_at > now,
                Tender.status == TenderStatus.OPEN,
            )
        )

        for _decision, tender, org, preferences in rows.all():
            assert tender.deadline_at is not None
            days_left = days_between(now, tender.deadline_at)
            offsets = [int(offset) for offset in (preferences.reminder_offsets or [])]
            if days_left not in offsets:
                continue

            source = await session.get(TenderSource, tender.source_id)
            if preferences.inapp_enabled and await notif.claim(
                session,
                org_id=org.id,
                notification_type=NotificationType.DEADLINE_REMINDER,
                subject_key=f"{tender.id}:{days_left}:inapp",
                channel="inapp",
            ):
                await notif.notify(
                    session,
                    org_id=org.id,
                    notification_type=NotificationType.DEADLINE_REMINDER,
                    title=f"{days_left} day{'s' if days_left != 1 else ''} left: {tender.title}",
                    body="You marked this one as a bid.",
                    link=f"/app/tenders/{tender.id}",
                    tender_id=tender.id,
                    data={"days_left": days_left},
                )

            delivery = await notif.send_to_recipients(
                session,
                org=org,
                notification_type=NotificationType.DEADLINE_REMINDER,
                template_key="deadline_reminder",
                # The offset is part of the key: the seven-day and two-day
                # nudges are different messages about the same tender.
                subject_key=f"{tender.id}:{days_left}",
                context={
                    "tender_title": tender.title,
                    "tender_url": tender_url(tender.id),
                    "days_left": days_left,
                    "deadline_label": deadline_label(tender.deadline_at, org.timezone),
                    "procuring_entity": tender.procuring_entity,
                    "source_name": source.name if source else "a portal",
                },
            )
            result["reminders"] += 1
            result["queued"] += delivery.queued

    logger.info("deadline_reminders_swept", **result)
    return result


# --- operator alerts -----------------------------------------------------


@tracked_job
async def alert_sources_down(ctx: dict[str, Any]) -> dict[str, Any]:
    """Mail platform staff about portals that have stopped answering.

    Staff rather than customers: a customer cannot fix a scraper, and telling
    them their feed is incomplete without telling them when it will be fixed
    only costs their confidence.
    """
    from app.modules.tenders.models import SourceHealth
    from app.modules.users.models import User

    result: dict[str, Any] = {"sources": 0, "queued": 0}

    async with session_scope() as session:
        down = list(
            (
                await session.scalars(
                    select(TenderSource).where(
                        TenderSource.enabled.is_(True),
                        TenderSource.health == SourceHealth.DOWN,
                    )
                )
            ).all()
        )
        if not down:
            return result

        staff = list(
            (
                await session.scalars(
                    select(User).where(User.is_superuser.is_(True), User.is_active.is_(True))
                )
            ).all()
        )
        if not staff:
            return result | {"skipped_reason": "no_staff_accounts"}

        from app.modules.notifications.email import outbox

        for source in down:
            result["sources"] += 1
            for member in staff:
                # Keyed by the failure streak, so a portal that stays down
                # nags once per further failure rather than once per sweep.
                stored = await outbox.enqueue(
                    session,
                    template_key="source_down",
                    to_email=member.email,
                    to_name=member.full_name,
                    dedupe_key=(
                        f"source_down:{source.id}:{source.consecutive_failures}:{member.id}"
                    ),
                    context={
                        "source_name": source.name,
                        "consecutive_failures": source.consecutive_failures,
                        "last_success_label": (
                            source.last_success_at.strftime("%-d %b %Y, %H:%M UTC")
                            if source.last_success_at
                            else "never"
                        ),
                        "last_error": await _last_error(session, source.id),
                    },
                )
                if stored is not None:
                    result["queued"] += 1

    logger.info("source_down_alerts", **result)
    return result


async def _last_error(session: AsyncSession, source_id: UUID) -> str | None:
    from app.jobs.runs import ScraperRun

    run = await session.scalar(
        select(ScraperRun)
        .where(ScraperRun.source_id == source_id, ScraperRun.error.is_not(None))
        .order_by(ScraperRun.started_at.desc())
        .limit(1)
    )
    return run.error if run else None


__all__ = [
    "alert_sources_down",
    "deadline_reminder_sweep",
    "digest_dispatcher",
    "notify_instant",
    "notify_tender_updated",
    "send_daily_digest",
]
