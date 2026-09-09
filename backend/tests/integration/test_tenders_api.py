"""Browsing and searching the shared pool over HTTP.

Runs against whatever the seed script loaded, so it asserts on relationships
between results rather than exact totals.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.time import utcnow
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.tenders.models import Tender
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
    """A verified user; the pool needs a signed-in reader but no organization."""
    email = f"reader-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Pool Reader",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
        )
        session.add(user)
        await session.flush()
        issued = await issue_session(session, user=user)
        token = issued.response.access_token

    yield {"Authorization": f"Bearer {token}"}

    async with session_scope() as session:
        found = await session.scalar(select(User).where(User.email == email))
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        if found is not None:
            await session.delete(found)


async def seeded_count() -> int:
    async with session_scope() as session:
        return len((await session.execute(select(Tender.id))).all())


async def fetch(api: AsyncClient, headers: dict[str, str], **params: Any) -> dict[str, Any]:
    response = await api.get("/api/v1/tenders", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


class TestAccess:
    async def test_the_pool_requires_a_signed_in_user(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/tenders")).status_code == 401

    async def test_a_user_without_an_organization_can_browse(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The pool is shared, so it must not require an organization."""
        response = await api.get("/api/v1/tenders", headers=auth_headers)

        assert response.status_code == 200


class TestListing:
    async def test_results_are_paginated(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 5:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, page=1, page_size=5)

        assert len(body["items"]) == 5
        assert body["total"] >= 5
        assert body["page"] == 1

    async def test_the_second_page_returns_different_rows(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        first = await fetch(api, auth_headers, page=1, page_size=5)
        second = await fetch(api, auth_headers, page=2, page_size=5)

        assert {row["id"] for row in first["items"]}.isdisjoint(
            {row["id"] for row in second["items"]}
        )

    async def test_an_oversized_page_is_rejected(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await api.get(
            "/api/v1/tenders", headers=auth_headers, params={"page_size": 5000}
        )

        assert response.status_code == 422


class TestSearchAndFilters:
    async def test_free_text_search_narrows_the_results(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        everything = await fetch(api, auth_headers, page_size=1)
        matching = await fetch(api, auth_headers, q="network infrastructure", page_size=50)

        assert 0 < matching["total"] < everything["total"]
        assert any(
            "network" in row["title"].lower() or "network" in (row["summary"] or "").lower()
            for row in matching["items"]
        )

    async def test_search_matches_a_partial_word(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Users type fragments; exact-token matching alone would find nothing."""
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, q="infrastruct", page_size=50)

        assert body["total"] >= 1

    async def test_a_nonsense_query_returns_nothing(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        body = await fetch(api, auth_headers, q="zzqqxx-not-a-real-term", page_size=10)

        assert body["total"] == 0
        assert body["items"] == []

    async def test_filtering_by_category(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, category="works", page_size=50)

        assert body["total"] >= 1
        assert {row["procurement_category"] for row in body["items"]} == {"works"}

    async def test_filtering_by_source(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, source="wb", page_size=50)

        assert {row["source_code"] for row in body["items"]} == {"wb"}

    async def test_open_only_excludes_closed_and_expired_notices(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        everything = await fetch(api, auth_headers, page_size=1)
        open_only = await fetch(api, auth_headers, open_only=True, page_size=100)

        assert open_only["total"] < everything["total"]
        assert all(row["status"] == "open" for row in open_only["items"])
        assert all(
            row["days_to_deadline"] is None or row["days_to_deadline"] >= 0
            for row in open_only["items"]
        )

    async def test_deadline_window_filter(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, deadline_within_days=7, page_size=100)

        assert all(
            row["days_to_deadline"] is not None and row["days_to_deadline"] <= 7
            for row in body["items"]
        )


class TestOrdering:
    async def test_sorting_by_deadline_puts_the_soonest_first(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, sort="deadline_at", descending=False, page_size=20)

        deadlines = [row["deadline_at"] for row in body["items"] if row["deadline_at"]]
        assert deadlines == sorted(deadlines)

    async def test_notices_without_the_sort_value_come_last(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Otherwise a deadline sort leads with everything that has no deadline."""
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        body = await fetch(api, auth_headers, sort="deadline_at", descending=False, page_size=100)

        deadlines = [row["deadline_at"] for row in body["items"]]
        missing_positions = [i for i, value in enumerate(deadlines) if value is None]
        present_positions = [i for i, value in enumerate(deadlines) if value is not None]
        if missing_positions and present_positions:
            assert min(missing_positions) > max(present_positions)

    async def test_an_unknown_sort_field_is_rejected(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """The sort field reaches SQL, so only a known list may pass."""
        response = await api.get(
            "/api/v1/tenders", headers=auth_headers, params={"sort": "password_hash"}
        )

        assert response.status_code == 422


class TestDetailAndFacets:
    async def test_detail_returns_the_full_notice(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 1:
            pytest.skip("pool not seeded; run `make seed`")

        listed = await fetch(api, auth_headers, page_size=1)
        tender_id = listed["items"][0]["id"]

        response = await api.get(f"/api/v1/tenders/{tender_id}", headers=auth_headers)

        body = response.json()
        assert response.status_code == 200
        assert body["id"] == tender_id
        assert body["version"] >= 1
        assert "description" in body

    async def test_an_unknown_tender_is_a_clean_404(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await api.get(f"/api/v1/tenders/{uuid4()}", headers=auth_headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "tender_not_found"

    async def test_facets_count_the_same_set_as_the_list(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        listing = await fetch(api, auth_headers, page_size=1)
        response = await api.get("/api/v1/tenders/facets", headers=auth_headers)

        facets = response.json()
        assert response.status_code == 200
        assert facets["total"] == listing["total"]
        assert sum(facets["by_category"].values()) == listing["total"]

    async def test_facets_follow_the_active_filters(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        if await seeded_count() < 10:
            pytest.skip("pool not seeded; run `make seed`")

        response = await api.get(
            "/api/v1/tenders/facets", headers=auth_headers, params={"source": "wb"}
        )

        facets = response.json()
        assert set(facets["by_source"]) == {"wb"}

    async def test_sources_are_listed_with_their_health(
        self, api: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        response = await api.get("/api/v1/sources", headers=auth_headers)

        body = response.json()
        assert response.status_code == 200
        if body:
            assert {"code", "name", "health", "enabled"} <= set(body[0])
