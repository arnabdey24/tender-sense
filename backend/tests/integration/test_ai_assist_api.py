"""The two form-filling endpoints, over HTTP.

The property worth pinning here is that both work for a signed-in user with
**no organization**. Research exists to fill in the organization form, so a
version of it that needs an organization to already exist would be useless on
the only screen that wants it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.ai import set_ai_client
from app.ai.fake_client import FakeAIClient
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


@pytest.fixture(autouse=True)
def _fake_ai() -> AsyncIterator[None]:
    set_ai_client(FakeAIClient())
    yield
    set_ai_client(None)


@pytest.fixture
async def orgless_headers() -> AsyncIterator[dict[str, str]]:
    """A verified account that has not created an organization yet.

    Deliberately org-less: this is the exact state of the person on the
    onboarding screen, which is where the research button lives.
    """
    email = f"aiassist-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Onboarding Person",
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


class TestResearchingACompany:
    async def test_it_requires_a_signed_in_user(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/ai/research-company", json={"url": "https://acme.com"})

        assert response.status_code == 401

    async def test_it_works_before_an_organization_exists(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/ai/research-company",
            headers=orgless_headers,
            json={"url": "acme-builders.com.bd"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["draft"]["reachable"] is True
        assert body["draft"]["company_name"]
        assert body["draft"]["overview"]
        # Normalised on the way in, so the form can show what was actually read.
        assert body["retrieved_url"] == "https://acme-builders.com.bd"

    async def test_a_site_that_cannot_be_read_is_an_error_not_a_guess(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/ai/research-company",
            headers=orgless_headers,
            json={"url": "https://does-not-exist-9f3a2b.example"},
        )

        assert response.status_code >= 400
        assert "draft" not in response.json()

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "http://localhost:8000", "nope"])
    async def test_an_address_that_is_not_a_website_is_rejected(
        self, api: AsyncClient, orgless_headers: dict[str, str], url: str
    ) -> None:
        response = await api.post(
            "/api/v1/ai/research-company", headers=orgless_headers, json={"url": url}
        )

        assert response.status_code == 422

    async def test_it_saves_nothing(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        """Still org-less afterwards: a draft is a draft."""
        await api.post(
            "/api/v1/ai/research-company",
            headers=orgless_headers,
            json={"url": "https://acme.com"},
        )

        me = await api.get("/api/v1/auth/me", headers=orgless_headers)

        assert me.json()["memberships"] == []


class TestImprovingText:
    async def test_it_requires_a_signed_in_user(self, api: AsyncClient) -> None:
        response = await api.post(
            "/api/v1/ai/improve-text", json={"field": "overview", "text": "hello"}
        )

        assert response.status_code == 401

    async def test_it_returns_a_rewrite(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/ai/improve-text",
            headers=orgless_headers,
            json={"field": "overview", "text": "we build roads and bridges"},
        )

        assert response.status_code == 200, response.text
        assert response.json()["text"]

    async def test_an_unknown_field_is_rejected(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/ai/improve-text",
            headers=orgless_headers,
            json={"field": "salary", "text": "hello"},
        )

        assert response.status_code == 422

    async def test_an_empty_draft_is_rejected_before_it_reaches_the_model(
        self, api: AsyncClient, orgless_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/ai/improve-text",
            headers=orgless_headers,
            json={"field": "overview", "text": ""},
        )

        assert response.status_code == 422
