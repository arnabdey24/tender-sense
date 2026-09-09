"""Organization, member and invitation rules against a real Postgres.

These exercise the service layer directly rather than over HTTP: the auth
dependencies that build an ``OrgContext`` are the concern of the auth module,
and the rules worth pinning down here are the database-backed ones (unique
slugs, the last-admin guard, the partial unique index on live invitations).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.pagination import PageParams
from app.core.security import hash_token
from app.core.time import utcnow
from app.db.session import dispose_engine, session_scope
from app.modules.orgs import repository as repo
from app.modules.orgs import service
from app.modules.orgs.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.modules.orgs.schemas import InvitationCreate, MemberUpdate, OrganizationCreate
from app.modules.users.models import User


@dataclass
class SentEmail:
    invitation: Invitation
    raw_token: str
    dedupe_key: str


@dataclass
class Cleanup:
    org_ids: list[UUID] = field(default_factory=list)
    user_ids: list[UUID] = field(default_factory=list)


@pytest.fixture
async def cleanup() -> AsyncIterator[Cleanup]:
    """Delete everything a test created; org deletes cascade to members."""
    bag = Cleanup()
    try:
        yield bag
    finally:
        async with session_scope() as session:
            if bag.org_ids:
                await session.execute(delete(Organization).where(Organization.id.in_(bag.org_ids)))
            if bag.user_ids:
                await session.execute(delete(User).where(User.id.in_(bag.user_ids)))
        await dispose_engine()


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[SentEmail]:
    """Capture invitation emails instead of queueing them in the outbox."""
    captured: list[SentEmail] = []

    async def fake_send(
        _session: AsyncSession,
        *,
        invitation: Invitation,
        raw_token: str,
        dedupe_key: str,
        **_kwargs: Any,
    ) -> None:
        captured.append(
            SentEmail(invitation=invitation, raw_token=raw_token, dedupe_key=dedupe_key)
        )

    monkeypatch.setattr(service, "_send_invitation_email", fake_send)
    return captured


async def make_user(session: AsyncSession, cleanup: Cleanup, *, name: str = "Test User") -> User:
    user = User(email=f"user-{uuid4().hex}@tsense-test.io", full_name=name)
    session.add(user)
    await session.flush()
    cleanup.user_ids.append(user.id)
    return user


async def make_org(
    session: AsyncSession, cleanup: Cleanup, owner: User, *, name: str = "Test Org"
) -> Organization:
    org, _ = await service.create_organization(
        session, user=owner, data=OrganizationCreate(name=name)
    )
    cleanup.org_ids.append(org.id)
    return org


async def add_member(
    session: AsyncSession, org: Organization, user: User, role: OrgRole = OrgRole.MEMBER
) -> Membership:
    membership = Membership(org_id=org.id, user_id=user.id, role=role, joined_at=utcnow())
    session.add(membership)
    await session.flush()
    return membership


class TestCreateOrganization:
    async def test_creator_becomes_an_active_admin(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            user = await make_user(session, cleanup, name="Rafiq Islam")

            org, membership = await service.create_organization(
                session, user=user, data=OrganizationCreate(name="Grameen Bank", country="bd")
            )
            cleanup.org_ids.append(org.id)

            assert org.slug == "grameen-bank"
            assert org.country == "BD"
            assert org.created_by_id == user.id
            assert membership.role is OrgRole.ADMIN
            assert membership.status is MembershipStatus.ACTIVE

    async def test_a_user_may_create_a_second_organization(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            user = await make_user(session, cleanup)

            first = await make_org(session, cleanup, user, name="First Org")
            second = await make_org(session, cleanup, user, name="Second Org")

            assert first.id != second.id
            assert await repo.get_membership(session, second.id, user.id) is not None

    async def test_colliding_names_get_a_numeric_suffix(self, cleanup: Cleanup) -> None:
        name = f"Collide {uuid4().hex[:8]}"

        async with session_scope() as session:
            user = await make_user(session, cleanup)
            first = await make_org(session, cleanup, user, name=name)
            second = await make_org(session, cleanup, user, name=name)
            third = await make_org(session, cleanup, user, name=name)

            assert second.slug == f"{first.slug}-2"
            assert third.slug == f"{first.slug}-3"


class TestMemberGuards:
    async def test_you_cannot_change_your_own_role(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            with pytest.raises(ValidationError) as excinfo:
                await service.update_member(
                    session,
                    org=org,
                    actor=admin,
                    target_user_id=admin.id,
                    data=MemberUpdate(role=OrgRole.MEMBER),
                )

            assert excinfo.value.code == "cannot_change_own_role"

    async def test_the_last_admin_cannot_be_demoted(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            other = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            await add_member(session, org, other)

            with pytest.raises(ConflictError) as excinfo:
                await service.update_member(
                    session,
                    org=org,
                    actor=other,
                    target_user_id=admin.id,
                    data=MemberUpdate(role=OrgRole.MEMBER),
                )

            assert excinfo.value.code == "last_admin"

    async def test_the_last_admin_cannot_be_disabled(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            other = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            await add_member(session, org, other)

            with pytest.raises(ConflictError):
                await service.update_member(
                    session,
                    org=org,
                    actor=other,
                    target_user_id=admin.id,
                    data=MemberUpdate(status=MembershipStatus.DISABLED),
                )

    async def test_an_admin_can_be_demoted_once_another_exists(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            second_admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            await add_member(session, org, second_admin, role=OrgRole.ADMIN)

            membership, _ = await service.update_member(
                session,
                org=org,
                actor=second_admin,
                target_user_id=admin.id,
                data=MemberUpdate(role=OrgRole.MEMBER),
            )

            assert membership.role is OrgRole.MEMBER

    async def test_the_last_admin_cannot_remove_themselves(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            with pytest.raises(ConflictError) as excinfo:
                await service.remove_member(session, org=org, actor=admin, target_user_id=admin.id)

            assert excinfo.value.code == "last_admin"

    async def test_an_admin_can_leave_once_another_admin_exists(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            second_admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            await add_member(session, org, second_admin, role=OrgRole.ADMIN)

            await service.remove_member(session, org=org, actor=admin, target_user_id=admin.id)

            assert await repo.get_membership(session, org.id, admin.id) is None

    async def test_updating_a_non_member_is_a_404(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            stranger = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            with pytest.raises(NotFoundError):
                await service.update_member(
                    session,
                    org=org,
                    actor=admin,
                    target_user_id=stranger.id,
                    data=MemberUpdate(role=OrgRole.ADMIN),
                )


class TestInvitations:
    async def test_invite_then_accept_creates_a_membership(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup, name="Nadia Rahman")
            invitee = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            invitation, raw_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=invitee.email, role=OrgRole.ADMIN),
            )

            assert invitation.token_hash == hash_token(raw_token)
            assert raw_token not in invitation.token_hash
            assert sent_emails[-1].dedupe_key == f"invitation:{invitation.id}"

            membership, _ = await service.accept_invitation(session, token=raw_token, user=invitee)

            assert membership.role is OrgRole.ADMIN
            assert membership.status is MembershipStatus.ACTIVE
            assert invitation.accepted_at is not None
            assert invitation.accepted_user_id == invitee.id

    async def test_accepting_with_a_different_address_is_refused(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            wrong_user = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            _, raw_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email="invited@tsense-test.io"),
            )

            with pytest.raises(PermissionDeniedError) as excinfo:
                await service.accept_invitation(session, token=raw_token, user=wrong_user)

            assert excinfo.value.code == "invitation_email_mismatch"
            assert "invited@tsense-test.io" in excinfo.value.message
            assert await repo.get_membership(session, org.id, wrong_user.id) is None

    async def test_the_address_match_ignores_case(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            invitee = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            _, raw_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=invitee.email.upper()),
            )

            membership, _ = await service.accept_invitation(session, token=raw_token, user=invitee)

            assert membership.user_id == invitee.id

    async def test_accepting_twice_is_idempotent(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            invitee = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            _, raw_token = await service.invite_member(
                session, org=org, inviter=admin, data=InvitationCreate(email=invitee.email)
            )

            first, _ = await service.accept_invitation(session, token=raw_token, user=invitee)
            second, _ = await service.accept_invitation(session, token=raw_token, user=invitee)

            assert first.id == second.id

    async def test_inviting_an_existing_member_is_a_conflict(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            with pytest.raises(ConflictError) as excinfo:
                await service.invite_member(
                    session, org=org, inviter=admin, data=InvitationCreate(email=admin.email)
                )

            assert excinfo.value.code == "already_member"

    async def test_a_second_invitation_revokes_the_first(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        email = f"repeat-{uuid4().hex}@tsense-test.io"

        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            first, first_token = await service.invite_member(
                session, org=org, inviter=admin, data=InvitationCreate(email=email)
            )
            second, second_token = await service.invite_member(
                session, org=org, inviter=admin, data=InvitationCreate(email=email)
            )

            assert first.id != second.id
            assert first.revoked_at is not None
            assert second.is_pending
            assert (await repo.get_pending_invitation(session, org.id, email)) is not None

            with pytest.raises(NotFoundError):
                await service.preview_invitation(session, first_token)

            preview = await service.preview_invitation(session, second_token)
            assert preview.org_name == org.name

    async def test_revoked_and_unknown_tokens_look_the_same(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            invitation, raw_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=f"revoke-{uuid4().hex}@tsense-test.io"),
            )

            await service.revoke_invitation(session, org=org, invitation_id=invitation.id)

            with pytest.raises(NotFoundError) as revoked:
                await service.preview_invitation(session, raw_token)
            with pytest.raises(NotFoundError) as unknown:
                await service.preview_invitation(session, "not-a-real-token")

            assert revoked.value.code == unknown.value.code == "invitation_not_found"

    async def test_preview_of_an_expired_invitation_is_rejected(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            invitee = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            invitation, raw_token = await service.invite_member(
                session, org=org, inviter=admin, data=InvitationCreate(email=invitee.email)
            )

            invitation.expires_at = utcnow() - timedelta(minutes=1)
            await session.flush()

            with pytest.raises(ValidationError) as excinfo:
                await service.preview_invitation(session, raw_token)
            assert excinfo.value.code == "invitation_expired"

            with pytest.raises(ValidationError):
                await service.accept_invitation(session, token=raw_token, user=invitee)

    async def test_preview_reports_whether_the_invitee_must_sign_up(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup, name="Nadia Rahman")
            known = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)

            _, known_token = await service.invite_member(
                session, org=org, inviter=admin, data=InvitationCreate(email=known.email)
            )
            _, stranger_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=f"new-{uuid4().hex}@tsense-test.io"),
            )

            known_preview = await service.preview_invitation(session, known_token)
            stranger_preview = await service.preview_invitation(session, stranger_token)

            assert known_preview.requires_signup is False
            assert known_preview.inviter_name == "Nadia Rahman"
            assert stranger_preview.requires_signup is True

    async def test_resend_issues_a_new_token_and_invalidates_the_old_one(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup)
            org = await make_org(session, cleanup, admin)
            invitation, old_token = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=f"resend-{uuid4().hex}@tsense-test.io"),
            )

            resent, new_token = await service.resend_invitation(
                session, org=org, inviter=admin, invitation_id=invitation.id
            )

            assert resent.id == invitation.id
            assert new_token != old_token
            assert sent_emails[-1].dedupe_key != f"invitation:{invitation.id}"
            with pytest.raises(NotFoundError):
                await service.preview_invitation(session, old_token)
            assert (await service.preview_invitation(session, new_token)).email == resent.email

    async def test_listing_invitations_reports_computed_status(
        self, cleanup: Cleanup, sent_emails: list[SentEmail]
    ) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup, name="Nadia Rahman")
            org = await make_org(session, cleanup, admin)
            pending, _ = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=f"pending-{uuid4().hex}@tsense-test.io"),
            )
            revoked, _ = await service.invite_member(
                session,
                org=org,
                inviter=admin,
                data=InvitationCreate(email=f"revoked-{uuid4().hex}@tsense-test.io"),
            )
            await service.revoke_invitation(session, org=org, invitation_id=revoked.id)

            listed = {row.id: row for row in await service.list_invitations(session, org.id)}

            assert listed[pending.id].status == "pending"
            assert listed[pending.id].invited_by_name == "Nadia Rahman"
            assert listed[revoked.id].status == "revoked"


class TestMemberListing:
    async def test_members_are_paginated_with_their_user_details(self, cleanup: Cleanup) -> None:
        async with session_scope() as session:
            admin = await make_user(session, cleanup, name="Nadia Rahman")
            org = await make_org(session, cleanup, admin)
            for _ in range(3):
                await add_member(session, org, await make_user(session, cleanup))

            first_page = await service.list_members(
                session, org.id, PageParams(page=1, page_size=2)
            )
            second_page = await service.list_members(
                session, org.id, PageParams(page=2, page_size=2)
            )

            assert first_page.total == 4
            assert len(first_page.items) == 2
            assert len(second_page.items) == 2
            assert first_page.items[0].email == admin.email
            assert first_page.items[0].full_name == "Nadia Rahman"
            assert first_page.items[0].role is OrgRole.ADMIN
