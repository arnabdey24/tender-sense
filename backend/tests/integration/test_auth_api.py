"""Authentication flows end to end over HTTP against the real database.

These are the tests that matter most in M1: they cover the paths an attacker
probes (enumeration, token replay, privilege carry-over) rather than only the
happy path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.time import utcnow
from app.db.session import session_scope
from app.modules.auth.models import AuthToken, RefreshSession, TokenPurpose
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.users.models import User

PASSWORD = "a-perfectly-fine-password"


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid4().hex[:12]}@tsense-test.io"


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    """A client that keeps cookies, so the refresh cookie behaves as in a browser."""
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def _cleanup(email: str) -> None:
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.email == email))
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        if user is not None:
            await session.delete(user)


async def register_user(api: AsyncClient, email: str, name: str = "Test User") -> dict[str, Any]:
    response = await api.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def latest_token(email: str, purpose: TokenPurpose) -> str | None:
    """Read the raw token out of the queued email, as a user would from their inbox."""
    async with session_scope() as session:
        template = "verify_email" if purpose is TokenPurpose.VERIFY_EMAIL else "reset_password"
        row = await session.scalar(
            select(EmailOutbox)
            .where(EmailOutbox.to_email == email, EmailOutbox.template_key == template)
            .order_by(EmailOutbox.created_at.desc())
        )
        if row is None:
            return None
        url_key = "verify_url" if purpose is TokenPurpose.VERIFY_EMAIL else "reset_url"
        return str(row.context[url_key]).split("token=")[1]


async def verify_and_login(api: AsyncClient, email: str) -> dict[str, Any]:
    token = await latest_token(email, TokenPurpose.VERIFY_EMAIL)
    assert token is not None
    response = await api.post("/api/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 200, response.text
    return response.json()


class TestRegistration:
    async def test_registration_creates_an_unverified_user_and_queues_an_email(
        self, api: AsyncClient
    ) -> None:
        email = unique_email()
        try:
            body = await register_user(api, email, name="Rahim Uddin")

            assert body["user"]["email"] == email
            assert body["user"]["email_verified"] is False
            assert await latest_token(email, TokenPurpose.VERIFY_EMAIL) is not None
        finally:
            await _cleanup(email)

    async def test_registering_twice_looks_identical_and_creates_one_account(
        self, api: AsyncClient
    ) -> None:
        """Otherwise the endpoint reveals which addresses are registered."""
        email = unique_email()
        try:
            first = await register_user(api, email)
            second = await register_user(api, email)

            assert first["user"]["id"] == second["user"]["id"]
            async with session_scope() as session:
                count = len((await session.execute(select(User).where(User.email == email))).all())
            assert count == 1
        finally:
            await _cleanup(email)

    async def test_registering_again_does_not_change_the_password(self, api: AsyncClient) -> None:
        """A second registration must not become a password reset."""
        email = unique_email()
        try:
            await register_user(api, email)
            await api.post(
                "/api/v1/auth/register",
                json={"email": email, "password": "an-attackers-password", "full_name": "X"},
            )

            response = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )

            assert response.status_code == 200
        finally:
            await _cleanup(email)

    async def test_email_is_case_insensitive(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            await verify_and_login(api, email)

            response = await api.post(
                "/api/v1/auth/login", json={"email": email.upper(), "password": PASSWORD}
            )

            assert response.status_code == 200
        finally:
            await _cleanup(email)


class TestLogin:
    async def test_login_returns_a_session_and_sets_the_refresh_cookie(
        self, api: AsyncClient
    ) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            await verify_and_login(api, email)
            api.cookies.clear()

            response = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )

            body = response.json()
            assert response.status_code == 200
            assert body["access_token"]
            assert body["memberships"] == []
            assert body["active_org_id"] is None
            assert settings.refresh_cookie_name in response.cookies
        finally:
            await _cleanup(email)

    async def test_the_refresh_cookie_is_http_only_and_scoped_to_auth(
        self, api: AsyncClient
    ) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            await verify_and_login(api, email)
            api.cookies.clear()

            response = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )

            cookie_header = response.headers["set-cookie"]
            assert "HttpOnly" in cookie_header
            assert "Path=/api/v1/auth" in cookie_header
            assert "SameSite=lax" in cookie_header.replace("Samesite", "SameSite")
        finally:
            await _cleanup(email)

    async def test_wrong_password_and_unknown_address_fail_alike(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)

            wrong = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": "not-the-password"}
            )
            unknown = await api.post(
                "/api/v1/auth/login",
                json={"email": unique_email("ghost"), "password": PASSWORD},
            )

            assert wrong.status_code == unknown.status_code == 401
            assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"]
            assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
        finally:
            await _cleanup(email)

    async def test_login_is_allowed_before_verification(self, api: AsyncClient) -> None:
        """The SPA needs a session to show the 'resend verification' screen."""
        email = unique_email()
        try:
            await register_user(api, email)

            response = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )

            assert response.status_code == 200
            assert response.json()["user"]["email_verified"] is False
        finally:
            await _cleanup(email)


class TestEmailVerification:
    async def test_verifying_marks_the_user_and_signs_them_in(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)

            body = await verify_and_login(api, email)

            assert body["user"]["email_verified"] is True
            assert body["access_token"]
        finally:
            await _cleanup(email)

    async def test_a_verification_token_cannot_be_used_twice(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            token = await latest_token(email, TokenPurpose.VERIFY_EMAIL)
            assert token is not None
            await api.post("/api/v1/auth/verify-email", json={"token": token})

            replay = await api.post("/api/v1/auth/verify-email", json={"token": token})

            assert replay.status_code == 422
            assert replay.json()["error"]["code"] == "token_expired"
        finally:
            await _cleanup(email)

    async def test_an_unknown_token_is_rejected(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/auth/verify-email", json={"token": "made-up"})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_token"

    async def test_resending_invalidates_the_previous_link(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            first = await latest_token(email, TokenPurpose.VERIFY_EMAIL)
            await api.post("/api/v1/auth/resend-verification", json={"email": email})
            second = await latest_token(email, TokenPurpose.VERIFY_EMAIL)

            assert first != second
            stale = await api.post("/api/v1/auth/verify-email", json={"token": first})
            assert stale.status_code == 422
        finally:
            await _cleanup(email)

    async def test_resending_to_an_unknown_address_says_nothing(self, api: AsyncClient) -> None:
        response = await api.post(
            "/api/v1/auth/resend-verification", json={"email": unique_email("ghost")}
        )

        assert response.status_code == 200
        assert "If that address has an account" in response.json()["message"]


class TestRefreshRotation:
    async def test_refresh_issues_a_new_token_pair(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            first = await verify_and_login(api, email)
            original_cookie = api.cookies.get(settings.refresh_cookie_name)

            response = await api.post("/api/v1/auth/refresh")

            assert response.status_code == 200
            assert response.json()["access_token"] != first["access_token"]
            assert api.cookies.get(settings.refresh_cookie_name) != original_cookie
        finally:
            await _cleanup(email)

    async def test_reusing_a_rotated_token_revokes_the_whole_family(self, api: AsyncClient) -> None:
        """The signature of a stolen refresh token: the old value comes back."""
        email = unique_email()
        try:
            await register_user(api, email)
            await verify_and_login(api, email)
            stolen = api.cookies.get(settings.refresh_cookie_name)
            assert stolen is not None

            await api.post("/api/v1/auth/refresh")  # legitimate rotation
            current = api.cookies.get(settings.refresh_cookie_name)

            replay = await api.post(
                "/api/v1/auth/refresh", cookies={settings.refresh_cookie_name: stolen}
            )
            assert replay.status_code == 401
            assert replay.json()["error"]["code"] == "refresh_token_reused"

            # The legitimate token is revoked too, forcing a fresh sign-in.
            after = await api.post(
                "/api/v1/auth/refresh", cookies={settings.refresh_cookie_name: current}
            )
            assert after.status_code == 401
        finally:
            await _cleanup(email)

    async def test_refresh_without_a_cookie_is_rejected(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/auth/refresh")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "missing_refresh_token"

    async def test_logout_revokes_only_this_session(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            await verify_and_login(api, email)

            await api.post("/api/v1/auth/logout")
            response = await api.post("/api/v1/auth/refresh")

            assert response.status_code == 401
        finally:
            await _cleanup(email)

    async def test_logout_all_revokes_every_session(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            session_body = await verify_and_login(api, email)
            token = session_body["access_token"]

            response = await api.post(
                "/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == 200

            async with session_scope() as db:
                user = await db.scalar(select(User).where(User.email == email))
                assert user is not None
                live = await db.execute(
                    select(RefreshSession).where(
                        RefreshSession.user_id == user.id,
                        RefreshSession.revoked_at.is_(None),
                    )
                )
                assert live.all() == []
        finally:
            await _cleanup(email)


class TestPasswordReset:
    async def test_reset_changes_the_password_and_kills_other_sessions(
        self, api: AsyncClient
    ) -> None:
        email = unique_email()
        new_password = "an-entirely-different-password"
        try:
            await register_user(api, email)
            await verify_and_login(api, email)

            await api.post("/api/v1/auth/forgot-password", json={"email": email})
            token = await latest_token(email, TokenPurpose.RESET_PASSWORD)
            assert token is not None

            response = await api.post(
                "/api/v1/auth/reset-password", json={"token": token, "password": new_password}
            )
            assert response.status_code == 200

            old = await api.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            assert old.status_code == 401
            new = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": new_password}
            )
            assert new.status_code == 200
        finally:
            await _cleanup(email)

    async def test_a_reset_token_is_single_use(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            await api.post("/api/v1/auth/forgot-password", json={"email": email})
            token = await latest_token(email, TokenPurpose.RESET_PASSWORD)
            assert token is not None
            await api.post(
                "/api/v1/auth/reset-password", json={"token": token, "password": "first-password"}
            )

            replay = await api.post(
                "/api/v1/auth/reset-password", json={"token": token, "password": "second-password"}
            )

            assert replay.status_code == 422
        finally:
            await _cleanup(email)

    async def test_forgot_password_for_an_unknown_address_says_nothing(
        self, api: AsyncClient
    ) -> None:
        response = await api.post(
            "/api/v1/auth/forgot-password", json={"email": unique_email("ghost")}
        )

        assert response.status_code == 200
        assert "If that address has an account" in response.json()["message"]

    async def test_a_verification_token_cannot_reset_a_password(self, api: AsyncClient) -> None:
        """Tokens must not be interchangeable across purposes."""
        email = unique_email()
        try:
            await register_user(api, email)
            verify_token = await latest_token(email, TokenPurpose.VERIFY_EMAIL)
            assert verify_token is not None

            response = await api.post(
                "/api/v1/auth/reset-password",
                json={"token": verify_token, "password": "a-new-password-here"},
            )

            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_token"
        finally:
            await _cleanup(email)


class TestProtectedRoutes:
    async def test_me_requires_a_token(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/auth/me")

        assert response.status_code == 401

    async def test_me_returns_the_signed_in_user(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email, name="Fatima Khan")
            body = await verify_and_login(api, email)

            response = await api.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )

            assert response.status_code == 200
            assert response.json()["user"]["full_name"] == "Fatima Khan"
        finally:
            await _cleanup(email)

    async def test_a_garbage_token_is_rejected(self, api: AsyncClient) -> None:
        response = await api.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
        )

        assert response.status_code == 401

    async def test_org_scoped_routes_refuse_a_user_without_an_organization(
        self, api: AsyncClient
    ) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            body = await verify_and_login(api, email)

            response = await api.get(
                "/api/v1/orgs/current",
                headers={"Authorization": f"Bearer {body['access_token']}"},
            )

            assert response.status_code == 403
            assert response.json()["error"]["code"] == "no_active_org"
        finally:
            await _cleanup(email)


class TestTokenHygiene:
    async def test_no_raw_token_is_stored_in_the_database(self, api: AsyncClient) -> None:
        """A database leak must not yield usable links or sessions."""
        email = unique_email()
        try:
            await register_user(api, email)
            raw_verify = await latest_token(email, TokenPurpose.VERIFY_EMAIL)
            assert raw_verify is not None
            await api.post("/api/v1/auth/verify-email", json={"token": raw_verify})
            raw_refresh = api.cookies.get(settings.refresh_cookie_name)
            assert raw_refresh is not None

            async with session_scope() as session:
                user = await session.scalar(select(User).where(User.email == email))
                assert user is not None
                auth_tokens = (
                    await session.execute(select(AuthToken).where(AuthToken.user_id == user.id))
                ).scalars()
                sessions = (
                    await session.execute(
                        select(RefreshSession).where(RefreshSession.user_id == user.id)
                    )
                ).scalars()

                stored = [row.token_hash for row in auth_tokens] + [
                    row.token_hash for row in sessions
                ]

            assert stored
            assert raw_verify not in stored
            assert raw_refresh not in stored
            assert all(len(value) == 64 for value in stored)
        finally:
            await _cleanup(email)

    async def test_the_password_hash_is_never_returned(self, api: AsyncClient) -> None:
        """The response may say whether a password exists, never what it is."""
        email = unique_email()
        try:
            await register_user(api, email)
            body = await verify_and_login(api, email)

            async with session_scope() as session:
                user = await session.scalar(select(User).where(User.email == email))
                assert user is not None
                stored_hash = user.password_hash
            assert stored_hash is not None

            serialised = str(body)
            assert stored_hash not in serialised
            assert "$argon2" not in serialised
            assert PASSWORD not in serialised
            assert "password_hash" not in serialised
        finally:
            await _cleanup(email)


class TestRateLimiting:
    async def test_repeated_failed_logins_are_throttled(self, api: AsyncClient) -> None:
        """Password guessing must become expensive after a few attempts."""
        email = unique_email()
        try:
            await register_user(api, email)

            statuses = []
            for _ in range(12):
                response = await api.post(
                    "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
                )
                statuses.append(response.status_code)

            assert 429 in statuses, "login was never throttled"
            assert statuses.index(429) >= 5, "throttled far too aggressively"
        finally:
            await _cleanup(email)

    async def test_verification_resends_are_throttled(self, api: AsyncClient) -> None:
        """Otherwise this endpoint is a free mail cannon aimed at any address."""
        email = unique_email()
        try:
            await register_user(api, email)

            statuses = [
                (
                    await api.post("/api/v1/auth/resend-verification", json={"email": email})
                ).status_code
                for _ in range(6)
            ]

            assert 429 in statuses
        finally:
            await _cleanup(email)


class TestEmailVerificationGate:
    """Creating or joining an organization requires a proven address.

    Without this, a typo'd or someone else's address could end up receiving an
    organization's tender notifications.
    """

    async def test_an_unverified_user_cannot_create_an_organization(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            login = await api.post(
                "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
            )
            token = login.json()["access_token"]

            response = await api.post(
                "/api/v1/orgs",
                headers={"Authorization": f"Bearer {token}"},
                json={"name": "Premature Ltd."},
            )

            assert response.status_code == 403
            assert response.json()["error"]["code"] == "email_not_verified"
        finally:
            await _cleanup(email)

    async def test_a_verified_user_can_create_an_organization(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            body = await verify_and_login(api, email)

            response = await api.post(
                "/api/v1/orgs",
                headers={"Authorization": f"Bearer {body['access_token']}"},
                json={"name": f"Acme {uuid4().hex[:8]}"},
            )

            assert response.status_code == 201, response.text
        finally:
            await _cleanup(email)


class TestPasswordPresence:
    """The account page must know whether to ask for a current password.

    A Google-only account has none, and asking for one would make changing the
    password impossible.
    """

    async def test_a_password_account_reports_having_one(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            await register_user(api, email)
            body = await verify_and_login(api, email)

            assert body["user"]["has_password"] is True
        finally:
            await _cleanup(email)

    async def test_an_account_without_a_password_reports_that(self, api: AsyncClient) -> None:
        email = unique_email()
        try:
            async with session_scope() as session:
                session.add(
                    User(
                        email=email,
                        full_name="Google Only",
                        password_hash=None,
                        email_verified_at=utcnow(),
                    )
                )

            async with session_scope() as session:
                user = await session.scalar(select(User).where(User.email == email))
                assert user is not None
                issued = await issue_session(session, user=user)

            assert issued.response.user.has_password is False
        finally:
            await _cleanup(email)
