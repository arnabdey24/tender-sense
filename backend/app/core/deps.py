"""Shared FastAPI dependencies: the current user, organization and role.

Tenant scoping rule: ``org_id`` always comes from the access token via
:class:`OrgContext`, never from a request body or path. Repositories therefore
cannot be tricked into reading another tenant's rows.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.users.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login")
BearerToken = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


class OrgContext:
    """The authenticated user together with their active organization."""

    __slots__ = ("membership", "org", "user")

    def __init__(self, user: User, org: Organization, membership: Membership) -> None:
        self.user = user
        self.org = org
        self.membership = membership

    @property
    def org_id(self) -> UUID:
        return self.org.id

    @property
    def role(self) -> OrgRole:
        return self.membership.role

    @property
    def is_admin(self) -> bool:
        return self.membership.role is OrgRole.ADMIN


async def get_current_user(session: DbSession, credentials: BearerToken) -> User:
    """Resolve the bearer token to an active user."""
    if credentials is None:
        raise AuthenticationError("Not authenticated.")

    claims = decode_access_token(credentials.credentials)
    user = await session.get(User, claims.sub)
    if user is None:
        raise AuthenticationError("Account no longer exists.", code="user_not_found")
    if not user.is_active:
        raise PermissionDeniedError("This account has been deactivated.", code="account_disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_verified_user(user: CurrentUser) -> User:
    """A user who has confirmed their email address.

    Required before creating or joining an organization, so invitations and
    notifications can never be routed to an unproven address.
    """
    if not user.email_verified:
        raise PermissionDeniedError(
            "Verify your email address to continue.", code="email_not_verified"
        )
    return user


VerifiedUser = Annotated[User, Depends(get_verified_user)]


async def get_current_org(
    request: Request, session: DbSession, user: CurrentUser, credentials: BearerToken
) -> OrgContext:
    """Resolve the organization named by the access token.

    Membership is re-read on every request rather than trusted from the token,
    so removing or disabling a member takes effect immediately instead of when
    their access token expires.
    """
    assert credentials is not None  # get_current_user already rejected the None case
    claims = decode_access_token(credentials.credentials)
    if claims.org is None:
        raise PermissionDeniedError(
            "No active organization. Create or join one first.", code="no_active_org"
        )

    result = await session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(Membership.org_id == claims.org, Membership.user_id == user.id)
    )
    row = result.first()
    if row is None:
        raise PermissionDeniedError(
            "You are not a member of this organization.", code="not_a_member"
        )

    membership, org = row
    if membership.status is not MembershipStatus.ACTIVE:
        raise PermissionDeniedError(
            "Your membership has been disabled.", code="membership_disabled"
        )
    if not org.is_active:
        raise PermissionDeniedError("This organization is inactive.", code="org_inactive")

    context = OrgContext(user=user, org=org, membership=membership)
    request.state.org_id = org.id
    return context


CurrentOrg = Annotated[OrgContext, Depends(get_current_org)]


async def require_org_admin(context: CurrentOrg) -> OrgContext:
    if not context.is_admin:
        raise PermissionDeniedError(
            "Only organization admins can perform this action.", code="admin_required"
        )
    return context


RequireOrgAdmin = Annotated[OrgContext, Depends(require_org_admin)]


async def require_superuser(user: CurrentUser) -> User:
    """Platform staff, not organization admins."""
    if not user.is_superuser:
        raise PermissionDeniedError("Staff access required.", code="staff_required")
    return user


Superuser = Annotated[User, Depends(require_superuser)]
