"""Editing your own profile."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.users.models import User


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
async def auth_headers() -> AsyncIterator[dict[str, str]]:
    email = f"profile-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Original Name",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
        )
        session.add(user)
        await session.flush()
        issued = await issue_session(session, user=user)
        token = issued.response.access_token

    yield {"Authorization": f"Bearer {token}"}

    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        found = await session.scalar(select(User).where(User.email == email))
        if found is not None:
            await session.delete(found)


class TestUpdateProfile:
    async def test_it_requires_a_signed_in_user(self, api: AsyncClient) -> None:
        response = await api.patch("/api/v1/users/me", json={"full_name": "X"})

        assert response.status_code == 401

    async def test_renaming_yourself(self, api: AsyncClient, auth_headers: dict[str, str]) -> None:
        response = await api.patch(
            "/api/v1/users/me", headers=auth_headers, json={"full_name": "Renamed Person"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["full_name"] == "Renamed Person"

    async def test_an_unset_field_is_left_alone(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A patch that omits the avatar must not blank it."""
        await api.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"avatar_url": "https://example.com/a.png"},
        )

        response = await api.patch(
            "/api/v1/users/me", headers=auth_headers, json={"full_name": "Still Here"}
        )

        body = response.json()
        assert body["full_name"] == "Still Here"
        assert body["avatar_url"] == "https://example.com/a.png"

    async def test_clearing_the_avatar(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        await api.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"avatar_url": "https://example.com/a.png"},
        )

        response = await api.patch(
            "/api/v1/users/me", headers=auth_headers, json={"avatar_url": None}
        )

        assert response.json()["avatar_url"] is None

    async def test_a_junk_avatar_url_is_rejected(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await api.patch(
            "/api/v1/users/me", headers=auth_headers, json={"avatar_url": "javascript:alert(1)"}
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_an_empty_name_is_rejected(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await api.patch("/api/v1/users/me", headers=auth_headers, json={"full_name": ""})

        assert response.status_code == 422

    async def test_the_email_address_cannot_be_changed_here(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Moving an account to a new address has to re-run verification."""
        response = await api.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"full_name": "Nice Try", "email": "someone-else@tsense-test.io"},
        )

        assert response.status_code == 200
        assert response.json()["email"] != "someone-else@tsense-test.io"
