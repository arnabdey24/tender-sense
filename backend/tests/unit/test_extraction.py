"""Reading requirements out of a notice."""

from __future__ import annotations

from app.ai.extraction import extract_attributes, extraction_input_hash, prompt_for
from app.ai.fake_client import FakeAIClient
from app.core.ids import new_id
from app.modules.tenders.models import ProcurementCategory, Tender


def tender(**overrides: object) -> Tender:
    defaults: dict[str, object] = {
        "id": new_id(),
        "external_id": "1331101",
        "canonical_url": "https://example.invalid/n/1",
        "title": "Supply and installation of enterprise network infrastructure",
        "summary": "Core switches, routers and structured cabling for a data centre.",
        "description": "Bidders must hold ISO 27001 and show three similar projects.",
        "procuring_entity": "Bangladesh Bank",
        "country": "BD",
        "procurement_category": ProcurementCategory.GOODS,
        "procurement_method": "Open Tendering Method",
    }
    return Tender(**(defaults | overrides))


class TestPrompt:
    def test_it_carries_the_fields_the_model_needs(self) -> None:
        text = prompt_for(tender())

        assert "enterprise network infrastructure" in text
        assert "Bangladesh Bank" in text
        assert "Open Tendering Method" in text

    def test_absent_fields_are_simply_left_out(self) -> None:
        text = prompt_for(tender(procuring_entity=None, description=None))

        assert "Procuring entity:" not in text
        assert "Notice text:" not in text


class TestInputHash:
    def test_the_same_notice_hashes_the_same(self) -> None:
        assert extraction_input_hash(tender()) == extraction_input_hash(tender())

    def test_an_edited_notice_hashes_differently(self) -> None:
        """This is what stops an unchanged notice being re-extracted daily."""
        original = extraction_input_hash(tender())
        amended = extraction_input_hash(tender(description="Now requires ISO 9001 as well."))

        assert original != amended

    def test_metadata_the_model_never_sees_does_not_change_the_hash(self) -> None:
        assert extraction_input_hash(tender()) == extraction_input_hash(
            tender(portal_metadata={"views": 41})
        )


class TestExtraction:
    async def test_it_returns_attributes_for_a_notice(self) -> None:
        outcome = await extract_attributes(tender(), client=FakeAIClient())

        assert outcome.succeeded
        assert outcome.attributes is not None
        assert outcome.error is None
        assert outcome.usage.tokens_in > 0

    async def test_a_failure_degrades_instead_of_raising(self) -> None:
        """A tender with no extraction must still be embeddable and matchable."""
        outcome = await extract_attributes(tender(), client=FakeAIClient(fail=True))

        assert not outcome.succeeded
        assert outcome.attributes is None
        assert outcome.error
        assert outcome.input_hash  # still recorded, so the attempt is traceable
