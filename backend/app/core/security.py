"""Password hashing, JWT access tokens, and opaque secret tokens.

Design notes:

* Passwords use Argon2id through ``pwdlib``, which also tells us when a stored
  hash was made with outdated parameters so it can be upgraded on login.
* Refresh tokens, email verification links and invitations are opaque random
  strings. Only their SHA-256 digest is stored, so a database leak cannot be
  replayed. SHA-256 is right here (unlike for passwords) because the input is
  256 bits of entropy, not a guessable secret.
* Access tokens are short-lived JWTs carrying the active organization and role,
  which avoids a membership lookup on every request. The 15-minute lifetime
  bounds how long a revoked membership keeps working.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.exceptions import AuthenticationError, TokenExpiredError
from app.core.ids import new_id
from app.core.time import utcnow

_password_hash = PasswordHash.recommended()

TOKEN_BYTES = 32
"""Entropy per opaque token. 256 bits — brute force is not a concern."""


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Verify a password.

    A ``None`` hash (a Google-only account) still runs a dummy verification so
    the response time does not reveal whether the address has a password set.
    """
    return verify_and_upgrade_password(password, password_hash)[0]


def verify_and_upgrade_password(
    password: str, password_hash: str | None
) -> tuple[bool, str | None]:
    """Verify a password and return a replacement hash when parameters changed.

    Returns ``(is_valid, new_hash_or_None)``. Callers that have a database
    session should persist ``new_hash`` so stored hashes keep up with the
    recommended Argon2 parameters.
    """
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False, None
    valid, updated = _password_hash.verify_and_update(password, password_hash)
    return bool(valid), updated


_DUMMY_HASH = _password_hash.hash("dummy-password-for-constant-time-comparison")


# --------------------------------------------------------------------------
# opaque tokens
# --------------------------------------------------------------------------
def generate_token() -> str:
    """A URL-safe secret to email or set in a cookie. Never stored as-is."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


# --------------------------------------------------------------------------
# access tokens
# --------------------------------------------------------------------------
class AccessTokenClaims(BaseModel):
    """Decoded contents of an access token."""

    sub: UUID
    """User id."""
    org: UUID | None = None
    """Active organization, absent before the user creates or joins one."""
    role: str | None = None
    jti: UUID
    typ: Literal["access"] = "access"
    exp: datetime
    iat: datetime


def create_access_token(
    *,
    user_id: UUID,
    org_id: UUID | None = None,
    role: str | None = None,
    expires_in: timedelta | None = None,
) -> tuple[str, datetime]:
    """Return the encoded token and the moment it expires."""
    now = utcnow()
    expires_at = now + (expires_in or timedelta(minutes=settings.access_token_ttl_minutes))
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "org": str(org_id) if org_id else None,
        "role": role,
        "jti": str(new_id()),
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at


def decode_access_token(token: str) -> AccessTokenClaims:
    """Decode and validate an access token.

    Raises :class:`TokenExpiredError` when it has merely expired, so the client
    knows to refresh rather than to log in again.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid access token.", code="invalid_token") from exc

    try:
        claims = AccessTokenClaims.model_validate(payload)
    except ValidationError as exc:
        raise AuthenticationError("Invalid access token.", code="invalid_token") from exc

    if claims.typ != "access":
        raise AuthenticationError("Invalid access token.", code="invalid_token")
    return claims
