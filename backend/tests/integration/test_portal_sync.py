"""Starting a portal sync by hand, as an ordinary member.

The endpoint exists because a deployment whose pool has never been filled shows
a new organization nothing at all, and the person looking at that empty screen
is not usually platform staff. So these tests pin two things that are easy to
lose later: that a plain member may press it, and that pressing it repeatedly
costs the portals nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import session_scope
from app.ingestion.portals import DEFAULT_PORTALS, ensure_default_sources
from app.jobs.queue import get_queue
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.tenders.models import TenderSource
from app.modules.users.models import User


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def member_headers() -> AsyncIterator[dict[str, str]]:
    """A verified user with no staff rights at all — the point of the endpoint."""
    email = f"member-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Ordinary Member",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
        )
        session.add(user)
        await session.flush()
        assert user.is_superuser is False
        issued = await issue_session(session, user=user)
        token = issued.response.access_token

    yield {"Authorization": f"Bearer {token}"}

    async with session_scope() as session:
        found = await session.scalar(select(User).where(User.email == email))
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        if found is not None:
            await session.delete(found)


@pytest.fixture(autouse=True)
async def sources() -> AsyncIterator[None]:
    """The shipped portals, however this database came to exist."""
    async with session_scope() as session:
        await ensure_default_sources(session)
    yield


@pytest.fixture(autouse=True)
async def drain_queued_scrapes() -> AsyncIterator[None]:
    """Clear the scrape queue around each test, in both directions.

    Before, because a scrape is deduplicated on a job id derived from the
    source, and a developer running the stack has a worker that will have left
    one behind — the endpoint would then correctly queue nothing, and the test
    would read that as a broken endpoint. After, so these tests do not leave
    real portal visits sitting on a real queue.
    """
    await _clear_scrape_jobs()
    yield
    await _clear_scrape_jobs()


async def _clear_scrape_jobs() -> None:
    redis = await get_queue()
    keys = [key async for key in redis.scan_iter("arq:*scrape:*")]
    if keys:
        await redis.delete(*keys)
    await redis.delete("arq:queue:scrape")


class TestAccess:
    async def test_a_signed_out_visitor_cannot_start_one(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/sources/sync")

        assert response.status_code == 401

    async def test_an_ordinary_member_can_start_one(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        response = await api.post("/api/v1/sources/sync", headers=member_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert sorted(body["queued"]) == sorted(spec["code"] for spec in DEFAULT_PORTALS)
        assert body["running"] is True


class TestCooldown:
    async def test_a_second_press_is_answered_with_the_wait(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        """Refusing is not failing. The button reports a countdown, not an error,
        because "wait nine minutes" is a real answer to "again, now"."""
        first = await api.post("/api/v1/sources/sync", headers=member_headers)
        assert first.status_code == 200, first.text

        second = await api.post("/api/v1/sources/sync", headers=member_headers)

        assert second.status_code == 200, second.text
        body = second.json()
        assert body["queued"] == []
        assert 0 < body["retry_after_seconds"] <= settings.source_sync_cooldown_seconds

    async def test_the_cooldown_is_deployment_wide(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        """The pool these presses fill is shared, so the limit cannot be per user:
        ten organizations must not mean ten times the traffic to one old portal."""
        await api.post("/api/v1/sources/sync", headers=member_headers)

        other = f"other-{uuid4().hex[:12]}@tsense-test.io"
        async with session_scope() as session:
            user = User(
                email=other,
                full_name="Somebody Else",
                password_hash=hash_password("a-perfectly-fine-password"),
                email_verified_at=utcnow(),
            )
            session.add(user)
            await session.flush()
            token = (await issue_session(session, user=user)).response.access_token

        response = await api.post(
            "/api/v1/sources/sync", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.json()["queued"] == []
        assert response.json()["retry_after_seconds"] > 0

        async with session_scope() as session:
            found = await session.scalar(select(User).where(User.email == other))
            await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == other))
            if found is not None:
                await session.delete(found)


class TestState:
    async def test_polling_reports_the_portals_without_starting_anything(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        response = await api.get("/api/v1/sources/sync", headers=member_headers)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["retry_after_seconds"] == 0
        assert body["queued"] == []
        assert sorted(portal["code"] for portal in body["portals"]) == sorted(
            spec["code"] for spec in DEFAULT_PORTALS
        )

    async def test_the_hand_entry_bucket_is_not_offered_as_a_portal(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        """`manual` is where hand-added notices live. Offering to scrape it would
        be offering to fetch nothing from nowhere."""
        response = await api.get("/api/v1/sources/sync", headers=member_headers)

        assert "manual" not in [portal["code"] for portal in response.json()["portals"]]


class TestRegistry:
    async def test_registering_the_shipped_portals_twice_changes_nothing(self) -> None:
        """The migration runs on every deploy; a second pass must not duplicate a
        portal or revert configuration an operator has since retuned."""
        async with session_scope() as session:
            before = (await session.scalars(select(TenderSource.code))).all()
            created = await ensure_default_sources(session)
            after = (await session.scalars(select(TenderSource.code))).all()

        assert created == []
        assert sorted(after) == sorted(before)


class TestScopedAnalysis:
    """A hand-pressed sync grades for the organization that pressed it.

    The bargain: the notices land in the shared pool for everyone, but only
    the presser is re-scored, so one button cannot make a portal's worth of
    notices re-score the whole deployment. The other half of that bargain is
    the six-hourly sweep below — without it, a scoped pass would hide those
    notices from every other tenant permanently, because on the next scheduled
    pass they are neither new nor amended.
    """

    async def test_the_fan_out_narrows_to_the_organization_that_asked(self) -> None:
        """`orgs_with_profiles` is what decides who a notice gets scored for."""
        from app.modules.matching.service import orgs_with_profiles

        async with session_scope() as session:
            everyone = await orgs_with_profiles(session)
            assert everyone, "the fixture pool should leave at least one tenant"
            target = str(everyone[0][0].id)

            scoped = await orgs_with_profiles(session, only_org_id=target)

        assert [str(org.id) for org, _ in scoped] == [target]

    async def test_a_scoped_run_and_a_full_one_do_not_cancel_each_other(self) -> None:
        """Both are deduplicated per tender. Sharing one job id would let
        whichever arrived first drop the other — and the sweep being dropped is
        the expensive direction, because the notice never reaches anyone else.
        """
        from app.jobs.tasks.matching import enqueue_processing

        # A synthetic id: this pins the job-id convention, and a real tender
        # would put the result at the mercy of whatever a live worker has
        # already queued.
        tender_id = str(uuid4())
        redis = await get_queue()
        try:
            assert await enqueue_processing(tender_id) is not None
            assert await enqueue_processing(tender_id, only_org_id="org-abc") is not None
            # A repeat of either is still deduplicated.
            assert await enqueue_processing(tender_id) is None
            assert await enqueue_processing(tender_id, only_org_id="org-abc") is None
        finally:
            keys = [key async for key in redis.scan_iter(f"arq:job:process:{tender_id}*")]
            if keys:
                await redis.delete(*keys)

    async def test_the_scheduled_pass_is_not_scoped(self) -> None:
        """The cron dispatch must stay tenant-wide: it is what grades a notice
        for everyone who did not press anything."""
        from app.jobs.tasks.scraping import scrape_all_sources

        result = await scrape_all_sources({})

        assert result["queued"] >= 1
        assert result.get("scoped_to_org") is None


class TestSweep:
    async def test_it_finds_a_notice_no_tenant_wide_pass_has_reached(self) -> None:
        """`analysed_at` is null exactly when a scoped pass stored a notice and
        nothing has matched it for the other tenants yet."""
        from app.jobs.tasks.matching import sweep_unanalysed_tenders
        from app.modules.tenders.models import Tender

        async with session_scope() as session:
            tender = await session.scalar(select(Tender).limit(1))
            assert tender is not None, "the pool fixture should have left one"
            tender.analysed_at = None
            tender_id = tender.id

        result = await sweep_unanalysed_tenders({})

        assert result["found"] >= 1
        async with session_scope() as session:
            # Still null: the sweep queues the work, the pass does the marking.
            fresh = await session.get(Tender, tender_id)
            assert fresh is not None and fresh.analysed_at is None

    async def test_it_leaves_an_already_analysed_notice_alone(self) -> None:
        from app.jobs.tasks.matching import sweep_unanalysed_tenders
        from app.modules.tenders.models import Tender

        async with session_scope() as session:
            await session.execute(Tender.__table__.update().values(analysed_at=utcnow()))

        result = await sweep_unanalysed_tenders({})

        assert result["found"] == 0


class TestWelcomeSync:
    """One pull, the first time a profile is worth matching against.

    The courtesy exists because finishing a profile is the moment somebody
    expects the product to do something, and what they see otherwise is
    whatever the last scheduled pass left. What these pin is the "once" — a
    portal that has been running since 2011 must not be asked again on every
    edit — and that a refused pull does not burn the single chance.
    """

    async def _profile(self, completeness: int):
        from app.modules.orgs.models import Organization
        from app.modules.profiles.models import CompanyProfile

        async with session_scope() as session:
            org = Organization(name=f"welcome-{uuid4().hex[:8]}", slug=uuid4().hex[:12])
            session.add(org)
            await session.flush()
            profile = CompanyProfile(org_id=org.id, completeness=completeness)
            session.add(profile)
            await session.flush()
            return profile.id

    async def test_crossing_the_threshold_pulls_the_portals_once(self) -> None:
        from app.modules.profiles.models import CompanyProfile
        from app.modules.profiles.service import maybe_welcome_sync

        profile_id = await self._profile(completeness=60)

        async with session_scope() as session:
            profile = await session.get(CompanyProfile, profile_id)
            assert profile is not None
            first = await maybe_welcome_sync(session, profile)
            assert first is not None, "a qualifying profile should pull once"
            assert profile.welcome_sync_at is not None

        # A second save must not ask the portals again.
        async with session_scope() as session:
            profile = await session.get(CompanyProfile, profile_id)
            assert profile is not None
            assert await maybe_welcome_sync(session, profile) is None

    async def test_a_thin_profile_is_left_alone(self) -> None:
        from app.modules.profiles.models import CompanyProfile
        from app.modules.profiles.service import maybe_welcome_sync

        profile_id = await self._profile(completeness=30)

        async with session_scope() as session:
            profile = await session.get(CompanyProfile, profile_id)
            assert profile is not None

            assert await maybe_welcome_sync(session, profile) is None
            # No stamp: it has not had its turn yet, so crossing later still works.
            assert profile.welcome_sync_at is None

    async def test_a_pull_refused_by_the_cooldown_does_not_spend_the_chance(
        self, api: AsyncClient, member_headers: dict[str, str]
    ) -> None:
        """The cooldown is deployment-wide, so a courtesy can collide with
        somebody else's sync. Stamping then would cost this organization its
        one pull for a pass that never ran."""
        from app.modules.profiles.models import CompanyProfile
        from app.modules.profiles.service import maybe_welcome_sync

        # Someone else presses first, claiming the deployment-wide cooldown.
        pressed = await api.post("/api/v1/sources/sync", headers=member_headers)
        assert pressed.status_code == 200, pressed.text

        profile_id = await self._profile(completeness=80)
        async with session_scope() as session:
            profile = await session.get(CompanyProfile, profile_id)
            assert profile is not None

            assert await maybe_welcome_sync(session, profile) is None
            assert profile.welcome_sync_at is None
