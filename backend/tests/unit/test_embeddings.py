"""Building the texts that get embedded, and skipping the ones that did not change."""

from __future__ import annotations

from app.ai.embeddings import (
    MAX_EMBED_CHARS,
    ChunkText,
    FacetText,
    embed_chunks,
    embed_facets,
    plan_embeddings,
    profile_facets,
    tender_chunks,
    text_hash,
)
from app.ai.fake_client import FakeAIClient
from app.core.ids import new_id
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileFacet,
    ProfilePastProject,
    ProfileService,
)
from app.modules.tenders.models import EmbeddingChunk, ProcurementCategory, Tender


def a_profile(**overrides: object) -> CompanyProfile:
    defaults: dict[str, object] = {
        "id": new_id(),
        "org_id": new_id(),
        "overview": "Systems integration for public sector clients.",
        "sectors": ["it", "telecom"],
        "geographies": ["BD", "NP"],
        "keywords": ["networking", "data centre"],
    }
    return CompanyProfile(**(defaults | overrides))


def a_service(name: str, description: str | None = None) -> ProfileService:
    return ProfileService(id=new_id(), profile_id=new_id(), name=name, description=description)


def a_project(title: str) -> ProfilePastProject:
    return ProfilePastProject(id=new_id(), profile_id=new_id(), title=title)


def a_tender(**overrides: object) -> Tender:
    defaults: dict[str, object] = {
        "id": new_id(),
        "external_id": "1",
        "canonical_url": "https://example.invalid/n/1",
        "title": "Supply of core network switches",
        "summary": "Switches and cabling for a data centre.",
        "procuring_entity": "Bangladesh Bank",
        "procurement_category": ProcurementCategory.GOODS,
    }
    return Tender(**(defaults | overrides))


class TestProfileFacets:
    def test_it_produces_one_facet_per_service_and_project(self) -> None:
        facets = profile_facets(
            a_profile(),
            services=[a_service("Network integration"), a_service("Managed hosting")],
            projects=[a_project("Core switch refresh for a bank")],
        )

        kinds = [facet.facet_kind for facet in facets]
        assert kinds.count(ProfileFacet.SERVICE) == 2
        assert kinds.count(ProfileFacet.PAST_PROJECT) == 1
        assert ProfileFacet.OVERVIEW in kinds
        assert ProfileFacet.SECTOR_GEO in kinds

    def test_an_empty_profile_produces_no_facets(self) -> None:
        """An empty facet would still score against every tender, badly,
        dragging the mean down for no reason."""
        facets = profile_facets(
            a_profile(overview=None, sectors=[], geographies=[], keywords=[]),
            services=[],
            projects=[],
        )

        assert facets == []

    def test_a_service_with_no_text_is_skipped(self) -> None:
        facets = profile_facets(
            a_profile(overview=None, sectors=[], geographies=[], keywords=[]),
            services=[a_service("")],
            projects=[],
        )

        assert facets == []

    def test_a_facet_carries_the_row_it_came_from(self) -> None:
        """Deleting a service has to be able to find and drop its vector."""
        service = a_service("Network integration")

        facets = profile_facets(a_profile(), services=[service], projects=[])

        service_facet = next(f for f in facets if f.facet_kind is ProfileFacet.SERVICE)
        assert service_facet.source_id == service.id
        assert service_facet.label == "Network integration"

    def test_profile_level_facets_have_no_source_row(self) -> None:
        facets = profile_facets(a_profile(), services=[], projects=[])

        assert all(f.source_id is None for f in facets)

    def test_sectors_and_geographies_read_as_one_statement(self) -> None:
        facets = profile_facets(a_profile(), services=[], projects=[])

        sector_geo = next(f for f in facets if f.facet_kind is ProfileFacet.SECTOR_GEO)
        assert "it, telecom" in sector_geo.text
        assert "operating in BD, NP" in sector_geo.text

    def test_very_long_text_is_clipped(self) -> None:
        facets = profile_facets(a_profile(overview="x " * 20_000), services=[], projects=[])

        overview = next(f for f in facets if f.facet_kind is ProfileFacet.OVERVIEW)
        assert len(overview.text) <= MAX_EMBED_CHARS


class TestTenderChunks:
    def test_a_scraped_notice_is_matchable_before_extraction_runs(self) -> None:
        chunks = tender_chunks(a_tender())

        assert [c.chunk_kind for c in chunks] == [EmbeddingChunk.TITLE_SUMMARY]

    def test_extraction_adds_a_second_sharper_chunk(self) -> None:
        chunks = tender_chunks(
            a_tender(),
            attributes={
                "scope_summary": "Install and commission core switches.",
                "key_deliverables": ["48-port switches", "structured cabling"],
                "sectors": ["it"],
            },
        )

        kinds = [c.chunk_kind for c in chunks]
        assert EmbeddingChunk.SCOPE_REQUIREMENTS in kinds
        scope = next(c for c in chunks if c.chunk_kind is EmbeddingChunk.SCOPE_REQUIREMENTS)
        assert "48-port switches" in scope.text

    def test_an_empty_extraction_adds_no_chunk(self) -> None:
        chunks = tender_chunks(a_tender(), attributes={"scope_summary": None})

        assert [c.chunk_kind for c in chunks] == [EmbeddingChunk.TITLE_SUMMARY]

    def test_the_headline_chunk_carries_the_buyer_and_category(self) -> None:
        chunks = tender_chunks(a_tender())

        assert "Bangladesh Bank" in chunks[0].text
        assert "goods" in chunks[0].text


class TestPlanEmbeddings:
    def test_unchanged_items_are_not_re_embedded(self) -> None:
        """Editing one service must not re-embed the whole profile."""
        facets = profile_facets(
            a_profile(),
            services=[a_service("Network integration"), a_service("Managed hosting")],
            projects=[],
        )
        existing = {f"{f.facet_kind.value}:{f.source_id or ''}": f.hash for f in facets}

        plan = plan_embeddings(facets, existing=existing)

        assert plan.call_count == 0
        assert len(plan.unchanged) == len(facets)

    def test_a_changed_item_is_re_embedded(self) -> None:
        facets = profile_facets(a_profile(), services=[], projects=[])
        stale = {f"{f.facet_kind.value}:{f.source_id or ''}": "a-different-hash" for f in facets}

        plan = plan_embeddings(facets, existing=stale)

        assert plan.call_count == len(facets)

    def test_a_brand_new_item_is_embedded(self) -> None:
        facets = profile_facets(a_profile(), services=[a_service("New thing")], projects=[])

        plan = plan_embeddings(facets, existing={})

        assert plan.call_count == len(facets)

    def test_two_services_with_the_same_text_stay_separate(self) -> None:
        """Identity is the row, not the text — otherwise one would mask the other."""
        first, second = a_service("Networking", "same"), a_service("Networking", "same")
        facets = profile_facets(
            a_profile(overview=None, sectors=[], geographies=[], keywords=[]),
            services=[first, second],
            projects=[],
        )

        plan = plan_embeddings(facets, existing={})

        assert plan.call_count == 2

    def test_tender_chunks_are_identified_by_kind(self) -> None:
        chunks = tender_chunks(a_tender())
        existing = {c.chunk_kind.value: c.hash for c in chunks}

        assert plan_embeddings(chunks, existing=existing).call_count == 0


class TestHashing:
    def test_surrounding_whitespace_does_not_change_the_hash(self) -> None:
        assert text_hash("  hello  ") == text_hash("hello")

    def test_different_text_hashes_differently(self) -> None:
        assert text_hash("a") != text_hash("b")


class TestEmbeddingCalls:
    async def test_profiles_are_embedded_as_queries_and_tenders_as_documents(self) -> None:
        """Getting the asymmetry backwards costs accuracy without ever failing."""
        client = FakeAIClient()
        facets = [FacetText(ProfileFacet.OVERVIEW, None, "Overview", "we do networking")]
        chunks = [ChunkText(EmbeddingChunk.TITLE_SUMMARY, "network switches", "Switches")]

        await embed_facets(facets, client=client)
        await embed_chunks(chunks, client=client)

        kinds = [call["kind"] for call in client.calls if call["op"] == "embed"]
        assert kinds == ["query", "document"]

    async def test_embedding_an_empty_list_makes_no_call(self) -> None:
        client = FakeAIClient()

        assert await embed_facets([], client=client) == []
        assert await embed_chunks([], client=client) == []
        assert client.calls == []
