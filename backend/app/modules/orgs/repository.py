"""Query helpers for organizations, memberships and invitations.

Thin by design: no business rules live here, only SQL. Every function takes the
session first and returns ORM objects or plain tuples.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.orgs.models import (
    Invitation,
    Membership,
    MembershipStatus,
    Organization,
    OrgRole,
)
from app.modules.users.models import User


async def get_org_by_id(session: AsyncSession, org_id: UUID) -> Organization | None:
    return await session.get(Organization, org_id)


async def get_org_by_slug(session: AsyncSession, slug: str) -> Organization | None:
    stmt = select(Organization).where(Organization.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def slug_exists(session: AsyncSession, slug: str) -> bool:
    stmt = select(Organization.id).where(Organization.slug == slug).limit(1)
    return (await session.execute(stmt)).first() is not None


async def create_org(session: AsyncSession, org: Organization) -> Organization:
    session.add(org)
    await session.flush()
    return org


async def get_membership(session: AsyncSession, org_id: UUID, user_id: UUID) -> Membership | None:
    stmt = select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_members(
    session: AsyncSession, org_id: UUID, params: PageParams
) -> tuple[list[tuple[Membership, User]], int]:
    """One page of members joined to their user rows, plus the total count."""
    total_stmt = select(func.count()).select_from(Membership).where(Membership.org_id == org_id)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id)
        .order_by(Membership.joined_at.asc(), Membership.id.asc())
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = [(membership, user) for membership, user in (await session.execute(stmt)).all()]
    return rows, total


async def count_admins(session: AsyncSession, org_id: UUID) -> int:
    """Active admins only — a disabled admin cannot manage anything."""
    stmt = (
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.org_id == org_id,
            Membership.role == OrgRole.ADMIN,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def get_invitation_by_id(
    session: AsyncSession, org_id: UUID, invitation_id: UUID
) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.id == invitation_id, Invitation.org_id == org_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_invitation_by_token_hash(session: AsyncSession, token_hash: str) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_invitations(session: AsyncSession, org_id: UUID) -> list[Invitation]:
    stmt = (
        select(Invitation).where(Invitation.org_id == org_id).order_by(Invitation.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_pending_invitation(
    session: AsyncSession, org_id: UUID, email: str
) -> Invitation | None:
    """The single live invitation for an address, if any.

    The partial unique index guarantees at most one row can match.
    """
    stmt = select(Invitation).where(
        Invitation.org_id == org_id,
        Invitation.email == email,
        Invitation.accepted_at.is_(None),
        Invitation.revoked_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_membership_by_email(
    session: AsyncSession, org_id: UUID, email: str
) -> tuple[Membership, User] | None:
    """Look up a member by address; used to reject inviting an existing member."""
    stmt = (
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id, User.email == email)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row is not None else None


async def get_users_by_ids(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, User]:
    """Bulk-load users so invitation listings do not fan out one query per row."""
    if not user_ids:
        return {}
    stmt = select(User).where(User.id.in_(user_ids))
    return {user.id: user for user in (await session.execute(stmt)).scalars().all()}
