"""The pipeline end to end: extract, embed, score, grade, store.

Runs against real Postgres with the deterministic fake AI client, so the same
inputs always produce the same grades and these assertions are stable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.ai.fake_client import FakeAIClient
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.jobs.tasks.matching import process_tender, rematch_org
from app.modules.matching.models import (
    MatchGrade,
    TenderMatch,
    TenderMatchHistory,
    Urgency,
)
from app.modules.orgs.models import Organization
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileEmbedding,
    ProfileService,
)
from app.modules.tenders.models import (
    ProcurementCategory,
    Tender,
    TenderEmbedding,
    TenderExtraction,
    TenderSource,
)


@pytest.fixture
def ctx() -> dict[str, object]:
    """ARQ job context carrying the deterministic client."""
    return {"ai_client": FakeAIClient(dims=768)}


@pytest.fixture
async def org() -> AsyncIterator[Organization]:
    record = Organization(
        name="Meghna Systems", slug=f"meghna-{uuid4().hex[:8]}", timezone="Asia/Dhaka"
    )
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
        overview="Systems integration, enterprise network infrastructure and data centres.",
        sectors=["it", "telecom"],
        geographies=["BD"],
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        session.add(
            ProfileService(
                profile_id=record.id,
                name="Network integration",
                description="enterprise network switches routers structured cabling",
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


async def make_tender(source: TenderSource, *, title: str, summary: str, **kw: object) -> Tender:
    fields: dict[str, object] = {
        "source_id": source.id,
        "external_id": uuid4().hex,
        "canonical_url": "https://example.invalid/n/1",
        "title": title,
        "summary": summary,
        "procuring_entity": "Bangladesh Bank",
        "country": "BD",
        "procurement_category": ProcurementCategory.GOODS,
        "content_hash": uuid4().hex,
        "deadline_at": utcnow() + timedelta(days=30),
    }
    record = Tender(**(fields | kw))
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    return record


async def match_for(org_id: object, tender_id: object) -> TenderMatch | None:
    async with session_scope() as session:
        return await session.scalar(
            select(TenderMatch).where(
                TenderMatch.org_id == org_id, TenderMatch.tender_id == tender_id
            )
        )


class TestProcessTender:
    async def test_it_extracts_embeds_and_matches(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        await rematch_org(ctx, str(org.id))  # gives the profile its vectors
        tender = await make_tender(
            source,
            title="Supply of enterprise network switches",
            summary="Core switches, routers and structured cabling for a data centre.",
        )

        result = await process_tender(ctx, str(tender.id))

        # Counts are across every tenant with a profile, so assert a floor and
        # check this organization's own verdict below.
        assert result["matched"] >= 1
        assert result["failed"] == 0
        async with session_scope() as session:
            extraction = await session.scalar(
                select(TenderExtraction).where(TenderExtraction.tender_id == tender.id)
            )
            chunks = await session.scalar(
                select(func.count(TenderEmbedding.id)).where(TenderEmbedding.tender_id == tender.id)
            )
        assert extraction is not None and extraction.is_current
        # Title/summary plus the scope chunk extraction unlocked.
        assert chunks == 2

        match = await match_for(org.id, tender.id)
        assert match is not None
        assert match.grade in set(MatchGrade)
        assert match.explanation_text
        assert match.inputs_fingerprint

    async def test_a_brand_new_profile_is_embedded_before_matching(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The bug this caught: a profile that had never been embedded scored
        0.0 against everything, so a new customer's entire first feed read as
        C-grade "weak fit" — a confident rejection of a comparison that never
        happened. `process_tender` now embeds the profile before scoring."""
        tender = await make_tender(
            source,
            title="Supply of enterprise network switches",
            summary="Core switches, routers and structured cabling for a data centre.",
        )

        # No `rematch_org` first: this is the very first thing the org sees.
        await process_tender(ctx, str(tender.id))

        match = await match_for(org.id, tender.id)
        assert match is not None
        assert match.similarity > 0.0

    async def test_a_match_is_not_stored_when_there_is_nothing_to_compare(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """An empty profile has no facets, so there is no comparison to make.
        Storing 0.0 would look like a considered verdict."""
        async with session_scope() as session:
            empty = await session.get(CompanyProfile, profile.id)
            assert empty is not None
            empty.overview = None
            empty.sectors = []
            empty.geographies = []
            empty.keywords = []
            await session.execute(
                delete(ProfileService).where(ProfileService.profile_id == profile.id)
            )

        tender = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )
        result = await process_tender(ctx, str(tender.id))

        assert result["not_scorable"] >= 1
        assert await match_for(org.id, tender.id) is None

    async def test_a_relevant_notice_outgrades_an_irrelevant_one(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The product's whole premise, asserted through the real pipeline."""
        await rematch_org(ctx, str(org.id))
        relevant = await make_tender(
            source,
            title="Supply of enterprise network switches",
            summary="Core switches, routers and structured cabling for a data centre.",
        )
        irrelevant = await make_tender(
            source,
            title="Printing of primary school textbooks",
            summary="Offset printing and binding of textbooks for rural schools.",
        )

        await process_tender(ctx, str(relevant.id))
        await process_tender(ctx, str(irrelevant.id))

        good = await match_for(org.id, relevant.id)
        bad = await match_for(org.id, irrelevant.id)
        assert good is not None and bad is not None
        assert good.similarity > bad.similarity

    async def test_reprocessing_an_unchanged_notice_skips_the_work(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The fingerprint guard is what keeps a daily scrape from re-scoring
        thousands of unchanged notices for every tenant."""
        await rematch_org(ctx, str(org.id))
        tender = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )

        first = await process_tender(ctx, str(tender.id))
        second = await process_tender(ctx, str(tender.id))

        assert first["matched"] >= 1
        # The second pass must recompute nothing: everything it saw was skipped.
        assert second["matched"] == 0
        assert second["skipped"] == first["matched"] + first["skipped"]

    async def test_it_records_history_once_not_on_every_run(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """Otherwise the timeline buries real movement under identical rows."""
        await rematch_org(ctx, str(org.id))
        tender = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )

        await process_tender(ctx, str(tender.id))
        await process_tender(ctx, str(tender.id))

        async with session_scope() as session:
            match_id = await session.scalar(
                select(TenderMatch.id).where(
                    TenderMatch.org_id == org.id, TenderMatch.tender_id == tender.id
                )
            )
            # Scoped to this match: the pool may hold other notices this org
            # was scored against, and their history is not what is under test.
            entries = await session.scalar(
                select(func.count(TenderMatchHistory.id)).where(
                    TenderMatchHistory.match_id == match_id
                )
            )
        assert entries == 1

    async def test_an_organization_without_a_profile_is_skipped(
        self, ctx: dict[str, object], org: Organization, source: TenderSource
    ) -> None:
        """A row of zeroes it would have to look at is worse than no row."""
        tender = await make_tender(source, title="Anything", summary="Anything at all.")

        result = await process_tender(ctx, str(tender.id))

        assert result["failed"] == 0
        assert await match_for(org.id, tender.id) is None

    async def test_a_missing_tender_returns_cleanly(self, ctx: dict[str, object]) -> None:
        result = await process_tender(ctx, str(uuid4()))

        assert result["error"] == "not_found"

    async def test_an_extraction_failure_still_leaves_a_match(
        self,
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """A notice the model cannot read must still be scored, not vanish.

        Extraction and embedding are separate endpoints and fail
        independently, so only generation is broken here.
        """
        tender = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )
        broken = {"ai_client": FakeAIClient(dims=768, fail_generation=True)}

        result = await process_tender(broken, str(tender.id))

        assert result["extraction"] == "failed"
        assert result["matched"] >= 1
        match = await match_for(org.id, tender.id)
        assert match is not None

    async def test_the_deadline_drives_urgency_in_the_org_timezone(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        await rematch_org(ctx, str(org.id))
        tender = await make_tender(
            source,
            title="Supply of network switches",
            summary="Switches and cabling.",
            deadline_at=utcnow() + timedelta(days=2),
        )

        await process_tender(ctx, str(tender.id))

        match = await match_for(org.id, tender.id)
        assert match is not None
        assert match.urgency is Urgency.CRITICAL


class TestRematchOrg:
    async def test_it_embeds_the_profile_and_scores_the_open_pool(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        tender = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )
        # Only tenders that already carry vectors are re-scored, so this one
        # has to go through the ingest path first.
        await process_tender(ctx, str(tender.id))

        result = await rematch_org(ctx, str(org.id))

        assert result["matched"] + result["skipped"] >= 1
        async with session_scope() as session:
            facets = await session.scalar(
                select(func.count(ProfileEmbedding.id)).where(
                    ProfileEmbedding.profile_id == profile.id
                )
            )
        # Overview, sector/geo, and the one service.
        assert facets == 3

    async def test_a_closed_tender_is_not_rescored(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """Re-scoring something nobody can bid on cannot change any decision."""
        expired = await make_tender(
            source,
            title="Supply of network switches",
            summary="Switches and cabling.",
            deadline_at=utcnow() - timedelta(days=1),
        )
        await process_tender(ctx, str(expired.id))  # gives it vectors
        async with session_scope() as session:
            await session.execute(delete(TenderMatch).where(TenderMatch.tender_id == expired.id))

        await rematch_org(ctx, str(org.id))

        assert await match_for(org.id, expired.id) is None

    async def test_a_tender_with_no_vectors_yet_gets_no_junk_match(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """A notice that has not been through `process_tender` has no vectors,
        so scoring it would store a 0.0-similarity C-grade match — a row in the
        feed saying "we looked and found nothing" when we never looked."""
        unprocessed = await make_tender(
            source, title="Supply of network switches", summary="Switches and cabling."
        )

        await rematch_org(ctx, str(org.id))

        assert await match_for(org.id, unprocessed.id) is None

    async def test_an_organization_without_a_profile_returns_cleanly(
        self, ctx: dict[str, object], org: Organization
    ) -> None:
        result = await rematch_org(ctx, str(org.id))

        assert result["error"] == "no_profile"

    async def test_editing_the_profile_rescores(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """The demo the milestone promises: change the profile, grades move."""
        tender = await make_tender(
            source,
            title="Printing of primary school textbooks",
            summary="Offset printing and binding of textbooks for rural schools.",
        )
        await process_tender(ctx, str(tender.id))
        before = await match_for(org.id, tender.id)
        assert before is not None

        async with session_scope() as session:
            fresh = await session.get(CompanyProfile, profile.id)
            assert fresh is not None
            fresh.overview = "Offset printing, binding and textbook production for schools."
            fresh.version += 1
            await session.execute(
                delete(ProfileService).where(ProfileService.profile_id == profile.id)
            )

        await rematch_org(ctx, str(org.id), reason="profile_changed")

        after = await match_for(org.id, tender.id)
        assert after is not None
        assert after.similarity > before.similarity

    async def test_a_deleted_service_stops_scoring(
        self,
        ctx: dict[str, object],
        org: Organization,
        profile: CompanyProfile,
        source: TenderSource,
    ) -> None:
        """A vector for work the company no longer does would inflate matches
        against that work forever."""
        await rematch_org(ctx, str(org.id))

        async with session_scope() as session:
            await session.execute(
                delete(ProfileService).where(ProfileService.profile_id == profile.id)
            )

        await rematch_org(ctx, str(org.id))

        async with session_scope() as session:
            remaining = await session.scalars(
                select(ProfileEmbedding.facet_kind).where(ProfileEmbedding.profile_id == profile.id)
            )
            kinds = {kind.value for kind in remaining.all()}
        assert "service" not in kinds
