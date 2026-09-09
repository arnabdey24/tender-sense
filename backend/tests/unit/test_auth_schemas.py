"""Validation rules on the authentication request bodies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    RegisterRequest,
    ResetPasswordRequest,
)


class TestRegisterRequest:
    def test_accepts_a_valid_registration(self) -> None:
        data = RegisterRequest(
            email="rahim@example.com", password="a-long-enough-password", full_name="Rahim Uddin"
        )

        assert data.email == "rahim@example.com"
        assert data.full_name == "Rahim Uddin"

    def test_rejects_a_password_below_the_minimum_length(self) -> None:
        too_short = "a" * (settings.password_min_length - 1)

        with pytest.raises(ValidationError, match="at least"):
            RegisterRequest(email="a@example.com", password=too_short, full_name="A")

    def test_rejects_an_absurdly_long_password(self) -> None:
        """Argon2 on a megabyte of input would be a cheap denial of service."""
        with pytest.raises(ValidationError, match="at most"):
            RegisterRequest(email="a@example.com", password="a" * 201, full_name="A")

    def test_rejects_a_whitespace_only_password(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            RegisterRequest(email="a@example.com", password=" " * 20, full_name="A")

    def test_rejects_a_malformed_email(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="a-long-password", full_name="A")

    def test_trims_surrounding_whitespace_from_the_name(self) -> None:
        data = RegisterRequest(
            email="a@example.com", password="a-long-password", full_name="  Fatima Khan  "
        )

        assert data.full_name == "Fatima Khan"

    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            RegisterRequest(email="a@example.com", password="a-long-password", full_name="   ")


class TestPasswordChangeRequests:
    def test_reset_enforces_the_same_password_policy(self) -> None:
        with pytest.raises(ValidationError, match="at least"):
            ResetPasswordRequest(token="t", password="short")

    def test_change_allows_omitting_the_current_password(self) -> None:
        """Accounts created through Google have no password to prove."""
        data = ChangePasswordRequest(new_password="a-brand-new-password")

        assert data.current_password is None

    def test_change_enforces_the_password_policy(self) -> None:
        with pytest.raises(ValidationError, match="at least"):
            ChangePasswordRequest(current_password="whatever", new_password="short")
