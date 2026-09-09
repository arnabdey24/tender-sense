"""Password hashing, opaque tokens, and access-token encoding."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest
import time_machine

from app.core.config import settings
from app.core.exceptions import AuthenticationError, TokenExpiredError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_token,
    hash_password,
    hash_token,
    tokens_match,
    verify_and_upgrade_password,
    verify_password,
)


class TestPasswords:
    def test_hash_is_not_the_password(self) -> None:
        hashed = hash_password("correct horse battery staple")

        assert "correct horse battery staple" not in hashed
        assert hashed.startswith("$argon2")

    def test_same_password_hashes_differently_each_time(self) -> None:
        """A per-hash salt means identical passwords are not detectable."""
        assert hash_password("same-password") != hash_password("same-password")

    def test_correct_password_verifies(self) -> None:
        assert verify_password("s3cret-password", hash_password("s3cret-password"))

    def test_wrong_password_is_rejected(self) -> None:
        assert not verify_password("wrong-password", hash_password("s3cret-password"))

    def test_account_without_a_password_never_verifies(self) -> None:
        """Google-only accounts must not be loggable with any password."""
        assert not verify_password("anything at all", None)

    def test_upgrade_returns_no_new_hash_for_current_parameters(self) -> None:
        hashed = hash_password("s3cret-password")

        valid, updated = verify_and_upgrade_password("s3cret-password", hashed)

        assert valid is True
        assert updated is None


class TestOpaqueTokens:
    def test_generated_tokens_are_unique(self) -> None:
        assert len({generate_token() for _ in range(100)}) == 100

    def test_generated_tokens_are_url_safe(self) -> None:
        token = generate_token()

        assert token.replace("-", "").replace("_", "").isalnum()
        assert len(token) >= 40

    def test_hash_is_stable_and_hides_the_token(self) -> None:
        token = generate_token()

        digest = hash_token(token)

        assert digest == hash_token(token)
        assert token not in digest
        assert len(digest) == 64

    def test_match_accepts_the_original_and_rejects_others(self) -> None:
        token = generate_token()
        digest = hash_token(token)

        assert tokens_match(token, digest)
        assert not tokens_match(generate_token(), digest)


class TestAccessTokens:
    def test_round_trip_preserves_identity_and_org(self) -> None:
        user_id, org_id = uuid4(), uuid4()

        token, expires_at = create_access_token(user_id=user_id, org_id=org_id, role="admin")
        claims = decode_access_token(token)

        assert claims.sub == user_id
        assert claims.org == org_id
        assert claims.role == "admin"
        assert claims.exp.replace(microsecond=0) == expires_at.replace(microsecond=0)

    def test_token_without_an_org_is_valid(self) -> None:
        """Users have no organization between registering and onboarding."""
        token, _ = create_access_token(user_id=uuid4())

        claims = decode_access_token(token)

        assert claims.org is None
        assert claims.role is None

    def test_each_token_gets_a_unique_id(self) -> None:
        user_id = uuid4()

        first, _ = create_access_token(user_id=user_id)
        second, _ = create_access_token(user_id=user_id)

        assert decode_access_token(first).jti != decode_access_token(second).jti

    def test_expired_token_is_reported_as_expired(self) -> None:
        """The client must be able to tell 'refresh me' from 'log in again'."""
        with time_machine.travel("2026-09-09 10:00:00 +0000", tick=False):
            token, _ = create_access_token(user_id=uuid4(), expires_in=timedelta(minutes=15))

        with (
            time_machine.travel("2026-09-09 10:16:00 +0000", tick=False),
            pytest.raises(TokenExpiredError),
        ):
            decode_access_token(token)

    def test_token_signed_with_another_key_is_rejected(self) -> None:
        forged = jwt.encode(
            {"sub": str(uuid4()), "jti": str(uuid4()), "typ": "access", "iat": 0, "exp": 9e9},
            "an-attackers-key-long-enough-to-avoid-a-library-warning",
            algorithm="HS256",
        )

        with pytest.raises(AuthenticationError):
            decode_access_token(forged)

    def test_unsigned_token_is_rejected(self) -> None:
        """Guards against the alg=none downgrade attack."""
        forged = jwt.encode(
            {"sub": str(uuid4()), "jti": str(uuid4()), "typ": "access", "iat": 0, "exp": 9e9},
            key="",
            algorithm="none",
        )

        with pytest.raises(AuthenticationError):
            decode_access_token(forged)

    def test_refresh_token_shaped_jwt_is_rejected_as_access_token(self) -> None:
        wrong_type = jwt.encode(
            {"sub": str(uuid4()), "jti": str(uuid4()), "typ": "refresh", "iat": 0, "exp": 9e9},
            settings.secret_key.get_secret_value(),
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(AuthenticationError):
            decode_access_token(wrong_type)

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(AuthenticationError):
            decode_access_token("not-a-jwt")
