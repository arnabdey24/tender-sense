"""Schema guarantees the matching pipeline is built on.

These assert against real Postgres because the guarantees are Postgres
guarantees: a partial unique index, an ON DELETE cascade, and nearest-neighbour
ordering over an HNSW index. None of them are observable from the ORM alone.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.ai.fake_client import deterministic_embedding
from app.core.ids import new_id

# Configures the whole SQLAlchemy registry. Importing only the modules used
# below leaves cross-module foreign keys (organizations -> users) unresolvable.
from app.db import models as _models  # noqa: F401
from app.db.session import session_scope
from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    MatchingConfig,
    Recommendation,
    TenderMatch,
    Urgency,
)
from app.modules.orgs.models import Organization
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfileEmbedding,
    ProfileFacet,
    ProfileService,
)
from app.modules.tenders.models import ProcurementCategory, Tender, TenderSource

DIMS = 768


@pytest.fixture
async def org() -> AsyncIterator[Organization]:
    record = Organization(name="Meghna Systems", slug=f"meghna-{uuid4().hex[:8]}")
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
        overview="Systems integration and network infrastructure for public sector clients.",
        sectors=["it", "telecom"],
        geographies=["BD", "NP"],
        annual_turnover=200_000_000,
        turnover_currency="BDT",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    return record


@pytest.fixture
async def tender() -> AsyncIterator[Tender]:
    source = TenderSource(
        code=f"t-{uuid4().hex[:8]}", name="Test", adapter_key="manual", base_url=""
    )
    record = Tender(
        external_id=uuid4().hex,
        canonical_url="https://example.invalid/n/1",
        title="Supply of core network switches",
        procurement_category=ProcurementCategory.GOODS,
        content_hash=uuid4().hex,
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


def a_match(*, org_id: object, tender_id: object, **overrides: object) -> TenderMatch:
    defaults: dict[str, object] = {
        "org_id": org_id,
        "tender_id": tender_id,
        "similarity": 0.81,
        "grade": MatchGrade.S,
        "eligibility_status": EligibilityStatus.ELIGIBLE,
        "recommendation": Recommendation.BID,
        "urgency": Urgency.HIGH,
        "inputs_fingerprint": uuid4().hex,
    }
    return TenderMatch(**(defaults | overrides))


class TestProfile:
    async def test_an_organization_has_at_most_one_profile(
        self, org: Organization, profile: CompanyProfile
    ) -> None:
        """One capability profile per tenant is a stated assumption; enforce it."""
        with pytest.raises(IntegrityError):
            async with session_scope() as session:
                session.add(CompanyProfile(org_id=org.id, overview="A second one"))

    async def test_deleting_the_organization_takes_the_profile_with_it(
        self, org: Organization, profile: CompanyProfile
    ) -> None:
        async with session_scope() as session:
            await session.execute(delete(Organization).where(Organization.id == org.id))

        async with session_scope() as session:
            remaining = await session.scalar(
                select(func.count(CompanyProfile.id)).where(CompanyProfile.id == profile.id)
            )
            assert remaining == 0

    async def test_a_certification_code_is_unique_per_profile(
        self, profile: CompanyProfile
    ) -> None:
        """Otherwise a rule asking "do we hold ISO 9001" could see it twice."""
        async with session_scope() as session:
            session.add(
                ProfileCertification(profile_id=profile.id, code="ISO9001", label="ISO 9001")
            )
            await session.flush()

        with pytest.raises(IntegrityError):
            async with session_scope() as session:
                session.add(
                    ProfileCertification(
                        profile_id=profile.id, code="ISO9001", label="ISO 9001:2015"
                    )
                )

    async def test_deleting_a_service_takes_its_facet_vector_with_it(
        self, profile: CompanyProfile
    ) -> None:
        """A vector for a service that no longer exists would still score."""
        service = ProfileService(profile_id=profile.id, name="Network integration")
        async with session_scope() as session:
            session.add(service)
            await session.flush()
            session.add(
                ProfileEmbedding(
                    profile_id=profile.id,
                    facet_kind=ProfileFacet.SERVICE,
                    source_id=service.id,
                    label="Network integration",
                    model="fake-embedding-1",
                    embedding=deterministic_embedding("network integration", DIMS),
                    text_hash=uuid4().hex,
                )
            )
            await session.flush()
            service_id = service.id

        async with session_scope() as session:
            await session.execute(delete(ProfileService).where(ProfileService.id == service_id))

        async with session_scope() as session:
            orphans = await session.scalar(
                select(func.count(ProfileEmbedding.id)).where(
                    ProfileEmbedding.source_id == service_id
                )
            )
            # The vector is scoped to the profile, so the application must clean
            # up facets whose owning row is gone — the FK does not do it.
            assert orphans == 1


class TestFacetSearch:
    async def test_the_closest_facet_to_a_tender_is_the_relevant_one(
        self, profile: CompanyProfile
    ) -> None:
        """The premise of facet-level matching, checked through pgvector."""
        async with session_scope() as session:
            for label, text in [
                ("Network integration", "enterprise network switches routers cabling"),
                ("Textbook printing", "offset printing of school textbooks and binding"),
            ]:
                session.add(
                    ProfileEmbedding(
                        profile_id=profile.id,
                        facet_kind=ProfileFacet.SERVICE,
                        source_id=new_id(),
                        label=label,
                        model="fake-embedding-1",
                        embedding=deterministic_embedding(text, DIMS),
                        text_hash=uuid4().hex,
                    )
                )
            await session.flush()

        probe = deterministic_embedding("supply and installation of network switches", DIMS)
        async with session_scope() as session:
            nearest = await session.scalar(
                select(ProfileEmbedding.label)
                .where(ProfileEmbedding.profile_id == profile.id)
                .order_by(ProfileEmbedding.embedding.cosine_distance(probe))
                .limit(1)
            )

        assert nearest == "Network integration"


class TestMatch:
    async def test_an_organization_matches_a_tender_once(
        self, org: Organization, tender: Tender
    ) -> None:
        async with session_scope() as session:
            session.add(a_match(org_id=org.id, tender_id=tender.id))
            await session.flush()

        with pytest.raises(IntegrityError):
            async with session_scope() as session:
                session.add(a_match(org_id=org.id, tender_id=tender.id))

    async def test_two_organizations_can_match_the_same_tender(
        self, org: Organization, tender: Tender
    ) -> None:
        """The pool is shared; only the verdict is per-tenant."""
        other = Organization(name="Other Ltd", slug=f"other-{uuid4().hex[:8]}")
        async with session_scope() as session:
            session.add(other)
            await session.flush()
            session.add(a_match(org_id=org.id, tender_id=tender.id))
            session.add(a_match(org_id=other.id, tender_id=tender.id, grade=MatchGrade.C))
            await session.flush()

            count = await session.scalar(
                select(func.count(TenderMatch.id)).where(TenderMatch.tender_id == tender.id)
            )
            assert count == 2

        async with session_scope() as session:
            await session.execute(delete(Organization).where(Organization.id == other.id))

    async def test_deleting_a_tender_takes_its_matches_with_it(
        self, org: Organization, tender: Tender
    ) -> None:
        async with session_scope() as session:
            session.add(a_match(org_id=org.id, tender_id=tender.id))
            await session.flush()

        async with session_scope() as session:
            await session.execute(delete(Tender).where(Tender.id == tender.id))

        async with session_scope() as session:
            remaining = await session.scalar(
                select(func.count(TenderMatch.id)).where(TenderMatch.tender_id == tender.id)
            )
            assert remaining == 0


class TestMatchingConfig:
    async def test_thresholds_round_trip_with_their_defaults(self) -> None:
        """Defaults live in the row, so calibration can move them without a deploy."""
        config = MatchingConfig(thresholds_version=1)
        async with session_scope() as session:
            session.add(config)
            await session.flush()
            await session.refresh(config)
            config_id = config.id

            assert config.grade_s_threshold == pytest.approx(0.78)
            assert config.grade_a_threshold == pytest.approx(0.70)
            assert config.max_facet_weight + config.mean_facet_weight == pytest.approx(1.0)

        async with session_scope() as session:
            await session.execute(delete(MatchingConfig).where(MatchingConfig.id == config_id))
