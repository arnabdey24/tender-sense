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
