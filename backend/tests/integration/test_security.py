"""Invariants that must hold no matter what else changes.

Written as tests rather than as a document because a security review is only
true on the day it was written. The route-enumeration tests are the point: they
fail for the *next* unguarded endpoint, not just the ones that exist today.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.security import hash_password
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox, NotificationRecipient
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.users.models import User

#: Endpoints that are unauthenticated on purpose, with the reason they are.
PUBLIC_PATHS = {
    "/api/v1/health/live": "liveness probe",
    "/api/v1/health/ready": "readiness probe",
    "/api/v1/auth/register": "there is no account yet",
    "/api/v1/auth/login": "there is no session yet",
    "/api/v1/auth/refresh": "authenticated by the refresh cookie",
    "/api/v1/auth/logout": "clearing a cookie needs no proof",
    "/api/v1/auth/verify-email": "the emailed token is the credential",
    "/api/v1/auth/resend-verification": "the address is the only input",
    "/api/v1/auth/forgot-password": "the address is the only input",
    "/api/v1/auth/reset-password": "the emailed token is the credential",
    "/api/v1/auth/google/start": "starts the OAuth round trip",
    "/api/v1/auth/google/callback": "finishes the OAuth round trip",
    "/api/v1/invitations/{token}": "the invitee has no account yet",
    "/api/v1/notifications/verify-recipient": "the recipient may have no account",
    "/api/v1/notifications/unsubscribe": "an unsubscribe must never need a login",
}


@dataclass
class Tenant:
    org: Organization
    headers: dict[str, str]
    email: str


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def make_tenant(*, superuser: bool = False, name: str = "Meghna") -> Tenant:
    email = f"{name.lower()}-{uuid4().hex[:10]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name=f"{name} Person",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
            is_superuser=superuser,
        )
        org = Organization(name=name, slug=f"{name.lower()}-{uuid4().hex[:8]}")
        session.add_all([user, org])
        await session.flush()
        session.add(
            Membership(
                org_id=org.id,
                user_id=user.id,
                role=OrgRole.ADMIN,
                status=MembershipStatus.ACTIVE,
            )
        )
        await session.flush()
        issued = await issue_session(session, user=user, org_id=org.id)
        token = issued.response.access_token
        await session.refresh(org)
    return Tenant(org=org, headers={"Authorization": f"Bearer {token}"}, email=email)


async def drop_tenant(tenant: Tenant) -> None:
    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.org_id == tenant.org.id))
        await session.execute(delete(Organization).where(Organization.id == tenant.org.id))
        found = await session.scalar(select(User).where(User.email == tenant.email))
        if found is not None:
            await session.delete(found)


@pytest.fixture
async def tenant() -> AsyncIterator[Tenant]:
    created = await make_tenant()
    yield created
    await drop_tenant(created)


def all_routes() -> list[APIRoute]:
    from app.main import create_app

    return [route for route in create_app().routes if isinstance(route, APIRoute)]


class TestEveryEndpointIsGuarded:
    def test_no_endpoint_is_public_without_a_recorded_reason(self) -> None:
        """A new route that forgets its dependency fails here rather than in
        production. Adding a path to PUBLIC_PATHS is a deliberate act with a
        reason attached, which is the point."""
        unguarded: list[str] = []
        for route in all_routes():
            if route.path in PUBLIC_PATHS or not route.path.startswith(settings.api_v1_prefix):
                continue
            signature = str(route.dependant.call.__annotations__)
            if not any(
                marker in signature
                for marker in ("CurrentUser", "CurrentOrg", "Superuser", "VerifiedUser")
            ):
                unguarded.append(f"{list(route.methods)} {route.path}")

        assert unguarded == [], (
            "These endpoints take no authenticated dependency. Add one, or add "
            f"the path to PUBLIC_PATHS with the reason: {unguarded}"
        )

    def test_every_admin_route_requires_staff(self) -> None:
        """Organization admins are not platform staff. These routes act on the
        shared pool that every tenant reads from."""
        ungated = [
            f"{list(route.methods)} {route.path}"
            for route in all_routes()
            if "/admin/" in route.path or route.path.endswith("/admin")
            if "Superuser" not in str(route.dependant.call.__annotations__)
        ]

        assert ungated == []

    async def test_a_signed_in_customer_cannot_reach_the_admin_surface(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.get("/api/v1/admin/sources", headers=tenant.headers)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "staff_required"


class TestTenantIsolation:
    async def test_one_organization_cannot_read_anothers_scoped_data(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """Every org-scoped read takes org_id from the access token, never from
        the request — so holding another tenant's identifier buys nothing."""
        other = await make_tenant(name="Padma")
        try:
            async with session_scope() as session:
                session.add(
                    NotificationRecipient(
                        org_id=other.org.id,
                        email="theirs@tsense-test.io",
                        unsubscribe_token=uuid4().hex,
                    )
                )

            mine = await api.get("/api/v1/notification-recipients", headers=tenant.headers)

            assert mine.status_code == 200
            assert mine.json() == []
        finally:
            await drop_tenant(other)

    async def test_switching_to_an_organization_you_do_not_belong_to_is_refused(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """The access token carries the active organization, so this endpoint is
        the one place a tenant boundary could be crossed by asking."""
        other = await make_tenant(name="Padma")
        try:
            response = await api.post(
                "/api/v1/auth/switch-org",
                json={"org_id": str(other.org.id)},
                headers=tenant.headers,
            )

            assert response.status_code == 403
            assert response.json()["error"]["code"] == "not_a_member"
        finally:
            await drop_tenant(other)


class TestSecretsAtRest:
    async def test_no_recipient_verification_token_is_stored_in_the_clear(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """Consistent with invitations, resets and refresh tokens: a database
        dump must not contain a working link."""
        await api.post(
            "/api/v1/notification-recipients",
            json={"email": "bids@tsense-test.io"},
            headers=tenant.headers,
        )

        async with session_scope() as session:
            recipient = await session.scalar(
                select(NotificationRecipient).where(NotificationRecipient.org_id == tenant.org.id)
            )
        assert recipient is not None
        assert recipient.verify_token_hash is not None
        assert len(recipient.verify_token_hash) == 64  # sha256 hex

    def test_credentials_never_appear_in_a_settings_repr(self) -> None:
        """A crash traceback prints settings. It must not print the database
        password with them — nor the computed URLs that embed it.

        Built with distinctive values rather than the live ones, because the
        default password happens to equal the default username, and a substring
        search against that would pass for the wrong reason.
        """
        from app.core.config import Settings

        probe = Settings(
            secret_key="k" * 40,  # type: ignore[arg-type]
            postgres_password="hunter2-do-not-print",  # type: ignore[arg-type]
            postgres_user="someone",
        )

        printed = repr(probe)

        assert "hunter2-do-not-print" not in printed
        assert "k" * 40 not in printed
        # The computed URLs embed the password, so they are left out of repr
        # entirely rather than relying on the password itself being masked.
        assert probe.database_url not in printed
        assert probe.redis_url not in printed
        assert "database_url=" not in printed
        assert "redis_url=" not in printed
        # And the values really are reachable — the redaction is in repr, not
        # in the settings being unset.
        assert probe.postgres_password.get_secret_value() == "hunter2-do-not-print"
        assert "hunter2-do-not-print" in probe.database_url


class TestBrowserHardening:
    async def test_responses_carry_the_headers_that_contain_an_xss(self, api: AsyncClient) -> None:
        response = await api.get("/api/v1/health/live")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    async def test_every_response_carries_a_request_id(self, api: AsyncClient) -> None:
        """Turns "it failed at about four" into one log line."""
        response = await api.get("/api/v1/health/live")

        assert response.headers["X-Request-ID"]

    async def test_a_caller_supplied_request_id_is_honoured(self, api: AsyncClient) -> None:
        """So a trace started at the proxy survives into the backend logs."""
        response = await api.get(
            "/api/v1/health/live", headers={"X-Request-ID": "trace-from-the-edge"}
        )

        assert response.headers["X-Request-ID"] == "trace-from-the-edge"


class TestSentryScrubbing:
    def test_a_token_in_a_query_string_never_leaves_the_process(self) -> None:
        """This application puts verification and reset tokens in query strings.
        One in a third-party dashboard is a working account takeover."""
        from app.core.observability import before_send

        event = before_send(
            {
                "request": {
                    "query_string": "token=super-secret-value",
                    "headers": {"Authorization": "Bearer abc", "User-Agent": "x"},
                    "cookies": "ts_refresh=abc",
                },
                "extra": {"password": "hunter2", "tender_id": "keep-me"},
            },  # type: ignore[arg-type]
            {},  # type: ignore[arg-type]
        )

        assert event is not None
        assert "super-secret-value" not in str(event)
        assert event["request"]["headers"]["Authorization"] == "[redacted]"
        assert event["request"]["cookies"] == "[redacted]"
        assert event["extra"]["password"] == "[redacted]"
        # Scrubbing must not eat the context that makes an event useful.
        assert event["extra"]["tender_id"] == "keep-me"
        assert event["request"]["headers"]["User-Agent"] == "x"
