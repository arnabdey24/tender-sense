"""The AI abstraction and its deterministic fake.

The fake is load-bearing: every matching test downstream trusts that the same
text always yields the same vector, and that related text scores higher than
unrelated text. Those two properties are asserted here so a change to the fake
cannot quietly invalidate the matching suite.
"""

from __future__ import annotations

import math

import pytest

from app.ai import build_client, get_ai_client, set_ai_client
from app.ai.base import AIClient, AIError, AIUsageTally, Usage, document_text, query_text
from app.ai.fake_client import FakeAIClient, deterministic_embedding
from app.ai.schemas import FieldEvidence, MatchExplanation, Sector, TenderAttributes


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class TestPrefixes:
    def test_documents_and_queries_are_prefixed_differently(self) -> None:
        """`gemini-embedding-2` takes no task_type, so the asymmetry lives here."""
        assert document_text("Title", "Body") != query_text("Title Body")
        assert "title:" in document_text("Title", "Body")
        assert "query:" in query_text("anything")

    def test_a_missing_title_still_produces_valid_text(self) -> None:
        assert document_text(None, "body") == "title:  | text: body"


class TestDeterminism:
    def test_the_same_text_always_gives_the_same_vector(self) -> None:
        first = deterministic_embedding("network infrastructure upgrade", 768)
        second = deterministic_embedding("network infrastructure upgrade", 768)

        assert first == second

    def test_vectors_are_unit_length(self) -> None:
        """pgvector's cosine distance assumes it."""
        vector = deterministic_embedding("supply of laptops", 768)

        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)

    def test_an_empty_string_still_yields_a_unit_vector(self) -> None:
        vector = deterministic_embedding("", 768)

        assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)

    def test_related_text_scores_above_unrelated_text(self) -> None:
        """The property the matching tests are actually built on."""
        profile = deterministic_embedding(
            "systems integration network infrastructure data centre", 768
        )
        related = deterministic_embedding(
            "supply and installation of enterprise network infrastructure", 768
        )
        unrelated = deterministic_embedding("printing of textbooks for primary education", 768)

        assert cosine(profile, related) > cosine(profile, unrelated)

    def test_dimension_count_is_honoured(self) -> None:
        assert len(deterministic_embedding("x", 256)) == 256


class TestFakeClient:
    async def test_it_satisfies_the_client_protocol(self) -> None:
        assert isinstance(FakeAIClient(), AIClient)

    async def test_embedding_documents_returns_one_vector_per_text(self) -> None:
        client = FakeAIClient(dims=768)

        result = await client.embed_documents(["a", "b"], titles=["A", "B"])

        assert len(result.vectors) == 2
        assert result.dims == 768
        assert result.model == client.embedding_model

    async def test_extraction_reads_sectors_out_of_the_text(self) -> None:
        """Otherwise every matching assertion downstream is against noise."""
        client = FakeAIClient()

        result = await client.generate_structured(
            prompt="Supply and installation of a network management system",
            schema=TenderAttributes,
        )

        assert Sector.IT in result.parsed.sectors

    async def test_extraction_is_stable_across_calls(self) -> None:
        client = FakeAIClient()
        prompt = "Construction of a rural bridge"

        first = await client.generate_structured(prompt=prompt, schema=TenderAttributes)
        second = await client.generate_structured(prompt=prompt, schema=TenderAttributes)

        assert first.parsed.model_dump() == second.parsed.model_dump()

    async def test_it_can_produce_an_explanation(self) -> None:
        client = FakeAIClient()

        result = await client.generate_structured(prompt="why?", schema=MatchExplanation)

        assert result.parsed.summary

    async def test_the_failure_switch_raises_on_embedding(self) -> None:
        """Exercises the degraded path without needing a broken network."""
        client = FakeAIClient(fail=True)

        with pytest.raises(AIError):
            await client.embed_documents(["a"])

    async def test_the_failure_switch_raises_on_generation(self) -> None:
        client = FakeAIClient(fail=True)

        with pytest.raises(AIError):
            await client.generate_structured(prompt="a", schema=TenderAttributes)

    async def test_calls_are_recorded_for_assertions(self) -> None:
        client = FakeAIClient()

        await client.embed_queries(["hello"])

        assert client.calls == [{"op": "embed", "kind": "query", "count": 1}]


class TestAttributes:
    def test_a_missing_field_reads_as_unknown(self) -> None:
        attributes = TenderAttributes()

        assert attributes.confidence_for("min_annual_turnover") == 0.0
        assert not attributes.is_reliable("min_annual_turnover")

    def test_low_confidence_is_not_reliable(self) -> None:
        """Below the floor an attribute must become "verify", never a rejection."""
        attributes = TenderAttributes(
            field_evidence=[FieldEvidence(field="jv_allowed", confidence=0.4)]
        )

        assert not attributes.is_reliable("jv_allowed")

    def test_confident_fields_are_reliable(self) -> None:
        attributes = TenderAttributes(
            field_evidence=[FieldEvidence(field="jv_allowed", confidence=0.9)]
        )

        assert attributes.is_reliable("jv_allowed")

    def test_the_evidence_list_rebuilds_the_maps_the_pipeline_wants(self) -> None:
        """Stored as a list only because Gemini rejects open-ended dicts."""
        attributes = TenderAttributes(
            field_evidence=[
                FieldEvidence(field="jv_allowed", confidence=0.9, quote="JV permitted"),
                FieldEvidence(field="bid_security", confidence=0.3),
            ]
        )

        assert attributes.confidence_map() == {"jv_allowed": 0.9, "bid_security": 0.3}
        # A field with no quote contributes no evidence, rather than an empty one.
        assert attributes.evidence_map() == {"jv_allowed": "JV permitted"}

    def test_the_response_schema_has_no_open_ended_maps(self) -> None:
        """The Gemini Developer API rejects `additionalProperties` outright."""
        import json

        schema = json.dumps(TenderAttributes.model_json_schema())

        assert "additionalProperties" not in schema


class TestUsageTally:
    def test_it_sums_across_models(self) -> None:
        tally = AIUsageTally()

        tally.add(Usage(model="embed", tokens_in=10))
        tally.add(Usage(model="gen", tokens_in=5, tokens_out=20))

        assert tally.calls == 2
        assert tally.total_tokens == 35
        assert tally.by_model == {"embed": 10, "gen": 25}


class TestClientSelection:
    def test_fake_is_used_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "ai_provider", "fake")

        assert isinstance(build_client(), FakeAIClient)

    def test_gemini_without_a_key_falls_back_to_the_fake(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh checkout must run end to end before anyone has a key."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        assert isinstance(build_client(), FakeAIClient)

    def test_the_cached_client_can_be_overridden(self) -> None:
        injected = FakeAIClient(dims=8)
        set_ai_client(injected)
        try:
            assert get_ai_client() is injected
        finally:
            set_ai_client(None)
