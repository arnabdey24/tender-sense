"""The adapter contract and the change-detection hash.

`content_hash` decides whether a re-scraped notice counts as changed. Too
sensitive and every scrape re-runs extraction and re-scores the pool for every
customer; too blunt and a real amendment is missed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ingestion.adapters.base import (
    ADAPTERS,
    NoticeRef,
    TenderIn,
    get_adapter_class,
    register_adapter,
)
from app.modules.tenders.models import ProcurementCategory, TenderStatus


def make_tender(**overrides: object) -> TenderIn:
    defaults: dict[str, object] = {
        "external_id": "1331101",
        "canonical_url": "https://www.eprocure.gov.bd/resources/common/ViewTender.jsp?id=1331101",
        "title": "Supply and installation of solar water pumps",
        "summary": "Procurement of solar irrigation pumps for Rangpur division.",
        "procuring_entity": "Local Government Engineering Department",
        "country": "BD",
        "procurement_method": "OTM",
        "procurement_category": ProcurementCategory.GOODS,
        "deadline_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        "currency": "BDT",
        "estimated_value": 12_500_000.0,
    }
    defaults.update(overrides)
    return TenderIn(**defaults)  # type: ignore[arg-type]


class TestContentHash:
    def test_identical_notices_hash_alike(self) -> None:
        assert make_tender().content_hash() == make_tender().content_hash()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("title", "Supply of diesel pumps"),
            ("summary", "A different scope entirely."),
            ("procuring_entity", "Roads and Highways Department"),
            ("deadline_at", datetime(2026, 11, 1, 12, 0, tzinfo=UTC)),
            ("estimated_value", 20_000_000.0),
            ("procurement_method", "LTM"),
            ("status", TenderStatus.CANCELLED),
        ],
    )
    def test_a_meaningful_edit_changes_the_hash(self, field: str, value: object) -> None:
        assert make_tender().content_hash() != make_tender(**{field: value}).content_hash()

    def test_portal_metadata_does_not_change_the_hash(self) -> None:
        """Portals rewrite view counters and render timestamps on every request."""
        noisy = make_tender(portal_metadata={"rendered_at": "2026-09-09T10:00:00", "views": 41})

        assert noisy.content_hash() == make_tender().content_hash()

    def test_surrounding_whitespace_does_not_change_the_hash(self) -> None:
        padded = make_tender(title="  Supply and installation of solar water pumps  ")

        assert padded.content_hash() == make_tender().content_hash()

    def test_a_missing_value_differs_from_an_empty_one(self) -> None:
        assert make_tender(summary=None).content_hash() == make_tender(summary="").content_hash()


class TestDefaults:
    def test_a_notice_is_open_and_uncategorised_until_told_otherwise(self) -> None:
        tender = TenderIn(
            external_id="1", canonical_url="https://example.invalid/1", title="Something"
        )

        assert tender.status is TenderStatus.OPEN
        assert tender.procurement_category is ProcurementCategory.UNKNOWN

    def test_a_listing_reference_needs_only_an_identifier_and_url(self) -> None:
        ref = NoticeRef(external_id="OP00467471", url="https://example.invalid/OP00467471")

        assert ref.listing_data == {}


class TestRegistry:
    def test_an_adapter_is_resolvable_by_its_key(self) -> None:
        @register_adapter
        class FakePortal:
            key = "fake_portal_for_tests"

        try:
            assert get_adapter_class("fake_portal_for_tests") is FakePortal
        finally:
            ADAPTERS.pop("fake_portal_for_tests", None)

    def test_an_adapter_without_a_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="key"):

            @register_adapter
            class Keyless:
                pass

    def test_an_unknown_key_names_the_ones_that_exist(self) -> None:
        with pytest.raises(LookupError, match="Known:"):
            get_adapter_class("no_such_portal")
