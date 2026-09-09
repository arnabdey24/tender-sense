"""Superuser admin surface: source registration and manual tender entry."""

from __future__ import annotations

import json
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
from app.modules.tenders.models import Tender, TenderSource
from app.modules.users.models import User


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def _make_user(*, superuser: bool) -> tuple[str, dict[str, str]]:
    email = f"admin-{uuid4().hex[:12]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name="Admin Tester",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
            is_superuser=superuser,
        )
        session.add(user)
        await session.flush()
        issued = await issue_session(session, user=user)
        token = issued.response.access_token
    return email, {"Authorization": f"Bearer {token}"}


async def _cleanup(email: str, source_codes: list[str]) -> None:
    async with session_scope() as session:
        for code in source_codes:
            await session.execute(delete(TenderSource).where(TenderSource.code == code))
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email))
        found = await session.scalar(select(User).where(User.email == email))
        if found is not None:
            await session.delete(found)


@pytest.fixture
async def superuser_headers() -> AsyncIterator[dict[str, str]]:
    email, headers = await _make_user(superuser=True)
    yield headers
    await _cleanup(email, [])


class TestAccess:
    async def test_non_superuser_is_forbidden(self, api: AsyncClient) -> None:
        email, headers = await _make_user(superuser=False)
        try:
            response = await api.get("/api/v1/admin/sources", headers=headers)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "staff_required"
        finally:
            await _cleanup(email, [])

    async def test_anonymous_is_unauthenticated(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/admin/sources")).status_code == 401


class TestSources:
    async def test_create_read_update_delete(
        self, api: AsyncClient, superuser_headers: dict[str, str]
    ) -> None:
        code = f"test-{uuid4().hex[:8]}"
        try:
            created = await api.post(
                "/api/v1/admin/sources",
                headers=superuser_headers,
                json={
                    "code": code,
                    "name": "Test Portal",
                    "adapter_key": "worldbank",
                    "base_url": "https://example.invalid",
                    "config": {"rows": 50},
                },
            )
            assert created.status_code == 201, created.text
            source_id = created.json()["id"]
            assert created.json()["config"] == {"rows": 50}

            patched = await api.patch(
                f"/api/v1/admin/sources/{source_id}",
                headers=superuser_headers,
                json={"enabled": False},
            )
            assert patched.status_code == 200
            assert patched.json()["enabled"] is False

            listed = await api.get("/api/v1/admin/sources", headers=superuser_headers)
            assert any(s["code"] == code for s in listed.json())

            deleted = await api.delete(
                f"/api/v1/admin/sources/{source_id}", headers=superuser_headers
            )
            assert deleted.status_code == 204
        finally:
            await _cleanup("noone@tsense-test.io", [code])

    async def test_unknown_adapter_is_rejected(
        self, api: AsyncClient, superuser_headers: dict[str, str]
    ) -> None:
        response = await api.post(
            "/api/v1/admin/sources",
            headers=superuser_headers,
            json={"code": f"x-{uuid4().hex[:6]}", "name": "X", "adapter_key": "nope"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unknown_adapter"

    async def test_duplicate_code_is_a_conflict(
        self, api: AsyncClient, superuser_headers: dict[str, str]
    ) -> None:
        code = f"test-{uuid4().hex[:8]}"
        body = {"code": code, "name": "Dup", "adapter_key": "manual"}
        try:
            first = await api.post("/api/v1/admin/sources", headers=superuser_headers, json=body)
            assert first.status_code == 201
            second = await api.post("/api/v1/admin/sources", headers=superuser_headers, json=body)
            assert second.status_code == 409
        finally:
            await _cleanup("noone@tsense-test.io", [code])


class TestManualTenders:
    async def test_add_one_notice_by_hand(
        self, api: AsyncClient, superuser_headers: dict[str, str]
    ) -> None:
        code = f"test-{uuid4().hex[:8]}"
        ext = f"manual-{uuid4().hex[:8]}"
        try:
            await api.post(
                "/api/v1/admin/sources",
                headers=superuser_headers,
                json={"code": code, "name": "Manual", "adapter_key": "manual"},
            )
            response = await api.post(
                "/api/v1/admin/tenders",
                headers=superuser_headers,
                json={
                    "source_code": code,
                    "external_id": ext,
                    "canonical_url": "https://example.invalid/n/1",
                    "title": "Supply of laptops for a training centre",
                    "country": "BD",
                    "procurement_category": "goods",
                },
            )
            assert response.status_code == 201, response.text
            assert response.json()["outcome"] == "created"

            async with session_scope() as session:
                tender = await session.scalar(select(Tender).where(Tender.external_id == ext))
                assert tender is not None
                await session.delete(tender)
        finally:
            await _cleanup("noone@tsense-test.io", [code])

    async def test_bulk_json_import(
        self, api: AsyncClient, superuser_headers: dict[str, str]
    ) -> None:
        code = f"test-{uuid4().hex[:8]}"
        ext = f"imp-{uuid4().hex[:8]}"
        try:
            await api.post(
                "/api/v1/admin/sources",
                headers=superuser_headers,
                json={"code": code, "name": "Import", "adapter_key": "manual"},
            )
            payload = [
                {
                    "external_id": ext,
                    "canonical_url": "https://example.invalid/n/2",
                    "title": "Consulting services for an MIS rollout",
                    "procurement_category": "consulting",
                }
            ]
            response = await api.post(
                f"/api/v1/admin/tenders/import?source_code={code}",
                headers={**superuser_headers, "content-type": "application/json"},
                content=json.dumps(payload),
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["created"] == 1
            assert body["failed"] == 0

            async with session_scope() as session:
                tender = await session.scalar(select(Tender).where(Tender.external_id == ext))
                assert tender is not None
                await session.delete(tender)
        finally:
            await _cleanup("noone@tsense-test.io", [code])
