"""The trends endpoint: whether today is normal.

What these pin is the part that is easy to get wrong and impossible to notice:
a chart drawn only from days that had arrivals closes the gap that is the whole
signal. A portal silent since Tuesday has to look different from one reporting
every day, and it only does if the quiet days are in the series.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import session_scope
from app.jobs.runs import JobRun, RunStatus
from app.modules.auth.service import issue_session
from app.modules.tenders.models import Tender, TenderSource
from app.modules.users.models import User


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def _auth(*, superuser: bool = True) -> tuple[str, dict[str, str]]:
    email = f"trends-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Trends Tester",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
            is_superuser=superuser,
        )
        session.add(user)
        await session.flush()
        token = (await issue_session(session, user=user)).response.access_token
    return email, {"Authorization": f"Bearer {token}"}


async def _drop_user(email: str) -> None:
    async with session_scope() as session:
        found = await session.scalar(select(User).where(User.email == email))
        if found is not None:
            await session.delete(found)


class TestAccess:
    @pytest.mark.anyio
    async def test_a_member_is_refused(self, api: AsyncClient) -> None:
        email, headers = await _auth(superuser=False)
        try:
            response = await api.get("/api/v1/admin/trends", headers=headers)
            assert response.status_code == 403
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_an_anonymous_caller_is_refused(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/admin/trends")).status_code == 401


class TestShape:
    @pytest.mark.anyio
    async def test_quiet_days_are_present_rather_than_omitted(self, api: AsyncClient) -> None:
        """The gap is the signal; a series that skips it cannot show it."""
        email, headers = await _auth()
        try:
            body = (await api.get("/api/v1/admin/trends?days=14", headers=headers)).json()
            assert len(body["intake"]) == 14
            assert len(body["jobs"]) == 14
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_the_window_is_contiguous_and_ends_today(self, api: AsyncClient) -> None:
        email, headers = await _auth()
        try:
            body = (await api.get("/api/v1/admin/trends?days=7", headers=headers)).json()
            days = [row["day"] for row in body["intake"]]
            assert days == sorted(days)
            assert len(set(days)) == 7
            assert days[-1] == utcnow().date().isoformat()
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_every_portal_appears_on_every_day(self, api: AsyncClient) -> None:
        """Including the ones that brought nothing, or a band vanishes."""
        email, headers = await _auth()
        try:
            body = (await api.get("/api/v1/admin/trends?days=5", headers=headers)).json()
            codes = set(body["sources"])
            assert codes
            for row in body["intake"]:
                assert set(row["by_source"]) == codes
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_disabled_sources_are_not_drawn(self, api: AsyncClient) -> None:
        """`manual` is a hand-entry bucket, not a portal that could go silent."""
        email, headers = await _auth()
        try:
            body = (await api.get("/api/v1/admin/trends", headers=headers)).json()
            assert "manual" not in body["sources"]
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_each_portal_is_named(self, api: AsyncClient) -> None:
        email, headers = await _auth()
        try:
            body = (await api.get("/api/v1/admin/trends", headers=headers)).json()
            for code in body["sources"]:
                assert body["source_names"].get(code)
        finally:
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_the_window_is_bounded(self, api: AsyncClient) -> None:
        email, headers = await _auth()
        try:
            assert (
                await api.get("/api/v1/admin/trends?days=500", headers=headers)
            ).status_code == 422
            assert (
                await api.get("/api/v1/admin/trends?days=0", headers=headers)
            ).status_code == 422
        finally:
            await _drop_user(email)


class TestCounts:
    @pytest.mark.anyio
    async def test_a_notice_lands_on_the_day_it_arrived(self, api: AsyncClient) -> None:
        email, headers = await _auth()
        marker = f"trend-{uuid4().hex[:10]}"
        async with session_scope() as session:
            source = await session.scalar(
                select(TenderSource).where(TenderSource.enabled.is_(True)).limit(1)
            )
            assert source is not None
            code = source.code
            session.add(
                Tender(
                    source_id=source.id,
                    external_id=marker,
                    canonical_url=f"https://example.test/{marker}",
                    title="A notice that arrived today",
                    content_hash=marker,
                )
            )
        try:
            body = (await api.get("/api/v1/admin/trends", headers=headers)).json()
            today = body["intake"][-1]
            assert today["day"] == utcnow().date().isoformat()
            assert today["by_source"][code] >= 1
        finally:
            async with session_scope() as session:
                await session.execute(delete(Tender).where(Tender.external_id == marker))
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_a_running_job_is_not_counted_as_an_outcome(self, api: AsyncClient) -> None:
        """A bar counting it would fall as the run finished."""
        email, headers = await _auth()
        name = f"trend-probe-{uuid4().hex[:8]}"
        async with session_scope() as session:
            session.add(
                JobRun(
                    name=name,
                    status=RunStatus.RUNNING,
                    started_at=utcnow(),
                )
            )
        try:
            body = (await api.get("/api/v1/admin/trends", headers=headers)).json()
            today = body["jobs"][-1]
            assert set(today) == {"day", "succeeded", "failed", "partial"}
        finally:
            async with session_scope() as session:
                await session.execute(delete(JobRun).where(JobRun.name == name))
            await _drop_user(email)

    @pytest.mark.anyio
    async def test_outcomes_are_counted_on_their_own_day(self, api: AsyncClient) -> None:
        email, headers = await _auth()
        name = f"trend-probe-{uuid4().hex[:8]}"
        async with session_scope() as session:
            for status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.FAILED):
                session.add(JobRun(name=name, status=status, started_at=utcnow()))
            session.add(
                JobRun(
                    name=name,
                    status=RunStatus.FAILED,
                    # Outside the window entirely.
                    started_at=utcnow() - timedelta(days=40),
                )
            )
        try:
            body = (await api.get("/api/v1/admin/trends?days=3", headers=headers)).json()
            today = body["jobs"][-1]
            assert today["succeeded"] >= 1
            assert today["failed"] >= 2
            assert sum(row["failed"] for row in body["jobs"]) < 1000
        finally:
            async with session_scope() as session:
                await session.execute(delete(JobRun).where(JobRun.name == name))
            await _drop_user(email)
