"""Authentication business rules.

Two ideas drive the design:

* **Do not leak which addresses are registered.** Registration, login,
  forgot-password and resend-verification all respond the same way whether or
  not the address exists.
* **Refresh tokens rotate, and reuse is treated as theft.** Every refresh
  revokes the presented token and issues a successor in the same family.
  Presenting an already-revoked token means the value escaped, so the entire
  family is revoked and the user must sign in again.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.ids import new_id
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_and_upgrade_password,
)
from app.core.time import utcnow
from app.modules.auth import repository as repo
from app.modules.auth.models import AuthToken, RefreshSession, TokenPurpose
from app.modules.auth.schemas import (
    MembershipSummary,
    RegisterRequest,
    SessionResponse,
    UserRead,
)
from app.modules.users.models import User

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """An access token plus the raw refresh token to put in the cookie."""

    response: SessionResponse
    refresh_token: str
    refresh_expires_at: datetime


@dataclass(frozen=True, slots=True)
class ClientInfo:
    user_agent: str | None = None
    ip_address: str | None = None


# --------------------------------------------------------------------------
# registration and email verification
# --------------------------------------------------------------------------
async def register(session: AsyncSession, data: RegisterRequest) -> tuple[User, str | None]:
    """Create an account and return it with the raw verification token.

    Re-registering an existing address returns ``(existing_user, None)`` so the
    endpoint can answer identically either way; no email is sent and the
    original password is untouched.
    """
    existing = await repo.get_user_by_email(session, data.email)
    if existing is not None:
        logger.info("register_existing_email", user_id=str(existing.id))
        return existing, None

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    session.add(user)
    await session.flush()

    token = await create_action_token(session, user=user, purpose=TokenPurpose.VERIFY_EMAIL)
    logger.info("user_registered", user_id=str(user.id))
    return user, token


async def create_action_token(session: AsyncSession, *, user: User, purpose: TokenPurpose) -> str:
    """Issue a single-use emailed token, invalidating older ones of its kind."""
    await repo.invalidate_auth_tokens(session, user_id=user.id, purpose=purpose)

    ttl = (
        timedelta(hours=settings.email_verify_token_ttl_hours)
        if purpose is TokenPurpose.VERIFY_EMAIL
        else timedelta(minutes=settings.password_reset_token_ttl_minutes)
    )
    raw_token = generate_token()
    session.add(
        AuthToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            expires_at=utcnow() + ttl,
        )
    )
    await session.flush()
    return raw_token


async def consume_action_token(session: AsyncSession, *, token: str, purpose: TokenPurpose) -> User:
    """Validate a token, mark it used, and return its user."""
    record = await repo.get_auth_token(session, token_hash=hash_token(token), purpose=purpose)
    if record is None:
        raise ValidationError("This link is not valid.", code="invalid_token")
    if not record.is_usable():
        raise ValidationError(
            "This link has expired or has already been used.", code="token_expired"
        )

    user = await repo.get_user_by_id(session, record.user_id)
    if user is None:  # pragma: no cover - cascade makes this unreachable
        raise NotFoundError("Account no longer exists.")

    record.used_at = utcnow()
    await session.flush()
    return user


async def verify_email(session: AsyncSession, token: str) -> User:
    user = await consume_action_token(session, token=token, purpose=TokenPurpose.VERIFY_EMAIL)
    if not user.email_verified:
        user.email_verified_at = utcnow()
        await session.flush()
        logger.info("email_verified", user_id=str(user.id))
    return user


async def start_email_verification(session: AsyncSession, email: str) -> tuple[User, str] | None:
    """Return the user and a fresh token, or ``None`` when there is nothing to do."""
    user = await repo.get_user_by_email(session, email)
    if user is None or user.email_verified or not user.is_active:
        return None
    token = await create_action_token(session, user=user, purpose=TokenPurpose.VERIFY_EMAIL)
    return user, token


# --------------------------------------------------------------------------
# login
# --------------------------------------------------------------------------
async def authenticate(session: AsyncSession, *, email: str, password: str) -> User:
    """Check credentials.

    The same error is raised for an unknown address and a wrong password, and
    the password is always verified against something so the timing does not
    differ between the two.
    """
    user = await repo.get_user_by_email(session, email)
    password_hash = user.password_hash if user else None

    valid, upgraded_hash = verify_and_upgrade_password(password, password_hash)
    if not valid or user is None:
        raise AuthenticationError("Incorrect email or password.", code="invalid_credentials")
    if not user.is_active:
        raise PermissionDeniedError("This account has been deactivated.", code="account_disabled")

    if upgraded_hash is not None:
        user.password_hash = upgraded_hash

    user.last_login_at = utcnow()
    await session.flush()
    return user


# --------------------------------------------------------------------------
# sessions: access token + rotating refresh token
# --------------------------------------------------------------------------
async def issue_session(
    session: AsyncSession,
    *,
    user: User,
    org_id: UUID | None = None,
    family_id: UUID | None = None,
    client: ClientInfo | None = None,
) -> IssuedSession:
    """Mint an access token and a new refresh token.

    ``family_id`` continues an existing chain during rotation; omit it to start
    a new one at login.
    """
    memberships = await repo.list_memberships(session, user.id)
    summaries = [
        MembershipSummary(org_id=org.id, org_name=org.name, org_slug=org.slug, role=membership.role)
        for membership, org in memberships
    ]

    active_org_id = _resolve_active_org(org_id, summaries)
    role = next((s.role.value for s in summaries if s.org_id == active_org_id), None)

    access_token, access_expires_at = create_access_token(
        user_id=user.id, org_id=active_org_id, role=role
    )

    raw_refresh = generate_token()
    refresh_expires_at = utcnow() + timedelta(days=settings.refresh_token_ttl_days)
    client = client or ClientInfo()
    refresh_session = RefreshSession(
        user_id=user.id,
        org_id=active_org_id,
        token_hash=hash_token(raw_refresh),
        family_id=family_id or new_id(),
        expires_at=refresh_expires_at,
        user_agent=client.user_agent,
        ip_address=client.ip_address,
    )
    session.add(refresh_session)
    await session.flush()

    return IssuedSession(
        response=SessionResponse(
            access_token=access_token,
            expires_at=access_expires_at,
            user=UserRead(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
                email_verified=user.email_verified,
                has_password=user.has_password,
                is_superuser=user.is_superuser,
                created_at=user.created_at,
            ),
            memberships=summaries,
            active_org_id=active_org_id,
        ),
        refresh_token=raw_refresh,
        refresh_expires_at=refresh_expires_at,
    )


def _resolve_active_org(
    requested: UUID | None, memberships: list[MembershipSummary]
) -> UUID | None:
    """Honour the requested organization when the user still belongs to it,
    otherwise fall back to their first one."""
    if requested is not None and any(s.org_id == requested for s in memberships):
        return requested
    return memberships[0].org_id if memberships else None


async def rotate_session(
    session: AsyncSession, *, refresh_token: str, client: ClientInfo | None = None
) -> IssuedSession:
    """Exchange a refresh token for a new pair.

    Reusing a revoked token revokes its whole family: either the token leaked,
    or a legitimate client raced with itself, and both are safest handled by
    forcing a fresh login.
    """
    record = await repo.get_refresh_session(session, hash_token(refresh_token))
    if record is None:
        raise AuthenticationError("Session is no longer valid.", code="invalid_refresh_token")

    if record.revoked_at is not None:
        revoked = await repo.revoke_refresh_family(session, family_id=record.family_id)
        # Commit before raising: the request-scoped session rolls back on an
        # exception, which would otherwise undo the very revocation that makes
        # reuse detection worth having.
        await session.commit()
        logger.warning(
            "refresh_token_reuse_detected",
            user_id=str(record.user_id),
            family_id=str(record.family_id),
            revoked_sessions=revoked,
        )
        raise AuthenticationError(
            "Session is no longer valid. Please sign in again.", code="refresh_token_reused"
        )

    if not record.is_active():
        raise AuthenticationError("Session has expired.", code="refresh_token_expired")

    user = await repo.get_user_by_id(session, record.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is no longer active.", code="account_disabled")

    issued = await issue_session(
        session,
        user=user,
        org_id=record.org_id,
        family_id=record.family_id,
        client=client,
    )

    successor = await repo.get_refresh_session(session, hash_token(issued.refresh_token))
    record.revoked_at = utcnow()
    record.replaced_by_id = successor.id if successor else None
    await session.flush()
    return issued


async def revoke_session(session: AsyncSession, refresh_token: str) -> None:
    """Log out one device. Unknown tokens are ignored."""
    record = await repo.get_refresh_session(session, hash_token(refresh_token))
    if record is not None and record.revoked_at is None:
        record.revoked_at = utcnow()
        await session.flush()


async def revoke_all_sessions(session: AsyncSession, user: User) -> int:
    return await repo.revoke_all_refresh_sessions(session, user_id=user.id)


async def switch_organization(
    session: AsyncSession, *, user: User, org_id: UUID, client: ClientInfo | None = None
) -> IssuedSession:
    membership = await repo.get_membership(session, user_id=user.id, org_id=org_id)
    if membership is None or not membership.is_active:
        raise PermissionDeniedError(
            "You are not a member of that organization.", code="not_a_member"
        )
    return await issue_session(session, user=user, org_id=org_id, client=client)


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------
async def start_password_reset(session: AsyncSession, email: str) -> tuple[User, str] | None:
    user = await repo.get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None
    token = await create_action_token(session, user=user, purpose=TokenPurpose.RESET_PASSWORD)
    return user, token


async def reset_password(session: AsyncSession, *, token: str, new_password: str) -> User:
    """Set a new password and sign out every other device."""
    user = await consume_action_token(session, token=token, purpose=TokenPurpose.RESET_PASSWORD)
    user.password_hash = hash_password(new_password)
    if not user.email_verified:
        # Reaching the reset link proves control of the address.
        user.email_verified_at = utcnow()
    await repo.revoke_all_refresh_sessions(session, user_id=user.id)
    await session.flush()
    logger.info("password_reset", user_id=str(user.id))
    return user


async def change_password(
    session: AsyncSession, *, user: User, current_password: str | None, new_password: str
) -> None:
    """Change a password from within the app.

    Accounts created through Google have no password yet and may set one
    without proving a previous value; everyone else must supply it.
    """
    if user.has_password:
        if not current_password:
            raise ValidationError("Enter your current password.", code="current_password_required")
        valid, _ = verify_and_upgrade_password(current_password, user.password_hash)
        if not valid:
            raise ValidationError("Current password is incorrect.", code="invalid_credentials")
    elif current_password:
        raise ConflictError("This account has no password set.", code="no_password_set")

    user.password_hash = hash_password(new_password)
    await session.flush()
    logger.info("password_changed", user_id=str(user.id))
