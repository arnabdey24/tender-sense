"""Rules against real rows: a rule change flips eligibility, with reasons."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date, timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.ai.fake_client import FakeAIClient
from app.core.ids import new_id
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.jobs.tasks.matching import process_tender
from app.modules.matching.models import EligibilityStatus, TenderMatch
from app.modules.orgs.models import Organization
from app.modules.profiles.models import CompanyProfile, ProfileCertification, ProfileService
from app.modules.rules.models import FxRate, OverrideVerdict, RuleOverride, RuleSet, RuleSetVersion
from app.modules.rules.service import evaluate_for_tender
from app.modules.tenders.models import (
    ExtractionStatus,
    ProcurementCategory,
    Tender,
    TenderExtraction,
    TenderSource,
)


@pytest.fixture
def ctx() -> dict[str, object]:
    return {"ai_client": FakeAIClient(dims=768)}


@pytest.fixture
async def org() -> AsyncIterator[Organization]:
    record = Organization(name="Meghna", slug=f"meghna-{uuid4().hex[:8]}")
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(Organization).where(Organization.id == record.id))


@pytest.fixture
async def profile(org: Organization) -> CompanyProfile:
    record = CompanyProfile(
        org_id=org.id,
        overview="Enterprise network infrastructure and systems integration.",
        sectors=["it"],
        geographies=["BD"],
        annual_turnover=200_000,
        turnover_currency="USD",
        years_in_business=12,
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        session.add(
            ProfileService(
                profile_id=record.id,
                name="Network integration",
                description="enterprise network switches routers cabling",
            )
        )
        session.add(ProfileCertification(profile_id=record.id, code="ISO9001", label="ISO 9001"))
        await session.flush()
        await session.refresh(record)
    return record


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


async def make_tender(source: TenderSource, **overrides: Any) -> Tender:
    fields: dict[str, Any] = {
        "source_id": source.id,
        "external_id": uuid4().hex,
        "canonical_url": "https://example.invalid/n/1",
        "title": "Supply of enterprise network switches",
        "summary": "Core switches and structured cabling for a data centre.",
        "procuring_entity": "Bangladesh Bank",
        "country": "BD",
        "procurement_category": ProcurementCategory.GOODS,
        "content_hash": uuid4().hex,
        "deadline_at": utcnow() + timedelta(days=30),
    }
    record = Tender(**(fields | overrides))
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    return record


async def set_extraction(
    tender: Tender, attributes: dict[str, Any], confidence: dict[str, float]
) -> None:
    async with session_scope() as session:
        await session.execute(
            delete(TenderExtraction).where(TenderExtraction.tender_id == tender.id)
        )
        session.add(
            TenderExtraction(
                tender_id=tender.id,
                version=1,
                model="test",
                prompt_version="v1",
                schema_version=1,
                attributes=attributes,
                field_confidence=confidence,
                evidence={},
                input_hash=uuid4().hex,
                status=ExtractionStatus.SUCCEEDED,
                is_current=True,
            )
        )


async def install_rules(org: Organization, rules: list[dict[str, Any]]) -> RuleSetVersion:
    """Replace the organization's active criteria with a new version."""
    async with session_scope() as session:
        rule_set = await session.scalar(select(RuleSet).where(RuleSet.org_id == org.id))
        if rule_set is None:
            rule_set = RuleSet(org_id=org.id, name="Bidding criteria")
            session.add(rule_set)
            await session.flush()

        existing = await session.scalars(
            select(RuleSetVersion).where(RuleSetVersion.rule_set_id == rule_set.id)
        )
        next_number = max((row.version_number for row in existing.all()), default=0) + 1

        version = RuleSetVersion(
            rule_set_id=rule_set.id,
            org_id=org.id,
            version_number=next_number,
            definition={"schema_version": 1, "combinator": "all", "rules": rules},
        )
        session.add(version)
        await session.flush()
        rule_set.current_version_id = version.id
        await session.flush()
        await session.refresh(version)
        return version


async def evaluate(org: Organization, profile: CompanyProfile, tender: Tender) -> Any:
    """Evaluate through the same seam the matcher uses.

    Not via `process_tender`: that re-runs extraction, which would overwrite
    the attributes a test planted to exercise a specific rule.
    """
    async with session_scope() as session:
        fresh_tender = await session.get(Tender, tender.id)
        fresh_profile = await session.get(CompanyProfile, profile.id)
        assert fresh_tender and fresh_profile
        return await evaluate_for_tender(
            session, tender=fresh_tender, profile=fresh_profile, org_id=org.id
        )


async def match_for(org_id: Any, tender_id: Any) -> TenderMatch | None:
    async with session_scope() as session:
        return await session.scalar(
            select(TenderMatch).where(
                TenderMatch.org_id == org_id, TenderMatch.tender_id == tender_id
            )
        )


TURNOVER_RULE = {
    "id": "r_turnover",
    "attribute": "min_annual_turnover",
    "operator": "lte",
    "value": {"source": "profile", "field": "annual_turnover"},
    "severity": "hard",
    "on_missing": "verify",
}


class TestEligibilityInTheFeed:
    async def test_no_rules_means_eligible(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """A customer who has written no criteria has not failed to answer."""
        tender = await make_tender(source)

        await process_tender(ctx, str(tender.id))

        match = await match_for(org.id, tender.id)
        assert match is not None
        assert match.eligibility_status is EligibilityStatus.ELIGIBLE

    async def test_a_rule_can_make_a_tender_ineligible_with_reasons(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The milestone's demo: a rule flips eligibility, and says why."""
        tender = await make_tender(source)
        await set_extraction(
            tender,
            {"min_annual_turnover": {"amount": 5_000_000, "currency": "USD"}},
            {"min_annual_turnover": 0.9},
        )
        await install_rules(org, [TURNOVER_RULE])

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.INELIGIBLE
        failing = evaluation.failing
        assert len(failing) == 1
        assert "USD 5,000,000" in (failing[0].tender_value or "")
        assert failing[0].confidence == pytest.approx(0.9)
        assert "does not meet" in failing[0].reason

    async def test_relaxing_the_rule_flips_it_back(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        tender = await make_tender(source)
        await set_extraction(
            tender,
            {"min_annual_turnover": {"amount": 5_000_000, "currency": "USD"}},
            {"min_annual_turnover": 0.9},
        )
        await install_rules(org, [TURNOVER_RULE])

        assert (await evaluate(org, profile, tender)).status is EligibilityStatus.INELIGIBLE

        # Same rule, but soft: it can colour the recommendation, never block.
        await install_rules(org, [{**TURNOVER_RULE, "severity": "soft"}])

        assert (await evaluate(org, profile, tender)).status is EligibilityStatus.ELIGIBLE

    async def test_a_new_rule_version_forces_a_rescore(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The rule set version is part of the fingerprint, so changing rules
        must invalidate every stored verdict rather than being skipped."""
        tender = await make_tender(source)
        await install_rules(org, [])
        await process_tender(ctx, str(tender.id))
        before = await match_for(org.id, tender.id)
        assert before is not None

        await install_rules(org, [TURNOVER_RULE])
        result = await process_tender(ctx, str(tender.id))

        assert result["matched"] >= 1
        after = await match_for(org.id, tender.id)
        assert after is not None
        assert after.inputs_fingerprint != before.inputs_fingerprint

    async def test_an_unstated_requirement_asks_rather_than_rejects(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """A notice that says nothing about turnover has not disqualified us."""
        tender = await make_tender(source)
        await set_extraction(tender, {}, {})
        await install_rules(org, [TURNOVER_RULE])

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.NEEDS_VERIFICATION
        assert evaluation.unresolved[0].status == "unknown"
        assert "does not state" in evaluation.unresolved[0].reason


class TestOverrides:
    async def test_a_teammate_can_answer_what_the_engine_could_not(
        self, org: Organization, profile: CompanyProfile, source: TenderSource
    ) -> None:
        tender = await make_tender(source)
        await set_extraction(tender, {}, {})
        await install_rules(org, [TURNOVER_RULE])

        async with session_scope() as session:
            session.add(
                RuleOverride(
                    org_id=org.id,
                    tender_id=tender.id,
                    rule_id="r_turnover",
                    verdict=OverrideVerdict.PASS,
                    note="Bid document says BDT 20m",
                )
            )

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.ELIGIBLE
        assert evaluation.results[0].source == "override"
        assert "Bid document says BDT 20m" in evaluation.results[0].reason

    async def test_an_override_cannot_flip_a_rule_the_engine_decided(
        self, org: Organization, profile: CompanyProfile, source: TenderSource
    ) -> None:
        """Otherwise the stored reasoning becomes a lie: it would show a rule
        passing beside evidence that it failed."""
        tender = await make_tender(source)
        await set_extraction(
            tender,
            {"min_annual_turnover": {"amount": 5_000_000, "currency": "USD"}},
            {"min_annual_turnover": 0.9},
        )
        await install_rules(org, [TURNOVER_RULE])

        async with session_scope() as session:
            session.add(
                RuleOverride(
                    org_id=org.id,
                    tender_id=tender.id,
                    rule_id="r_turnover",
                    verdict=OverrideVerdict.PASS,
                )
            )

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.INELIGIBLE


class TestCurrencyConversion:
    async def test_a_stored_rate_is_used_to_compare_across_currencies(
        self, org: Organization, profile: CompanyProfile, source: TenderSource
    ) -> None:
        """A BDT requirement against a USD profile is a hundredfold error if
        compared raw."""
        tender = await make_tender(source)
        await set_extraction(
            tender,
            {"min_annual_turnover": {"amount": 10_000_000, "currency": "BDT"}},
            {"min_annual_turnover": 0.9},
        )
        await install_rules(org, [TURNOVER_RULE])

        rate_id = new_id()
        async with session_scope() as session:
            session.add(
                FxRate(
                    id=rate_id,
                    base="USD",
                    currency="BDT",
                    rate=110.0,
                    as_of=date(2026, 9, 1),
                )
            )

        try:
            evaluation = await evaluate(org, profile, tender)

            # 10m BDT ≈ 91k USD, inside the 200k profile capacity.
            assert evaluation.status is EligibilityStatus.ELIGIBLE
        finally:
            async with session_scope() as session:
                await session.execute(delete(FxRate).where(FxRate.id == rate_id))

    async def test_without_a_rate_the_rule_asks_rather_than_guessing(
        self, org: Organization, profile: CompanyProfile, source: TenderSource
    ) -> None:
        tender = await make_tender(source)
        await set_extraction(
            tender,
            {"min_annual_turnover": {"amount": 10_000_000, "currency": "XYZ"}},
            {"min_annual_turnover": 0.9},
        )
        await install_rules(org, [TURNOVER_RULE])

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.NEEDS_VERIFICATION


class TestPortalWinsOverExtraction:
    async def test_the_scraped_deadline_is_used_not_the_inferred_one(
        self, org: Organization, profile: CompanyProfile, source: TenderSource
    ) -> None:
        """A scraped field is a fact; an inferred one is a guess."""
        deadline = utcnow() + timedelta(days=45)
        tender = await make_tender(source, deadline_at=deadline)
        await set_extraction(tender, {"deadline": "2020-01-01"}, {"deadline": 0.9})
        await install_rules(
            org,
            [
                {
                    "id": "r_time",
                    "attribute": "deadline_at",
                    "operator": "after",
                    "value": {"source": "literal", "data": {"days_from_now": 7}},
                    "severity": "hard",
                    "on_missing": "verify",
                }
            ],
        )

        evaluation = await evaluate(org, profile, tender)

        assert evaluation.status is EligibilityStatus.ELIGIBLE
