"""Database access for authentication. No business rules live here."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.modules.auth.models import AuthToken, RefreshSession, TokenPurpose
from app.modules.orgs.models import Membership, MembershipStatus, Organization
from app.modules.users.models import OAuthAccount, User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Case-insensitive by virtue of the citext column."""
    result = await session.scalar(select(User).where(User.email == email))
    return result


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_oauth_account(
    session: AsyncSession, *, provider: str, provider_account_id: str
) -> OAuthAccount | None:
    result = await session.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_account_id == provider_account_id,
        )
    )
    return result


async def get_auth_token(
    session: AsyncSession, *, token_hash: str, purpose: TokenPurpose
) -> AuthToken | None:
    result = await session.scalar(
        select(AuthToken).where(AuthToken.token_hash == token_hash, AuthToken.purpose == purpose)
    )
    return result


async def invalidate_auth_tokens(
    session: AsyncSession, *, user_id: UUID, purpose: TokenPurpose, now: datetime | None = None
) -> None:
    """Burn any outstanding tokens so only the newest link works."""
    await session.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
        .values(used_at=now or utcnow())
    )


async def get_refresh_session(session: AsyncSession, token_hash: str) -> RefreshSession | None:
    result = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    )
    return result


async def revoke_refresh_family(
    session: AsyncSession, *, family_id: UUID, now: datetime | None = None
) -> int:
    """Revoke every live token descended from one login. Returns the count."""
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now or utcnow())
        ),
    )
    return result.rowcount or 0


async def revoke_all_refresh_sessions(
    session: AsyncSession, *, user_id: UUID, now: datetime | None = None
) -> int:
    result = cast(
        CursorResult[Any],
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now or utcnow())
        ),
    )
    return result.rowcount or 0


async def list_memberships(
    session: AsyncSession, user_id: UUID
) -> list[tuple[Membership, Organization]]:
    """Active memberships in active organizations, oldest first."""
    result = await session.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.org_id)
        .where(
            Membership.user_id == user_id,
            Membership.status == MembershipStatus.ACTIVE,
            Organization.is_active.is_(True),
        )
        .order_by(Membership.joined_at)
    )
    return [(membership, org) for membership, org in result.all()]


async def get_membership(
    session: AsyncSession, *, user_id: UUID, org_id: UUID
) -> Membership | None:
    result = await session.scalar(
        select(Membership).where(Membership.user_id == user_id, Membership.org_id == org_id)
    )
    return result
