"""The rules API and the decisions trail over HTTP."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import hash_password
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.modules.auth.service import issue_session
from app.modules.notifications.models import EmailOutbox
from app.modules.orgs.models import Membership, MembershipStatus, Organization, OrgRole
from app.modules.tenders.models import ProcurementCategory, Tender, TenderSource
from app.modules.users.models import User

TURNOVER_RULE = {
    "id": "r_turnover",
    "attribute": "min_annual_turnover",
    "operator": "lte",
    "value": {"source": "profile", "field": "annual_turnover"},
    "severity": "hard",
    "on_missing": "verify",
}


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
async def tender() -> AsyncIterator[Tender]:
    source = TenderSource(
        code=f"t-{uuid4().hex[:8]}", name="Test", adapter_key="manual", base_url=""
    )
    record = Tender(
        external_id=uuid4().hex,
        canonical_url="https://example.invalid/n/1",
        title="Supply of enterprise network switches",
        procurement_category=ProcurementCategory.GOODS,
        content_hash=uuid4().hex,
        deadline_at=utcnow() + timedelta(days=30),
    )
    async with session_scope() as session:
        session.add(source)
        await session.flush()
        record.source_id = source.id
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == source.id))


def rule_set_body(rules: list[dict[str, Any]], note: str | None = None) -> dict[str, Any]:
    return {
        "name": "Bidding criteria",
        "note": note,
        "definition": {"schema_version": 1, "combinator": "all", "rules": rules},
    }


class TestCatalogue:
    async def test_it_lists_attributes_operators_and_presets(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.get("/api/v1/rules/catalogue", headers=tenant.headers)

        body = response.json()
        assert response.status_code == 200
        assert any(a["key"] == "min_annual_turnover" for a in body["attributes"])
        assert any(p["key"] == "turnover_within_capacity" for p in body["presets"])
        assert set(body["on_missing_options"]) == {"verify", "pass", "fail"}

    async def test_each_attribute_advertises_only_operators_it_accepts(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """The builder reads this, so an unusable pairing must never appear."""
        body = (await api.get("/api/v1/rules/catalogue", headers=tenant.headers)).json()

        boolean = next(a for a in body["attributes"] if a["key"] == "jv_allowed")
        assert boolean["operators"] == ["eq"]

    async def test_the_schema_is_served_for_client_side_validation(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.get("/api/v1/rules/schema", headers=tenant.headers)

        assert response.status_code == 200
        assert "rules" in response.json()["properties"]


class TestValidation:
    async def test_a_valid_draft_passes(self, api: AsyncClient, tenant: Tenant) -> None:
        response = await api.post(
            "/api/v1/rules/validate",
            headers=tenant.headers,
            json={"schema_version": 1, "combinator": "all", "rules": [TURNOVER_RULE]},
        )

        assert response.json() == {"valid": True, "errors": []}

    async def test_errors_name_the_offending_rule(self, api: AsyncClient, tenant: Tenant) -> None:
        """So the builder can mark the row instead of the whole form."""
        response = await api.post(
            "/api/v1/rules/validate",
            headers=tenant.headers,
            json={
                "schema_version": 1,
                "combinator": "all",
                "rules": [{**TURNOVER_RULE, "id": "r_bad", "operator": "contains_any"}],
            },
        )

        body = response.json()
        assert body["valid"] is False
        assert body["errors"][0]["rule_id"] == "r_bad"
        assert "does not support" in body["errors"][0]["message"]


class TestRuleSetVersions:
    async def test_saving_writes_a_new_version_each_time(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        """Versions are immutable: a match records the one that graded it."""
        first = await api.put(
            "/api/v1/rule-sets/current", headers=tenant.headers, json=rule_set_body([])
        )
        second = await api.put(
            "/api/v1/rule-sets/current",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE], note="added turnover"),
        )

        assert first.json()["version_number"] == 1
        assert second.json()["version_number"] == 2

        versions = (
            await api.get("/api/v1/rule-sets/current/versions", headers=tenant.headers)
        ).json()
        assert [v["version_number"] for v in versions] == [2, 1]
        assert versions[0]["note"] == "added turnover"

    async def test_the_current_set_reflects_the_latest_save(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        await api.put(
            "/api/v1/rule-sets/current",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE]),
        )

        body = (await api.get("/api/v1/rule-sets/current", headers=tenant.headers)).json()

        assert [r["id"] for r in body["definition"]["rules"]] == ["r_turnover"]

    async def test_rolling_back_restores_an_earlier_version(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        await api.put("/api/v1/rule-sets/current", headers=tenant.headers, json=rule_set_body([]))
        await api.put(
            "/api/v1/rule-sets/current",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE]),
        )
        versions = (
            await api.get("/api/v1/rule-sets/current/versions", headers=tenant.headers)
        ).json()
        first_id = next(v["id"] for v in versions if v["version_number"] == 1)

        await api.post(
            f"/api/v1/rule-sets/current/versions/{first_id}/activate", headers=tenant.headers
        )

        body = (await api.get("/api/v1/rule-sets/current", headers=tenant.headers)).json()
        assert body["definition"]["rules"] == []

    async def test_an_invalid_draft_is_rejected_before_it_is_stored(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.put(
            "/api/v1/rule-sets/current",
            headers=tenant.headers,
            json=rule_set_body([{**TURNOVER_RULE, "attribute": "not_a_thing"}]),
        )

        assert response.status_code == 422

    async def test_a_member_cannot_change_the_rules(self, api: AsyncClient) -> None:
        """A rule decides what the whole organization is shown."""
        member = await make_tenant(role=OrgRole.MEMBER, name="Padma")
        try:
            read = await api.get("/api/v1/rule-sets/current", headers=member.headers)
            write = await api.put(
                "/api/v1/rule-sets/current", headers=member.headers, json=rule_set_body([])
            )

            assert read.status_code == 200
            assert write.status_code == 403
        finally:
            await drop_tenant(member)

    async def test_one_tenant_cannot_see_anothers_criteria(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        other = await make_tenant(name="Jamuna")
        try:
            await api.put(
                "/api/v1/rule-sets/current",
                headers=tenant.headers,
                json=rule_set_body([TURNOVER_RULE]),
            )

            body = (await api.get("/api/v1/rule-sets/current", headers=other.headers)).json()

            assert body["definition"]["rules"] == []
        finally:
            await drop_tenant(other)


class TestPreview:
    async def test_a_draft_reports_what_it_would_do(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        response = await api.post(
            "/api/v1/rule-sets/preview",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE]),
            params={"limit": 50},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["counts"]["evaluated"] > 0
        # Per-rule counts are the useful part: they name the line to relax.
        assert "r_turnover" in body["per_rule"]

    async def test_an_empty_draft_leaves_everything_eligible(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        body = (
            await api.post(
                "/api/v1/rule-sets/preview",
                headers=tenant.headers,
                json=rule_set_body([]),
                params={"limit": 50},
            )
        ).json()

        assert body["counts"]["ineligible"] == 0
        assert body["counts"]["needs_verification"] == 0

    async def test_preview_stores_nothing(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        """Trying a draft must not change the criteria in force."""
        await api.post(
            "/api/v1/rule-sets/preview",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE]),
        )

        body = (await api.get("/api/v1/rule-sets/current", headers=tenant.headers)).json()
        assert body["definition"]["rules"] == []

    async def test_testing_one_tender_explains_it_rule_by_rule(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        response = await api.post(
            f"/api/v1/rule-sets/test/{tender.id}",
            headers=tenant.headers,
            json=rule_set_body([TURNOVER_RULE]),
        )

        body = response.json()
        assert response.status_code == 200
        assert body["title"] == tender.title
        assert body["results"][0]["rule_id"] == "r_turnover"
        assert body["results"][0]["reason"]

    async def test_testing_an_unknown_tender_is_a_clean_404(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.post(
            f"/api/v1/rule-sets/test/{uuid4()}",
            headers=tenant.headers,
            json=rule_set_body([]),
        )

        assert response.status_code == 404


class TestDecisions:
    async def test_recording_and_reading_a_decision(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        response = await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid", "note": "Good fit, we have the certs"},
        )

        body = response.json()
        assert response.status_code == 200
        assert body["decision"] == "bid"
        assert body["is_current"] is True

    async def test_changing_your_mind_keeps_the_trail(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        """The note on a reversal is often the most valuable text in the system."""
        await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "skip", "note": "Too small"},
        )
        await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid", "note": "Buyer extended the scope"},
        )

        history = (
            await api.get(f"/api/v1/tenders/{tender.id}/decisions", headers=tenant.headers)
        ).json()

        assert [d["decision"] for d in history] == ["bid", "skip"]
        assert [d["is_current"] for d in history] == [True, False]
        assert history[0]["note"] == "Buyer extended the scope"

    async def test_only_one_decision_is_live_at_a_time(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        for outcome in ("bid", "hold", "skip"):
            await api.put(
                f"/api/v1/tenders/{tender.id}/decision",
                headers=tenant.headers,
                json={"decision": outcome},
            )

        listed = (await api.get("/api/v1/decisions", headers=tenant.headers)).json()
        for_tender = [d for d in listed["items"] if d["tender_id"] == str(tender.id)]
        assert len(for_tender) == 1
        assert for_tender[0]["decision"] == "skip"

    async def test_withdrawing_keeps_the_history(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid"},
        )

        removed = await api.delete(f"/api/v1/tenders/{tender.id}/decision", headers=tenant.headers)
        history = (
            await api.get(f"/api/v1/tenders/{tender.id}/decisions", headers=tenant.headers)
        ).json()

        assert removed.status_code == 204
        assert len(history) == 1
        assert history[0]["is_current"] is False

    async def test_the_list_can_be_filtered_by_outcome(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid"},
        )

        bids = (
            await api.get("/api/v1/decisions", headers=tenant.headers, params={"decision": "bid"})
        ).json()

        assert all(d["decision"] == "bid" for d in bids["items"])
        assert any(d["tender_id"] == str(tender.id) for d in bids["items"])

    async def test_a_decision_survives_having_no_match(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        """The state every company is in before it finishes its profile.

        Nothing has been scored, so there is no match row to join to. The
        decision is still a decision, and the pipeline is built from this
        list — an inner join here is what made a recorded bid appear on no
        screen in the product.
        """
        await api.put(
            f"/api/v1/tenders/{tender.id}/decision",
            headers=tenant.headers,
            json={"decision": "bid"},
        )

        listed = (await api.get("/api/v1/decisions", headers=tenant.headers)).json()

        row = next(d for d in listed["items"] if d["tender_id"] == str(tender.id))
        assert row["verdict"] is None
        assert row["tender"]["title"] == "Supply of enterprise network switches"

    async def test_a_member_may_decide(self, api: AsyncClient, tender: Tender) -> None:
        """The person who spots a tender is often not the admin."""
        member = await make_tenant(role=OrgRole.MEMBER, name="Padma")
        try:
            response = await api.put(
                f"/api/v1/tenders/{tender.id}/decision",
                headers=member.headers,
                json={"decision": "hold"},
            )

            assert response.status_code == 200
        finally:
            await drop_tenant(member)

    async def test_one_tenant_cannot_see_anothers_decisions(
        self, api: AsyncClient, tenant: Tenant, tender: Tender
    ) -> None:
        other = await make_tenant(name="Jamuna")
        try:
            await api.put(
                f"/api/v1/tenders/{tender.id}/decision",
                headers=tenant.headers,
                json={"decision": "bid"},
            )

            history = (
                await api.get(f"/api/v1/tenders/{tender.id}/decisions", headers=other.headers)
            ).json()

            assert history == []
        finally:
            await drop_tenant(other)

    async def test_deciding_on_an_unknown_tender_is_a_clean_404(
        self, api: AsyncClient, tenant: Tenant
    ) -> None:
        response = await api.put(
            f"/api/v1/tenders/{uuid4()}/decision",
            headers=tenant.headers,
            json={"decision": "bid"},
        )

        assert response.status_code == 404
