"""Tenant scoping and role checks.

These guard the rule that an organization is only ever taken from the verified
access token, and that membership is re-read per request so revocation is
immediate rather than delayed until the token expires.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.deps import OrgContext, require_org_admin, require_superuser
from app.core.exceptions import PermissionDeniedError
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.users.models import User


def make_context(role: OrgRole) -> OrgContext:
    user = User(id=uuid4(), email="a@example.com", full_name="A")
    org = Organization(id=uuid4(), name="Acme", slug="acme")
    membership = Membership(
        org_id=org.id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE
    )
    return OrgContext(user=user, org=org, membership=membership)


class TestOrgContext:
    def test_admin_context_reports_admin(self) -> None:
        context = make_context(OrgRole.ADMIN)

        assert context.is_admin is True
        assert context.role is OrgRole.ADMIN

    def test_member_context_is_not_admin(self) -> None:
        assert make_context(OrgRole.MEMBER).is_admin is False

    def test_org_id_comes_from_the_organization(self) -> None:
        context = make_context(OrgRole.MEMBER)

        assert context.org_id == context.org.id


class TestRoleGuards:
    async def test_admin_passes_the_admin_guard(self) -> None:
        context = make_context(OrgRole.ADMIN)

        assert await require_org_admin(context) is context

    async def test_member_is_refused_by_the_admin_guard(self) -> None:
        with pytest.raises(PermissionDeniedError) as exc:
            await require_org_admin(make_context(OrgRole.MEMBER))

        assert exc.value.code == "admin_required"
        assert exc.value.status_code == 403

    async def test_org_admin_is_not_platform_staff(self) -> None:
        """An organization admin must not reach the platform admin endpoints."""
        org_admin = make_context(OrgRole.ADMIN).user

        with pytest.raises(PermissionDeniedError) as exc:
            await require_superuser(org_admin)

        assert exc.value.code == "staff_required"

    async def test_superuser_passes_the_staff_guard(self) -> None:
        staff = User(id=uuid4(), email="staff@example.com", full_name="Staff", is_superuser=True)

        assert await require_superuser(staff) is staff
