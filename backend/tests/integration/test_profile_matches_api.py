"""The profile and match APIs over HTTP, including the tenancy boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.ai.fake_client import FakeAIClient
from app.core.security import hash_password
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.jobs.tasks.matching import process_tender
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.profiles.models import CompanyProfile
from app.modules.tenders.models import ProcurementCategory, Tender, TenderSource
from app.modules.users.models import User


@dataclass
class Tenant:
    org: Organization
    headers: dict[str, str]
    email: str


@pytest.fixture
async def api() -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        yield client


async def make_tenant(*, role: OrgRole = OrgRole.ADMIN, name: str = "Meghna") -> Tenant:
    email = f"{name.lower()}-{uuid4().hex[:10]}@tsense-test.io"
    async with session_scope() as session:
        user = User(
            email=email,
            full_name=f"{name} Admin",
            password_hash=hash_password("a-perfectly-fine-password"),
            email_verified_at=utcnow(),
        )
        org = Organization(name=name, slug=f"{name.lower()}-{uuid4().hex[:8]}")
        session.add_all([user, org])
        await session.flush()
        session.add(
            Membership(org_id=org.id, user_id=user.id, role=role, status=MembershipStatus.ACTIVE)
        )
        await session.flush()
        issued = await issue_session(session, user=user, org_id=org.id)
        token = issued.response.access_token
        await session.refresh(org)
    return Tenant(org=org, headers={"Authorization": f"Bearer {token}"}, email=email)


async def drop_tenant(tenant: Tenant) -> None:
    async with session_scope() as session:
        await session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == tenant.email))
        await session.execute(delete(Organization).where(Organization.id == tenant.org.id))
        found = await session.scalar(select(User).where(User.email == tenant.email))
        if found is not None:
            await session.delete(found)


@pytest.fixture
async def tenant() -> AsyncIterator[Tenant]:
    created = await make_tenant()
    yield created
    await drop_tenant(created)


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"t-{uuid4().hex[:8]}", name="Test", adapter_key="manual", base_url=""
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


async def make_tender(source: TenderSource, *, title: str, summary: str) -> Tender:
    record = Tender(
        source_id=source.id,
        external_id=uuid4().hex,
        canonical_url="https://example.invalid/n/1",
        title=title,
        summary=summary,
        procuring_entity="Bangladesh Bank",
        country="BD",
        procurement_category=ProcurementCategory.GOODS,
        content_hash=uuid4().hex,
        deadline_at=utcnow() + timedelta(days=30),
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    return record


class TestProfileAccess:
    async def test_it_requires_an_organization(self, api: AsyncClient) -> None:
        assert (await api.get("/api/v1/profile")).status_code == 401

    async def test_a_member_can_read_but_not_write(self, api: AsyncClient) -> None:
        member = await make_tenant(role=OrgRole.MEMBER, name="Padma")
        try:
            read = await api.get("/api/v1/profile", headers=member.headers)
            write = await api.put(
                "/api/v1/profile", headers=member.headers, json={"overview": "nope"}
            )

            assert read.status_code == 200
            assert write.status_code == 403
            assert write.json()["error"]["code"] == "admin_required"
        finally:
            await drop_tenant(member)


class TestProfile:
    async def test_reading_creates_an_empty_profile(self, api: AsyncClient, tenant: Tenant) -> None:
        """So the wizard and settings can both just PUT, with no create step."""
        response = await api.get("/api/v1/profile", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert body["completeness"] == 0
        assert body["services"] == []

    async def test_updating_bumps_the_version(self, api: AsyncClient, tenant: Tenant) -> None:
        """The version is what invalidates every stored match's fingerprint."""
        before = (await api.get("/api/v1/profile", headers=tenant.headers)).json()

        after = await api.put(
            "/api/v1/profile",
            headers=tenant.headers,
            json={"overview": "Systems integration and networking.", "sectors": ["it"]},
        )

        assert after.status_code == 200
        assert after.json()["version"] > before["version"]

    async def test_completeness_rises_as_sections_are_filled(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        empty = (await api.get("/api/v1/profile/completeness", headers=tenant.headers)).json()

        await api.put(
            "/api/v1/profile",
            headers=tenant.headers,
            json={"overview": "Systems integration.", "sectors": ["it"], "geographies": ["BD"]},
        )
        await api.post(
            "/api/v1/profile/services",
            headers=tenant.headers,
            json={"name": "Network integration"},
        )
        filled = (await api.get("/api/v1/profile/completeness", headers=tenant.headers)).json()

        assert empty["score"] == 0
        assert filled["score"] > empty["score"]
        assert filled["next_step"]

    async def test_geographies_are_normalised_to_iso_codes(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.put(
            "/api/v1/profile",
            headers=tenant.headers,
            json={"geographies": ["bd", "BD", "np", "not-a-code"]},
        )

        assert response.json()["geographies"] == ["BD", "NP"]

    async def test_services_can_be_added_updated_and_removed(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        created = await api.post(
            "/api/v1/profile/services",
            headers=tenant.headers,
            json={"name": "Network integration", "sector": "it"},
        )
        service_id = created.json()["id"]

        updated = await api.put(
            f"/api/v1/profile/services/{service_id}",
            headers=tenant.headers,
            json={"name": "Managed networking", "sector": "it"},
        )
        removed = await api.delete(f"/api/v1/profile/services/{service_id}", headers=tenant.headers)
        listed = (await api.get("/api/v1/profile", headers=tenant.headers)).json()

        assert created.status_code == 201
        assert updated.json()["name"] == "Managed networking"
        assert removed.status_code == 204
        assert listed["services"] == []

    async def test_a_certification_is_stored_under_a_canonical_code(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """So a rule asking about ISO 9001 matches however it was typed."""
        response = await api.post(
            "/api/v1/profile/certifications",
            headers=tenant.headers,
            json={"label": "iso-9001:2015"},
        )

        assert response.json()["code"] == "ISO9001"

    async def test_re_adding_a_certification_updates_rather_than_duplicates(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """A duplicate would be double-counted by the eligibility engine."""
        await api.post(
            "/api/v1/profile/certifications",
            headers=tenant.headers,
            json={"label": "ISO 9001"},
        )
        await api.post(
            "/api/v1/profile/certifications",
            headers=tenant.headers,
            json={"label": "ISO 9001:2015"},
        )

        listed = (await api.get("/api/v1/profile", headers=tenant.headers)).json()
        assert len(listed["certifications"]) == 1
        assert listed["certifications"][0]["label"] == "ISO 9001:2015"

    async def test_another_tenants_service_cannot_be_reached(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """The profile id comes from the token, so a guessed id must 404."""
        other = await make_tenant(name="Jamuna")
        try:
            created = await api.post(
                "/api/v1/profile/services",
                headers=other.headers,
                json={"name": "Their service"},
            )
            service_id = created.json()["id"]

            response = await api.delete(
                f"/api/v1/profile/services/{service_id}", headers=tenant.headers
            )

            assert response.status_code == 404
        finally:
            await drop_tenant(other)

    async def test_taxonomies_are_served_from_the_backend(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """So a form cannot offer a sector the matcher does not understand."""
        response = await api.get("/api/v1/taxonomies", headers=tenant.headers)

        body = response.json()
        assert {"value": "it", "label": "It"} in body["sectors"]
        assert "ISO 9001" in body["common_certifications"]
        # Services feed the matcher directly, so the form suggests them too —
        # a misspelled service is a facet that scores against nothing.
        assert "Network integration" in body["common_services"]


class TestMatches:
    @pytest.fixture
    async def matched(self, tenant: Tenant, source: TenderSource) -> dict[str, Any]:
        """A profile with one strong and one weak match already scored."""
        async with session_scope() as session:
            profile = CompanyProfile(
                org_id=tenant.org.id,
                overview="Enterprise network infrastructure and data centre integration.",
                sectors=["it"],
                geographies=["BD"],
            )
            session.add(profile)
            await session.flush()

        good = await make_tender(
            source,
            title="Supply of enterprise network switches",
            summary="Core switches, routers and structured cabling for a data centre.",
        )
        bad = await make_tender(
            source,
            title="Printing of primary school textbooks",
            summary="Offset printing and binding for rural schools.",
        )
        ctx = {"ai_client": FakeAIClient(dims=768)}
        await process_tender(ctx, str(good.id))
        await process_tender(ctx, str(bad.id))
        return {"good": good, "bad": bad}

    async def test_the_feed_leads_with_the_best_fit(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        response = await api.get("/api/v1/matches", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert body["total"] >= 2
        similarities = [row["similarity"] for row in body["items"]]
        assert similarities == sorted(similarities, reverse=True)

    async def test_every_row_carries_enough_of_the_notice_to_render(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        body = (await api.get("/api/v1/matches", headers=tenant.headers)).json()

        row = body["items"][0]
        assert row["tender"]["title"]
        assert row["explanation_text"]
        assert row["grade"] in {"S", "A", "B", "C"}

    async def test_a_row_carries_this_org_s_own_decision(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        """Distinct from ``recommendation``, which is what the matcher thinks.

        Without it the Bid button on a feed row wrote a record the row then
        rendered no differently, so pressing it looked like it had done
        nothing, and the same notice kept asking to be triaged.
        """
        good = matched["good"]
        undecided = (await api.get("/api/v1/matches", headers=tenant.headers)).json()
        assert all(row["decision"] is None for row in undecided["items"])

        await api.put(
            f"/api/v1/tenders/{good.id}/decision",
            headers=tenant.headers,
            json={"decision": "skip", "note": "Buyer is on hold"},
        )

        body = (await api.get("/api/v1/matches", headers=tenant.headers)).json()

        rows = {row["tender_id"]: row for row in body["items"]}
        assert rows[str(good.id)]["decision"] == "skip"
        assert rows[str(matched["bad"].id)]["decision"] is None
        # One row per match still: the outer join must not multiply them.
        assert len(body["items"]) == len(rows)

    async def test_a_decided_match_reaches_the_pipeline_with_its_grade(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        good = matched["good"]
        await api.put(
            f"/api/v1/tenders/{good.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid"},
        )

        listed = (await api.get("/api/v1/decisions", headers=tenant.headers)).json()

        row = next(d for d in listed["items"] if d["tender_id"] == str(good.id))
        assert row["verdict"] is not None
        assert row["verdict"]["grade"] in {"S", "A", "B", "C"}
        assert 0.0 <= row["verdict"]["similarity"] <= 1.0

    async def test_filtering_by_grade(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        response = await api.get("/api/v1/matches", headers=tenant.headers, params={"grade": "C"})

        assert {row["grade"] for row in response.json()["items"]} <= {"C"}

    async def test_stats_count_the_same_set_as_the_feed(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        feed = (await api.get("/api/v1/matches", headers=tenant.headers)).json()
        stats = (await api.get("/api/v1/matches/stats", headers=tenant.headers)).json()

        assert stats["total"] == feed["total"]
        assert sum(stats["by_grade"].values()) == feed["total"]

    async def test_one_match_carries_its_provenance(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        """ "Graded A" is not defensible; "graded A against profile v3" is."""
        response = await api.get(f"/api/v1/matches/{matched['good'].id}", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert body["profile_version"] >= 1
        assert body["embedding_model"]
        assert body["thresholds_version"] >= 1

    async def test_an_unmatched_tender_is_a_clean_404(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.get(f"/api/v1/matches/{uuid4()}", headers=tenant.headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "match_not_found"

    async def test_one_tenant_cannot_see_anothers_verdict(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        """The pool is shared; the grade, reasoning and decisions are not."""
        other = await make_tenant(name="Jamuna")
        try:
            response = await api.get(f"/api/v1/matches/{matched['good'].id}", headers=other.headers)
            feed = await api.get("/api/v1/matches", headers=other.headers)

            assert response.status_code == 404
            assert feed.json()["total"] == 0
        finally:
            await drop_tenant(other)

    async def test_the_pipeline_view_leads_with_the_soonest_deadline(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        response = await api.get("/api/v1/pipeline", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        deadlines = [
            row["tender"]["deadline_at"] for row in body["items"] if row["tender"]["deadline_at"]
        ]
        assert deadlines == sorted(deadlines)

    async def test_the_shortlist_is_narrower_than_the_feed(
        self, api: AsyncClient, tenant: Tenant, matched: dict[str, Any]
    ) -> None:
        """The point of a shortlist is that it is short."""
        feed = (await api.get("/api/v1/matches", headers=tenant.headers)).json()
        today = (await api.get("/api/v1/matches/today", headers=tenant.headers)).json()

        assert today["total"] <= feed["total"]
        assert {row["grade"] for row in today["items"]} <= {"S", "A"}
