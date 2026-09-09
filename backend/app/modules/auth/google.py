"""Google sign-in over OpenID Connect.

The authorization-code flow runs entirely server-side: the browser is
redirected to Google, Google redirects back with a code, and this service
exchanges it. The SPA never handles Google tokens.

CSRF protection is the ``state`` parameter, signed into a short-lived cookie
and compared on return. Replay protection is the ``nonce``, which is embedded
in the ID token by Google and checked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthenticationError, ExternalServiceError
from app.core.logging import get_logger
from app.core.time import utcnow
from app.modules.auth import repository as repo
from app.modules.users.models import OAuthAccount, User

logger = get_logger(__name__)

PROVIDER = "google"
DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

_oauth: OAuth | None = None


class GoogleNotConfiguredError(AppError):
    status_code = 503
    code = "google_sign_in_unavailable"
    message = "Google sign-in is not configured on this deployment."


def is_configured() -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def get_google_client() -> StarletteOAuth2App:
    """Lazily register the Google app so an unconfigured deployment still boots."""
    global _oauth
    if not is_configured():
        raise GoogleNotConfiguredError()

    if _oauth is None:
        oauth = OAuth()
        oauth.register(
            name=PROVIDER,
            client_id=settings.google_client_id,
            client_secret=(
                settings.google_client_secret.get_secret_value()
                if settings.google_client_secret
                else None
            ),
            server_metadata_url=DISCOVERY_URL,
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth

    client: StarletteOAuth2App = _oauth.create_client(PROVIDER)
    return client


@dataclass(frozen=True, slots=True)
class GoogleProfile:
    """The subset of Google's ID token claims we rely on."""

    subject: str
    email: str
    email_verified: bool
    full_name: str
    picture: str | None = None

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> GoogleProfile:
        subject = claims.get("sub")
        email = claims.get("email")
        if not subject or not email:
            raise AuthenticationError(
                "Google did not return an email address.", code="google_profile_incomplete"
            )
        return cls(
            subject=str(subject),
            email=str(email),
            email_verified=bool(claims.get("email_verified", False)),
            full_name=str(claims.get("name") or email.split("@")[0]),
            picture=claims.get("picture"),
        )


async def link_or_create_user(session: AsyncSession, profile: GoogleProfile) -> User:
    """Resolve a Google profile to a local account.

    Resolution order:

    1. An existing link on the provider's stable subject id.
    2. An account with the same address, but **only** when Google says the
       address is verified. Without that check, anyone able to create a Google
       account claiming an address could take over the local account.
    3. Otherwise a new, already-verified account with no password.
    """
    linked = await repo.get_oauth_account(
        session, provider=PROVIDER, provider_account_id=profile.subject
    )
    if linked is not None:
        user = await repo.get_user_by_id(session, linked.user_id)
        if user is None:  # pragma: no cover - cascade makes this unreachable
            raise AuthenticationError("Linked account no longer exists.")
        _refresh_profile(user, profile)
        await session.flush()
        return user

    existing = await repo.get_user_by_email(session, profile.email)
    if existing is not None:
        if not profile.email_verified:
            raise AuthenticationError(
                "That email address is already registered. Sign in with your password instead.",
                code="google_email_unverified",
            )
        _link(session, existing, profile)
        if not existing.email_verified:
            existing.email_verified_at = utcnow()
        _refresh_profile(existing, profile)
        await session.flush()
        logger.info("google_linked_existing_user", user_id=str(existing.id))
        return existing

    user = User(
        email=profile.email,
        password_hash=None,
        full_name=profile.full_name,
        avatar_url=profile.picture,
        email_verified_at=utcnow() if profile.email_verified else None,
    )
    session.add(user)
    await session.flush()
    _link(session, user, profile)
    await session.flush()
    logger.info("google_created_user", user_id=str(user.id))
    return user


def _link(session: AsyncSession, user: User, profile: GoogleProfile) -> None:
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider=PROVIDER,
            provider_account_id=profile.subject,
            email=profile.email,
            raw_profile={
                "sub": profile.subject,
                "email": profile.email,
                "email_verified": profile.email_verified,
                "name": profile.full_name,
                "picture": profile.picture,
            },
        )
    )


def _refresh_profile(user: User, profile: GoogleProfile) -> None:
    """Fill in details the local account is missing, without overwriting edits."""
    if not user.avatar_url and profile.picture:
        user.avatar_url = profile.picture
    if not user.full_name and profile.full_name:
        user.full_name = profile.full_name


async def exchange_code(client: StarletteOAuth2App, request: Any) -> GoogleProfile:
    """Complete the code exchange and return the verified profile."""
    try:
        token = await client.authorize_access_token(request)
    except Exception as exc:
        logger.warning("google_code_exchange_failed", error=str(exc))
        raise ExternalServiceError(
            "Could not complete Google sign-in.", code="google_exchange_failed"
        ) from exc

    claims = token.get("userinfo")
    if not claims:
        raise AuthenticationError("Google did not return a profile.", code="google_no_profile")
    return GoogleProfile.from_claims(dict(claims))
