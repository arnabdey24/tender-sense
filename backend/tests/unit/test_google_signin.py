"""Google profile handling.

The account-takeover risk here is real: if an unverified Google address could
attach itself to an existing local account, anyone able to create a Google
account claiming someone's address would inherit their organizations.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import AuthenticationError
from app.modules.auth.google import GoogleProfile, _refresh_profile
from app.modules.users.models import User

CLAIMS = {
    "sub": "1093847561029384756",
    "email": "rahim@example.com",
    "email_verified": True,
    "name": "Rahim Uddin",
    "picture": "https://lh3.googleusercontent.com/a/photo",
}


class TestGoogleProfile:
    def test_reads_the_claims_we_depend_on(self) -> None:
        profile = GoogleProfile.from_claims(CLAIMS)

        assert profile.subject == "1093847561029384756"
        assert profile.email == "rahim@example.com"
        assert profile.email_verified is True
        assert profile.full_name == "Rahim Uddin"

    def test_records_an_unverified_address_as_unverified(self) -> None:
        profile = GoogleProfile.from_claims({**CLAIMS, "email_verified": False})

        assert profile.email_verified is False

    def test_treats_a_missing_verification_claim_as_unverified(self) -> None:
        claims = {key: value for key, value in CLAIMS.items() if key != "email_verified"}

        assert GoogleProfile.from_claims(claims).email_verified is False

    def test_falls_back_to_the_local_part_when_no_name_is_given(self) -> None:
        claims = {key: value for key, value in CLAIMS.items() if key != "name"}

        assert GoogleProfile.from_claims(claims).full_name == "rahim"

    def test_rejects_a_profile_without_a_subject(self) -> None:
        claims = {key: value for key, value in CLAIMS.items() if key != "sub"}

        with pytest.raises(AuthenticationError, match="email address"):
            GoogleProfile.from_claims(claims)

    def test_rejects_a_profile_without_an_email(self) -> None:
        claims = {key: value for key, value in CLAIMS.items() if key != "email"}

        with pytest.raises(AuthenticationError):
            GoogleProfile.from_claims(claims)


class TestProfileRefresh:
    def test_fills_in_a_missing_avatar(self) -> None:
        user = User(email="a@example.com", full_name="A", avatar_url=None)

        _refresh_profile(user, GoogleProfile.from_claims(CLAIMS))

        assert user.avatar_url == CLAIMS["picture"]

    def test_does_not_overwrite_an_avatar_the_user_chose(self) -> None:
        user = User(email="a@example.com", full_name="A", avatar_url="https://own.example/me.png")

        _refresh_profile(user, GoogleProfile.from_claims(CLAIMS))

        assert user.avatar_url == "https://own.example/me.png"

    def test_does_not_overwrite_an_existing_name(self) -> None:
        user = User(email="a@example.com", full_name="Preferred Name")

        _refresh_profile(user, GoogleProfile.from_claims(CLAIMS))

        assert user.full_name == "Preferred Name"
