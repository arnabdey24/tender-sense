"""Notification settings, recipients and the in-app centre over HTTP.

The rules worth pinning are the ones a customer would be harmed by if they
broke: mail never goes to an address nobody proved they own, an unsubscribe is
honoured for good, and one member clearing their badge does not hide news from
the rest of the company.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import generate_token, hash_password, hash_token
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import (
    EmailOutbox,
    Notification,
    NotificationRecipient,
    NotificationType,
)
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.users.models import User


@dataclass
class Tenant:
    org: Organization
    headers: dict[str, str]
    email: str
    user_id: object


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def make_tenant(
    *, role: OrgRole = OrgRole.ADMIN, org: Organization | None = None, name: str = "Meghna"
) -> Tenant:
    email = f"{name.lower()}-{uuid4().hex[:10]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name=f"{name} Person",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
        )
        session.add(user)
        if org is None:
            organization = Organization(name=name, slug=f"{name.lower()}-{uuid4().hex[:8]}")
            session.add(organization)
        else:
            organization = await session.merge(org)
        await session.flush()
        session.add(
            Membership(
                org_id=organization.id,
                user_id=user.id,
                role=role,
                status=MembershipStatus.ACTIVE,
            )
        )
        await session.flush()
        issued = await issue_session(session, user=user, org_id=organization.id)
        token = issued.response.access_token
        await session.refresh(organization)
        user_id = user.id
    return Tenant(
        org=organization,
        headers={"Authorization": f"Bearer {token}"},
        email=email,
        user_id=user_id,
    )


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


@pytest.fixture
async def member(tenant: Tenant) -> AsyncIterator[Tenant]:
    """A second person in the same organization."""
    created = await make_tenant(role=OrgRole.MEMBER, org=tenant.org, name="Colleague")
    yield created
    async with session_scope() as session:
        found = await session.scalar(select(User).where(User.email == created.email))
        if found is not None:
            await session.delete(found)


async def add_notification(org_id: object, title: str = "A new match") -> Notification:
    async with session_scope() as session:
        record = Notification(
            org_id=org_id,
            type=NotificationType.INSTANT_MATCH,
            title=title,
            link="/app/tenders/x",
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record


async def outbox_for(org_id: object) -> list[EmailOutbox]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(EmailOutbox).where(EmailOutbox.org_id == org_id).order_by(EmailOutbox.created_at)
        )
        return list(rows.all())


class TestSettings:
    async def test_defaults_are_created_on_first_read(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.get("/api/v1/notification-settings", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert body["digest_enabled"] is True
        assert body["digest_time"] == "08:00:00"
        assert body["instant_min_grade"] == "S"
        assert body["reminder_offsets"] == [7, 2]

    async def test_the_digest_timezone_starts_as_the_organizations_own(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """08:00 UTC would reach a Dhaka company in the afternoon."""
        async with session_scope() as session:
            org = await session.get(Organization, tenant.org.id)
            assert org is not None
            org.timezone = "Europe/London"

        body = (await api.get("/api/v1/notification-settings", headers=tenant.headers)).json()

        assert body["digest_timezone"] == "Europe/London"

    async def test_an_admin_can_change_them(self, api: AsyncClient, tenant: Tenant) -> None:
        response = await api.put(
            "/api/v1/notification-settings",
            json={
                "digest_time": "06:30:00",
                "instant_min_grade": "A",
                "reminder_offsets": [3, 14, 3],
            },
            headers=tenant.headers,
        )

        body = response.json()
        assert response.status_code == 200
        assert body["digest_time"] == "06:30:00"
        assert body["instant_min_grade"] == "A"
        # De-duplicated and ordered, so the far nudge precedes the near one and
        # a repeated number cannot mail twice.
        assert body["reminder_offsets"] == [14, 3]

    async def test_a_member_cannot_change_them(
        self, api: AsyncClient, tenant: Tenant, member: Tenant
    ) -> None:
        response = await api.put(
            "/api/v1/notification-settings",
            json={"digest_enabled": False},
            headers=member.headers,
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "admin_required"

    async def test_an_unknown_timezone_is_rejected(self, api: AsyncClient, tenant: Tenant) -> None:
        """A typo here would silently move a company's digest by hours."""
        response = await api.put(
            "/api/v1/notification-settings",
            json={"digest_timezone": "Asia/Dacca_typo"},
            headers=tenant.headers,
        )

        assert response.status_code == 422

    async def test_a_zero_day_reminder_is_rejected(self, api: AsyncClient, tenant: Tenant) -> None:
        """ "On the day it closes" is too late to act on."""
        response = await api.put(
            "/api/v1/notification-settings",
            json={"reminder_offsets": [0]},
            headers=tenant.headers,
        )

        assert response.status_code == 422


class TestRecipients:
    async def test_adding_one_sends_a_confirmation_and_delivers_nothing_yet(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """Without this, an admin could route a shortlist anywhere they liked."""
        response = await api.post(
            "/api/v1/notification-recipients",
            json={"email": "bids@tsense-test.io", "name": "Bid desk"},
            headers=tenant.headers,
        )

        body = response.json()
        assert response.status_code == 201
        assert body["verified_at"] is None

        queued = await outbox_for(tenant.org.id)
        assert [email.template_key for email in queued] == ["recipient_verify"]

    async def test_the_same_address_twice_is_a_conflict(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """A silent re-send would make this endpoint a way to mail someone
        repeatedly."""
        payload = {"email": "bids@tsense-test.io"}
        await api.post("/api/v1/notification-recipients", json=payload, headers=tenant.headers)
        response = await api.post(
            "/api/v1/notification-recipients", json=payload, headers=tenant.headers
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "recipient_exists"

    async def test_a_member_cannot_add_one(
        self, api: AsyncClient, tenant: Tenant, member: Tenant
    ) -> None:
        response = await api.post(
            "/api/v1/notification-recipients",
            json={"email": "bids@tsense-test.io"},
            headers=member.headers,
        )

        assert response.status_code == 403

    async def test_confirming_from_the_emailed_link_works_without_a_session(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """The person holding the address may have no account at all."""
        token = await seed_recipient(tenant.org.id, "bids@tsense-test.io")

        response = await api.post("/api/v1/notifications/verify-recipient", json={"token": token})

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "verified"
        assert body["email"] == "bids@tsense-test.io"

    async def test_a_confirmation_link_cannot_be_replayed(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        token = await seed_recipient(tenant.org.id, "bids@tsense-test.io")
        await api.post("/api/v1/notifications/verify-recipient", json={"token": token})

        response = await api.post("/api/v1/notifications/verify-recipient", json={"token": token})

        assert response.status_code == 404

    async def test_unsubscribing_is_honoured_and_the_link_keeps_working(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """Someone re-clicking an old link and being told "invalid" concludes it
        failed, and reports the next message as spam instead."""
        await seed_recipient(tenant.org.id, "bids@tsense-test.io", verified=True)
        async with session_scope() as session:
            recipient = await session.scalar(
                select(NotificationRecipient).where(NotificationRecipient.org_id == tenant.org.id)
            )
            assert recipient is not None
            unsubscribe_token = recipient.unsubscribe_token

        first = await api.post(
            "/api/v1/notifications/unsubscribe", json={"token": unsubscribe_token}
        )
        second = await api.post(
            "/api/v1/notifications/unsubscribe", json={"token": unsubscribe_token}
        )

        assert first.status_code == 200
        assert second.status_code == 200
        listed = (await api.get("/api/v1/notification-recipients", headers=tenant.headers)).json()
        assert listed[0]["unsubscribed_at"] is not None

    async def test_resending_issues_a_fresh_token(self, api: AsyncClient, tenant: Tenant) -> None:
        """So an old link sitting in an inbox stops working."""
        old_token = await seed_recipient(tenant.org.id, "bids@tsense-test.io")
        listed = (await api.get("/api/v1/notification-recipients", headers=tenant.headers)).json()

        response = await api.post(
            f"/api/v1/notification-recipients/{listed[0]['id']}/resend",
            headers=tenant.headers,
        )

        assert response.status_code == 200
        replayed = await api.post(
            "/api/v1/notifications/verify-recipient", json={"token": old_token}
        )
        assert replayed.status_code == 404

    async def test_a_verified_address_cannot_be_re_verified(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        await seed_recipient(tenant.org.id, "bids@tsense-test.io", verified=True)
        listed = (await api.get("/api/v1/notification-recipients", headers=tenant.headers)).json()

        response = await api.post(
            f"/api/v1/notification-recipients/{listed[0]['id']}/resend",
            headers=tenant.headers,
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_verified"

    async def test_one_organization_cannot_touch_anothers_recipients(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        other = await make_tenant(name="Padma")
        try:
            await seed_recipient(other.org.id, "theirs@tsense-test.io")
            listed = (
                await api.get("/api/v1/notification-recipients", headers=other.headers)
            ).json()

            response = await api.delete(
                f"/api/v1/notification-recipients/{listed[0]['id']}",
                headers=tenant.headers,
            )

            assert response.status_code == 404
        finally:
            await drop_tenant(other)


async def seed_recipient(org_id: object, email: str, *, verified: bool = False) -> str:
    """Create a recipient directly and return its raw verification token."""
    token = generate_token()
    async with session_scope() as session:
        session.add(
            NotificationRecipient(
                org_id=org_id,
                email=email,
                verify_token_hash=None if verified else hash_token(token),
                verified_at=utcnow() if verified else None,
                unsubscribe_token=generate_token(),
            )
        )
    return token


class TestNotificationCentre:
    async def test_it_lists_the_organizations_notifications(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        await add_notification(tenant.org.id, "Grade S match: Network switches")

        response = await api.get("/api/v1/notifications", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert body[0]["title"] == "Grade S match: Network switches"
        assert body[0]["read"] is False

    async def test_read_state_is_per_person(
        self, api: AsyncClient, tenant: Tenant, member: Tenant
    ) -> None:
        """A match belongs to the company; one person clearing their badge must
        not hide it from their colleagues."""
        notification = await add_notification(tenant.org.id)

        await api.post(f"/api/v1/notifications/{notification.id}/read", headers=tenant.headers)

        mine = (await api.get("/api/v1/notifications", headers=tenant.headers)).json()
        theirs = (await api.get("/api/v1/notifications", headers=member.headers)).json()
        assert mine[0]["read"] is True
        assert theirs[0]["read"] is False

    async def test_the_badge_counts_only_what_this_person_has_not_read(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        first = await add_notification(tenant.org.id, "One")
        await add_notification(tenant.org.id, "Two")

        before = (
            await api.get("/api/v1/notifications/unread-count", headers=tenant.headers)
        ).json()
        await api.post(f"/api/v1/notifications/{first.id}/read", headers=tenant.headers)
        after = (await api.get("/api/v1/notifications/unread-count", headers=tenant.headers)).json()

        assert before["unread"] == 2
        assert after["unread"] == 1

    async def test_reading_twice_is_not_an_error(self, api: AsyncClient, tenant: Tenant) -> None:
        notification = await add_notification(tenant.org.id)

        first = await api.post(
            f"/api/v1/notifications/{notification.id}/read", headers=tenant.headers
        )
        second = await api.post(
            f"/api/v1/notifications/{notification.id}/read", headers=tenant.headers
        )

        assert first.status_code == 204
        assert second.status_code == 204

    async def test_mark_all_clears_the_badge(self, api: AsyncClient, tenant: Tenant) -> None:
        await add_notification(tenant.org.id, "One")
        await add_notification(tenant.org.id, "Two")

        response = await api.post("/api/v1/notifications/read-all", headers=tenant.headers)

        assert response.json()["unread"] == 0

    async def test_one_organization_never_sees_anothers(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        other = await make_tenant(name="Padma")
        try:
            await add_notification(other.org.id, "Their private match")

            body = (await api.get("/api/v1/notifications", headers=tenant.headers)).json()

            assert all(item["title"] != "Their private match" for item in body)
        finally:
            await drop_tenant(other)

    async def test_unread_only_filters_the_list(self, api: AsyncClient, tenant: Tenant) -> None:
        first = await add_notification(tenant.org.id, "Read one")
        await add_notification(tenant.org.id, "Unread one")
        await api.post(f"/api/v1/notifications/{first.id}/read", headers=tenant.headers)

        body = (
            await api.get("/api/v1/notifications?unread_only=true", headers=tenant.headers)
        ).json()

        assert [item["title"] for item in body] == ["Unread one"]


class TestTestEmail:
    async def test_it_defaults_to_the_senders_own_address(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.post(
            "/api/v1/notification-settings/test-email", headers=tenant.headers
        )

        body = response.json()
        assert response.status_code == 200
        assert body["to_email"] == tenant.email
        queued = await outbox_for(tenant.org.id)
        assert queued[-1].template_key == "test_email"

    async def test_a_member_cannot_send_one(
        self, api: AsyncClient, tenant: Tenant, member: Tenant
    ) -> None:
        """It takes an arbitrary address and mails it."""
        response = await api.post(
            "/api/v1/notification-settings/test-email", headers=member.headers
        )

        assert response.status_code == 403
