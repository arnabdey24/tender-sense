"""Contract tests against the real Gemini API.

Excluded from every normal run (`-m "not live"`). Run them deliberately when a
model id changes or a call starts behaving oddly:

    GEMINI_API_KEY=... uv run pytest -m live

They exist because the things most likely to break here are facts about
someone else's API — which model ids resolve, whether a truncated vector comes
back normalised, and which JSON Schema features the Developer API accepts —
and none of that is observable from a mock.
"""

from __future__ import annotations

import math

import pytest

from app.ai.base import AIError
from app.ai.gemini_client import GeminiClient
from app.ai.schemas import MatchExplanation, TenderAttributes
from app.core.config import settings

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def api_key() -> str:
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY is not set")
    return settings.gemini_api_key.get_secret_value()


NOTICE = (
    "Supply and installation of enterprise network switches for Bangladesh Bank. "
    "Bidders must hold ISO 27001 certification and demonstrate an average annual "
    "turnover of at least BDT 50,000,000 over the last three financial years. "
    "Joint ventures are permitted. Bid security of BDT 1,500,000 is required."
)


class TestEmbeddings:
    @pytest.mark.parametrize(
        "model", ["gemini-embedding-2", "gemini-embedding-2-preview", "gemini-embedding-001"]
    )
    async def test_the_configured_model_ids_all_resolve(self, api_key: str, model: str) -> None:
        """Model-id churn is a named risk; this is how we find out early."""
        client = GeminiClient(api_key=api_key, embedding_model=model, dims=768)

        result = await client.embed_documents(["network infrastructure"], titles=["Test"])

        assert len(result.vectors[0]) == 768

    async def test_a_truncated_vector_comes_back_unit_length(self, api_key: str) -> None:
        """pgvector's cosine distance depends on it."""
        client = GeminiClient(api_key=api_key, dims=768)

        result = await client.embed_documents(["network infrastructure"], titles=["Test"])

        norm = math.sqrt(sum(x * x for x in result.vectors[0]))
        assert math.isclose(norm, 1.0, rel_tol=1e-5)

    async def test_documents_and_queries_can_both_be_embedded(self, api_key: str) -> None:
        client = GeminiClient(api_key=api_key, dims=768)

        documents = await client.embed_documents(["a data centre upgrade"], titles=["Net"])
        queries = await client.embed_queries(["data centre integration"])

        assert len(documents.vectors) == len(queries.vectors) == 1

    async def test_related_text_outscores_unrelated_text(self, api_key: str) -> None:
        """The premise of the whole product, checked against the real model."""
        client = GeminiClient(api_key=api_key, dims=768)

        profile = (await client.embed_queries(["systems integration and networking"])).vectors[0]
        result = await client.embed_documents(
            [
                "supply and installation of enterprise network switches",
                "printing of textbooks for primary schools",
            ],
            titles=["Network switches", "Textbook printing"],
        )
        related, unrelated = result.vectors

        def cosine(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=True))

        assert cosine(profile, related) > cosine(profile, unrelated)

    async def test_a_batch_returns_one_vector_per_text(self, api_key: str) -> None:
        """The bug this caught: `gemini-embedding-2` collapses a batch to one.

        Given a list of contents it returns a single embedding and no error, so
        a naive batched call pairs the wrong vector with the wrong chunk and
        every match score downstream is quietly wrong. The client now fans out
        one request per text for any model not in `_BATCHING_MODELS`.
        """
        client = GeminiClient(api_key=api_key, dims=768)

        result = await client.embed_documents(
            ["first text about routers", "second text about school textbooks"],
            titles=["One", "Two"],
        )

        assert len(result.vectors) == 2
        assert result.vectors[0] != result.vectors[1]

    async def test_the_raw_api_still_collapses_batches_for_the_default_model(
        self, api_key: str
    ) -> None:
        """Pins the upstream behaviour, so we notice if Google ever fixes it."""
        from google import genai
        from google.genai import types

        raw = genai.Client(api_key=api_key)
        response = await raw.aio.models.embed_content(
            model="gemini-embedding-2",
            contents=["one", "two", "three"],
            config=types.EmbedContentConfig(output_dimensionality=768),
        )

        assert len(response.embeddings or []) == 1, (
            "gemini-embedding-2 now batches; add it to _BATCHING_MODELS"
        )

    async def test_embedding_nothing_is_an_error_not_a_call(self, api_key: str) -> None:
        client = GeminiClient(api_key=api_key)

        with pytest.raises(AIError):
            await client.embed_documents([])


class TestStructuredGeneration:
    @pytest.mark.parametrize("model", ["gemini-3.1-flash-lite", "gemini-2.5-flash-lite"])
    async def test_extraction_reads_the_stated_requirements(self, api_key: str, model: str) -> None:
        """Also proves the response schema stays inside what the API accepts.

        `TenderAttributes` originally carried `dict[str, float]` maps for
        confidence and evidence; pydantic renders those as
        `additionalProperties`, which the Developer API rejects.
        """
        client = GeminiClient(api_key=api_key, generation_model=model)

        result = await client.generate_structured(
            prompt=f"Extract the attributes of this notice.\n\n{NOTICE}",
            schema=TenderAttributes,
        )

        parsed = result.parsed
        assert parsed.min_annual_turnover is not None
        assert parsed.min_annual_turnover.amount == pytest.approx(50_000_000)
        assert parsed.min_annual_turnover.currency == "BDT"
        assert any("27001" in cert for cert in parsed.required_certifications)
        assert result.usage.tokens_out > 0

    async def test_it_reports_confidence_and_evidence_per_field(self, api_key: str) -> None:
        """Without these the rule engine cannot refuse to act on a guess."""
        client = GeminiClient(api_key=api_key)

        result = await client.generate_structured(
            prompt=f"Extract the attributes of this notice.\n\n{NOTICE}",
            schema=TenderAttributes,
        )

        confidence = result.parsed.confidence_map()
        assert confidence, "model returned no per-field confidence"
        assert all(0.0 <= score <= 1.0 for score in confidence.values())
        assert result.parsed.evidence_map(), "model returned no supporting quotes"

    async def test_it_does_not_invent_requirements_that_are_not_stated(self, api_key: str) -> None:
        """A hallucinated requirement makes a winnable tender look ineligible."""
        client = GeminiClient(api_key=api_key)

        result = await client.generate_structured(
            prompt=(
                "Extract the attributes of this notice.\n\n"
                "Supply of 200 office chairs to a district council. "
                "Sealed bids by 30 June."
            ),
            schema=TenderAttributes,
        )

        parsed = result.parsed
        assert parsed.required_certifications == []
        assert parsed.min_annual_turnover is None or parsed.min_annual_turnover.amount is None

    async def test_an_explanation_can_be_generated(self, api_key: str) -> None:
        client = GeminiClient(api_key=api_key)

        result = await client.generate_structured(
            prompt=(
                "A Dhaka systems integrator with ISO 27001 and BDT 200m turnover is "
                f"considering this tender. Explain the fit.\n\n{NOTICE}"
            ),
            schema=MatchExplanation,
        )

        assert result.parsed.summary


class TestHealthcheck:
    async def test_a_good_key_reports_healthy(self, api_key: str) -> None:
        assert await GeminiClient(api_key=api_key).healthcheck() is True

    async def test_a_bad_key_reports_unhealthy_rather_than_raising(self) -> None:
        assert await GeminiClient(api_key="not-a-real-key").healthcheck() is False
