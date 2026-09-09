"""Linking Google identities to local accounts, against the real database."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.exceptions import AuthenticationError
from app.core.security import hash_password
from app.db.session import session_scope
from app.modules.auth.google import GoogleProfile, link_or_create_user
from app.modules.users.models import OAuthAccount, User


def unique_email(prefix: str = "google") -> str:
    return f"{prefix}-{uuid4().hex[:12]}@tsense-test.io"


def profile_for(email: str, *, verified: bool = True, subject: str | None = None) -> GoogleProfile:
    return GoogleProfile(
        subject=subject or uuid4().hex,
        email=email,
        email_verified=verified,
        full_name="Google User",
        picture="https://lh3.googleusercontent.com/a/photo",
    )


async def _cleanup(email: str) -> None:
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.email == email))
        if user is not None:
            await session.execute(delete(OAuthAccount).where(OAuthAccount.user_id == user.id))
            await session.delete(user)


async def test_first_sign_in_creates_a_verified_account_without_a_password() -> None:
    email = unique_email()
    try:
        async with session_scope() as session:
            user = await link_or_create_user(session, profile_for(email))

            assert user.email == email
            assert user.email_verified is True
            assert user.has_password is False
    finally:
        await _cleanup(email)


async def test_signing_in_again_reuses_the_same_account() -> None:
    email = unique_email()
    profile = profile_for(email)
    try:
        async with session_scope() as session:
            first = await link_or_create_user(session, profile)
            first_id = first.id
        async with session_scope() as session:
            second = await link_or_create_user(session, profile)

            assert second.id == first_id
    finally:
        await _cleanup(email)


async def test_a_changed_google_address_still_resolves_by_subject() -> None:
    """Google's `sub` is the stable identifier; the address can change."""
    email = unique_email()
    profile = profile_for(email)
    try:
        async with session_scope() as session:
            original = await link_or_create_user(session, profile)
            original_id = original.id
        async with session_scope() as session:
            renamed = GoogleProfile(
                subject=profile.subject,
                email=unique_email("renamed"),
                email_verified=True,
                full_name="Google User",
            )
            resolved = await link_or_create_user(session, renamed)

            assert resolved.id == original_id
    finally:
        await _cleanup(email)


async def test_a_verified_google_address_links_to_an_existing_password_account() -> None:
    email = unique_email()
    try:
        async with session_scope() as session:
            session.add(
                User(email=email, full_name="Existing", password_hash=hash_password("a-password"))
            )
        async with session_scope() as session:
            user = await link_or_create_user(session, profile_for(email, verified=True))

            assert user.email == email
            assert user.has_password is True, "linking must not remove the password"
            assert user.email_verified is True
    finally:
        await _cleanup(email)


async def test_an_unverified_google_address_cannot_claim_an_existing_account() -> None:
    """The account-takeover guard: without Google's verification, no linking."""
    email = unique_email()
    try:
        async with session_scope() as session:
            session.add(
                User(email=email, full_name="Existing", password_hash=hash_password("a-password"))
            )

        with pytest.raises(AuthenticationError) as exc:
            async with session_scope() as session:
                await link_or_create_user(session, profile_for(email, verified=False))

        assert exc.value.code == "google_email_unverified"
    finally:
        await _cleanup(email)


async def test_linking_records_the_provider_account() -> None:
    email = unique_email()
    profile = profile_for(email)
    try:
        async with session_scope() as session:
            user = await link_or_create_user(session, profile)
            user_id = user.id

        async with session_scope() as session:
            account = await session.scalar(
                select(OAuthAccount).where(OAuthAccount.user_id == user_id)
            )

            assert account is not None
            assert account.provider == "google"
            assert account.provider_account_id == profile.subject
    finally:
        await _cleanup(email)
