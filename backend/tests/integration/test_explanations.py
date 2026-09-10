"""Model-written explanations, and the budget that rations them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.ai.fake_client import FakeAIClient
from app.core.config import settings
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.jobs.tasks.explanations import generate_explanations
from app.jobs.tasks.matching import process_tender
from app.modules.matching.ai_usage import AiUsage, spent_today, within_budget
from app.modules.matching.models import ExplanationKind, TenderMatch
from app.modules.orgs.models import Organization
from app.modules.profiles.models import CompanyProfile, ProfileService
from app.modules.tenders.models import ProcurementCategory, Tender, TenderSource


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
        await session.execute(delete(AiUsage).where(AiUsage.org_id == record.id))
        await session.execute(delete(Organization).where(Organization.id == record.id))


@pytest.fixture
async def profile(org: Organization) -> CompanyProfile:
    record = CompanyProfile(
        org_id=org.id,
        overview="Enterprise network infrastructure and systems integration.",
        sectors=["it"],
        geographies=["BD"],
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
        "summary": "Core switches, routers and structured cabling for a data centre.",
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


async def match_for(org_id: Any, tender_id: Any) -> TenderMatch | None:
    async with session_scope() as session:
        return await session.scalar(
            select(TenderMatch).where(
                TenderMatch.org_id == org_id, TenderMatch.tender_id == tender_id
            )
        )


class TestGeneration:
    async def test_a_strong_match_gets_model_written_prose(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        tender = await make_tender(source)

        await process_tender(ctx, str(tender.id))

        match = await match_for(org.id, tender.id)
        assert match is not None
        if match.grade.value in {"S", "A"}:
            assert match.explanation_kind is ExplanationKind.LLM
            assert match.explanation_text

    async def test_every_match_keeps_a_templated_explanation_regardless(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """Hitting the cap or an outage must degrade the prose, not the product."""
        tender = await make_tender(source)
        await process_tender(ctx, str(tender.id))

        broken = {"ai_client": FakeAIClient(dims=768, fail_generation=True)}
        result = await generate_explanations(broken, str(tender.id))

        match = await match_for(org.id, tender.id)
        assert match is not None
        assert match.explanation_text
        assert result["written"] == 0

    async def test_a_weak_match_is_not_worth_the_tokens(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        unrelated = await make_tender(
            source,
            title="Printing of primary school textbooks",
            summary="Offset printing and binding for rural schools.",
        )

        await process_tender(ctx, str(unrelated.id))

        match = await match_for(org.id, unrelated.id)
        assert match is not None
        if match.grade.value == "C":
            assert match.explanation_kind is ExplanationKind.TEMPLATED

    async def test_rerunning_does_not_rewrite_identical_prose(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """An unchanged verdict does not need paying for twice."""
        tender = await make_tender(source)
        await process_tender(ctx, str(tender.id))

        again = await generate_explanations(ctx, str(tender.id))

        assert again["written"] == 0


class TestBudget:
    async def test_usage_is_recorded_per_call(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        tender = await make_tender(source)

        await process_tender(ctx, str(tender.id))

        async with session_scope() as session:
            rows = list(
                (await session.scalars(select(AiUsage).where(AiUsage.org_id == org.id))).all()
            )
        match = await match_for(org.id, tender.id)
        assert match is not None
        if match.explanation_kind is ExplanationKind.LLM:
            assert rows and rows[0].purpose == "explanation"

    async def test_an_exhausted_budget_stops_spending(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A key exhausted at 09:00 must not leave the rest of the day silent
        about why — it should simply keep the templated explanations."""
        tender = await make_tender(source)
        await process_tender(ctx, str(tender.id))

        # Reset to templated so there is something to spend on, then cap it.
        async with session_scope() as session:
            match = await session.scalar(
                select(TenderMatch).where(
                    TenderMatch.org_id == org.id, TenderMatch.tender_id == tender.id
                )
            )
            assert match is not None
            match.explanation_kind = ExplanationKind.TEMPLATED

        monkeypatch.setattr(settings, "ai_daily_token_budget", 1)
        result = await generate_explanations(ctx, str(tender.id))

        assert result["written"] == 0
        after = await match_for(org.id, tender.id)
        assert after is not None
        assert after.explanation_text  # the templated one survives

    async def test_a_budget_of_zero_means_unlimited(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An operator who has not set a budget should not silently get nothing."""
        monkeypatch.setattr(settings, "ai_daily_token_budget", 0)

        async with session_scope() as session:
            assert await within_budget(session, headroom=10**9) is True

    async def test_spending_is_counted_for_today(self, org: Organization) -> None:
        async with session_scope() as session:
            before = await spent_today(session)
            session.add(
                AiUsage(
                    org_id=org.id,
                    day=utcnow().date(),
                    purpose="test",
                    model="fake",
                    tokens_in=100,
                    tokens_out=50,
                )
            )
            await session.flush()
            after = await spent_today(session)

        assert after - before == 150
