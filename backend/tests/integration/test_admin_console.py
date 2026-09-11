"""The platform operator console: overview, tenants, accounts and limits.

These are the routes that answer "is anything wrong" and "change it without a
deploy", so what they pin is mostly about who may call them and what a caller
cannot do to themselves.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import platform_settings
from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.users.models import User


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def _make_user(*, superuser: bool) -> tuple[str, str, dict[str, str]]:
    email = f"console-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Console Tester",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
            is_superuser=superuser,
        )
        session.add(user)
        await session.flush()
        user_id = str(user.id)
        token = (await issue_session(session, user=user)).response.access_token
    return email, user_id, {"Authorization": f"Bearer {token}"}


async def _drop(email: str) -> None:
    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        found = await session.scalar(select(User).where(User.email == email))
        if found is not None:
            await session.delete(found)


@pytest.fixture
async def staff() -> AsyncIterator[tuple[str, dict[str, str]]]:
    email, user_id, headers = await _make_user(superuser=True)
    yield user_id, headers
    await _drop(email)


@pytest.fixture(autouse=True)
async def restore_limits() -> AsyncIterator[None]:
    """Limits are deployment-wide and cached, so a test that moves one puts it
    back — otherwise the next test inherits a sign-in throttle it never set."""
    yield
    async with session_scope() as session:
        await platform_settings.reset_limits(session)
    platform_settings.invalidate()


class TestAccess:
    async def test_an_ordinary_member_reaches_none_of_it(self, api: AsyncClient) -> None:
        email, _, headers = await _make_user(superuser=False)
        try:
            for path in ("/api/v1/admin/overview", "/api/v1/admin/users", "/api/v1/admin/limits"):
                assert (await api.get(path, headers=headers)).status_code == 403, path
        finally:
            await _drop(email)


class TestOverview:
    async def test_it_answers_the_whole_front_page_in_one_request(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        _, headers = staff

        body = (await api.get("/api/v1/admin/overview", headers=headers)).json()

        assert body["users"] >= 1
        assert body["tenders"] >= 0
        assert isinstance(body["sources"], list)
        # The portals are registered by migration, so any deployment has them.
        assert {"egp_bd", "wb"} <= {source["code"] for source in body["sources"]}


class TestAccounts:
    async def test_staff_can_suspend_someone_else(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        _, headers = staff
        email, user_id, _ = await _make_user(superuser=False)
        try:
            response = await api.patch(
                f"/api/v1/admin/users/{user_id}",
                headers=headers,
                json={"is_active": False},
            )

            assert response.status_code == 200, response.text
            assert response.json()["is_active"] is False
        finally:
            await _drop(email)

    async def test_staff_cannot_lock_themselves_out(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        """The one mistake the console cannot undo: on a single-VM deployment
        the person who just revoked their own access may be the only operator."""
        user_id, headers = staff

        response = await api.patch(
            f"/api/v1/admin/users/{user_id}",
            headers=headers,
            json={"is_superuser": False},
        )

        assert response.status_code == 422
        assert (await api.get("/api/v1/admin/overview", headers=headers)).status_code == 200


class TestLimits:
    async def test_unset_limits_are_the_deployment_s_own(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        _, headers = staff

        body = (await api.get("/api/v1/admin/limits", headers=headers)).json()

        assert body["source_sync_cooldown_seconds"] == settings.source_sync_cooldown_seconds
        assert body["login_attempts_per_ip"] == settings.login_attempts_per_ip

    async def test_a_stored_limit_takes_effect_without_a_deploy(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        _, headers = staff
        current = (await api.get("/api/v1/admin/limits", headers=headers)).json()

        stored = await api.put(
            "/api/v1/admin/limits",
            headers=headers,
            json={**current, "source_sync_cooldown_seconds": 42},
        )

        assert stored.status_code == 200, stored.text
        assert stored.json()["source_sync_cooldown_seconds"] == 42
        # Read back through the same path the sync endpoint uses, not the cache.
        async with session_scope() as session:
            limits = await platform_settings.get_limits(session, fresh=True)
        assert limits.source_sync_cooldown_seconds == 42

    async def test_clearing_the_override_restores_the_configured_value(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        """Not "whatever it was before it was changed" — the deployment's own
        number, so removing an override is a return to a known state."""
        _, headers = staff
        current = (await api.get("/api/v1/admin/limits", headers=headers)).json()
        await api.put(
            "/api/v1/admin/limits",
            headers=headers,
            json={**current, "login_attempts_per_ip": 999},
        )

        restored = await api.delete("/api/v1/admin/limits", headers=headers)

        assert restored.json()["login_attempts_per_ip"] == settings.login_attempts_per_ip

    async def test_a_nonsense_limit_is_refused(
        self, api: AsyncClient, staff: tuple[str, dict[str, str]]
    ) -> None:
        _, headers = staff
        current = (await api.get("/api/v1/admin/limits", headers=headers)).json()

        response = await api.put(
            "/api/v1/admin/limits",
            headers=headers,
            json={**current, "login_attempts_per_ip": 0},
        )

        assert response.status_code == 422
