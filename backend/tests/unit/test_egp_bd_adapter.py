"""The e-GP Bangladesh parser, against real captured HTML.

This is the riskiest source in the system — an undocumented servlet on an old
JSP stack that changes without notice. These fixtures are the safety net: when
the markup moves, the parser is fixed and replayed here rather than debugged
against a live portal that is slow, rate limited, and drops closed notices.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.adapters.base import NoticeRef, RawDocument
from app.ingestion.adapters.egp_bd import (
    EgpBdAdapter,
    parse_datetime,
    parse_detail,
    parse_listing,
    parse_money,
    strip_leading_reference,
)
from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus

FIXTURES = Path(__file__).parent.parent / "fixtures" / "egp_bd"
LISTING = (FIXTURES / "listing.html").read_text(errors="replace")
DETAIL = (FIXTURES / "detail.html").read_text(errors="replace")


def rows() -> list[dict[str, Any]]:
    parsed, _ = parse_listing(LISTING)
    return parsed


def normalize(row: dict[str, Any], *, with_detail: bool = True) -> Any:
    documents = []
    if with_detail:
        documents.append(RawDocument(kind=DocumentKind.DETAIL_HTML, content=DETAIL.encode()))
    return EgpBdAdapter().normalize(
        NoticeRef(external_id=row["id"], url="https://x", listing_data=row), documents
    )


class TestListingParser:
    def test_it_finds_every_row(self) -> None:
        parsed, _ = parse_listing(LISTING)

        assert len(parsed) == 10

    def test_it_reads_the_page_count(self) -> None:
        """Without it a run has no idea when to stop walking pages."""
        _, total_pages = parse_listing(LISTING)

        assert total_pages == 361

    def test_the_identifier_comes_from_the_hidden_field(self) -> None:
        """Sturdier than positional text parsing, which the portal reorders."""
        first = rows()[0]

        assert first["id"].isdigit()

    def test_a_row_carries_the_fields_the_matcher_needs(self) -> None:
        first = rows()[0]

        assert first["title"]
        assert first["reference_no"]
        assert first["procurement_nature"] == "Works"
        assert first["status"] == "Live"
        assert first["ministry"].startswith("Ministry")
        assert first["published_at"]
        assert first["closing_at"]

    def test_empty_html_yields_nothing_rather_than_failing(self) -> None:
        """An empty result page is normal, not an error."""
        parsed, pages = parse_listing("")

        assert parsed == []
        assert pages == 1

    def test_a_malformed_row_is_skipped_not_fatal(self) -> None:
        """One broken row must not cost the other ninety-nine."""
        parsed, _ = parse_listing("<tr><td>only one cell</td></tr>" + LISTING)

        assert len(parsed) == 10

    def test_a_row_without_an_identifier_is_skipped(self) -> None:
        cells = "".join(f"<td>{i}</td>" for i in range(6))
        parsed, _ = parse_listing(f"<tr>{cells}</tr>")

        assert parsed == []


class TestDetailParser:
    def test_it_reads_the_label_value_table(self) -> None:
        fields = parse_detail(DETAIL)

        assert len(fields) > 30
        assert fields["Ministry"] == "Ministry of Agriculture"
        assert fields["Procurement Method"].startswith("Open Tendering")

    def test_it_survives_markup_that_is_not_the_detail_page(self) -> None:
        assert parse_detail("<html><body>nothing here</body></html>") == {}


class TestDateParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("10-Sep-2026 12:10", datetime(2026, 9, 10, 12, 10, tzinfo=UTC)),
            ("10-Sep-2026", datetime(2026, 9, 10, tzinfo=UTC)),
            ("10/09/2026 12:10", datetime(2026, 9, 10, 12, 10, tzinfo=UTC)),
        ],
    )
    def test_the_formats_the_portal_uses(self, raw: str, expected: datetime) -> None:
        assert parse_datetime(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", "not a date", "32-Xxx-2026"])
    def test_anything_else_is_none_rather_than_a_crash(self, raw: str) -> None:
        assert parse_datetime(raw) is None

    def test_dates_are_timezone_aware(self) -> None:
        """A naive value would drift against an org's local deadline maths."""
        parsed = parse_datetime("10-Sep-2026 12:10")

        assert parsed is not None and parsed.tzinfo is not None


class TestMoneyParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"), [("1000", 1000.0), ("BDT 1,000", 1000.0), ("1000.50", 1000.5)]
    )
    def test_it_reads_an_amount(self, raw: str, expected: float) -> None:
        assert parse_money(raw) == expected

    @pytest.mark.parametrize("raw", ["", "Package wise", "—"])
    def test_a_non_numeric_value_is_none(self, raw: str) -> None:
        assert parse_money(raw) is None


class TestReferenceStripping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (
                "PD/CCDIDP/2026-2027/e-GP/Works-43.36 Construction of a bridge",
                "Construction of a bridge",
            ),
            ("LGED/CH/2026/W-12 Repair of a road", "Repair of a road"),
        ],
    )
    def test_a_leading_reference_code_is_dropped(self, raw: str, expected: str) -> None:
        """A reference shares no vocabulary with anything a company says about
        itself, so leaving it in the title is pure noise in the embedding."""
        assert strip_leading_reference(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "Construction of a road",
            "Supply and/or installation of pumps",  # "and/or" has no digit
            "P-123/2026",  # nothing follows it, so it *is* the title
        ],
    )
    def test_ordinary_titles_are_left_alone(self, raw: str) -> None:
        assert strip_leading_reference(raw) == raw


class TestNormalize:
    def test_the_detail_page_supplies_the_richer_fields(self) -> None:
        tender = normalize(rows()[0])

        assert tender.title.startswith("Construction of small size irrigation")
        assert tender.procuring_entity
        assert tender.description
        assert tender.procurement_method.startswith("Open Tendering")

    def test_it_is_usable_from_the_listing_row_alone(self) -> None:
        """A detail fetch that fails must not cost us the notice."""
        tender = normalize(rows()[0], with_detail=False)

        assert tender.external_id == rows()[0]["id"]
        assert tender.title
        assert tender.deadline_at is not None
        assert tender.procurement_category is ProcurementCategory.WORKS

    def test_the_closing_date_is_the_deadline(self) -> None:
        """The portal publishes several dates; only this one is what a bidder
        is racing, so a countdown against any other would mislead."""
        tender = normalize(rows()[0])

        assert tender.deadline_at == datetime(2026, 9, 24, 12, 0, tzinfo=UTC)

    def test_a_live_notice_is_open(self) -> None:
        assert normalize(rows()[0]).status is TenderStatus.OPEN

    def test_an_unrecognised_status_is_not_assumed_open(self) -> None:
        """Showing a withdrawn notice as biddable wastes a bidder's week."""
        row = dict(rows()[0]) | {"status": "Something New"}

        assert normalize(row, with_detail=False).status is TenderStatus.UNKNOWN

    def test_the_summary_does_not_fall_back_to_the_notice_type(self) -> None:
        """ "Tender - Single Lot" is a category, not a summary.

        It used to be used as one whenever the portal omitted "Invitation
        for", which put the notice type under a heading that promises prose
        and made every such tender page read as padding. The nature is already
        carried as ``procurement_category``, so leaving this null loses
        nothing and lets the interface show absent as absent.
        """
        tender = normalize(rows()[0], with_detail=False)

        assert tender.summary is None
        assert tender.procurement_category is ProcurementCategory.WORKS

    def test_an_unrecognised_nature_is_not_guessed(self) -> None:
        row = dict(rows()[0]) | {"procurement_nature": "Mystery"}

        assert normalize(row, with_detail=False).procurement_category is ProcurementCategory.UNKNOWN

    def test_every_notice_is_bangladeshi_and_priced_in_taka(self) -> None:
        tender = normalize(rows()[0])

        assert tender.country == "BD"
        assert tender.currency == "BDT"

    def test_portal_metadata_keeps_what_the_columns_cannot(self) -> None:
        metadata = normalize(rows()[0]).portal_metadata

        assert metadata["reference_no"]
        assert metadata["ministry"] == "Ministry of Agriculture"
        assert metadata["document_price_bdt"] == 1000.0

    def test_normalising_is_stable(self) -> None:
        """Same bytes, same row — otherwise every scrape bumps the version."""
        assert normalize(rows()[0]).content_hash() == normalize(rows()[0]).content_hash()

    def test_every_captured_row_normalises(self) -> None:
        for row in rows():
            tender = normalize(row, with_detail=False)

            assert tender.external_id
            assert tender.title
            assert tender.canonical_url.endswith(row["id"])


class TestListingRequests:
    def _adapter(self, handler: Any) -> EgpBdAdapter:
        return EgpBdAdapter(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            # No sleeping in tests; politeness is exercised by its own test.
            config={"request_delay_seconds": 0, "page_size": 10},
        )

    async def test_it_yields_the_rows_it_finds(self) -> None:
        adapter = self._adapter(lambda _: httpx.Response(200, text=LISTING))

        found = [ref async for ref in adapter.list_notices(limit_pages=1)]

        assert len(found) == 10
        assert found[0].external_id == rows()[0]["id"]

    async def test_it_stops_at_a_notice_it_already_has(self) -> None:
        adapter = self._adapter(lambda _: httpx.Response(200, text=LISTING))
        second = rows()[1]["id"]

        found = [
            ref async for ref in adapter.list_notices(cursor={"seen_ids": [second]}, limit_pages=1)
        ]

        assert len(found) == 1

    async def test_it_posts_the_form_the_servlet_expects(self) -> None:
        """Every field has to be present; the servlet does not tolerate gaps."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, text="")

        adapter = self._adapter(handler)
        [ref async for ref in adapter.list_notices(limit_pages=1)]

        body = seen[0].content.decode()
        assert seen[0].method == "POST"
        for field in ("funName=AllTenders", "viewType=Live", "pageNo=1", "h=t"):
            assert field in body

    async def test_it_does_not_walk_past_the_last_page(self) -> None:
        pages: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            pages.append(request.content.decode())
            # One page in total, so a second request would be pointless load on
            # a government portal.
            return httpx.Response(
                200,
                text=LISTING.replace('id="totalPages" value="361"', 'id="totalPages" value="1"'),
            )

        adapter = self._adapter(handler)
        [ref async for ref in adapter.list_notices(limit_pages=20)]

        assert len(pages) == 1

    async def test_healthcheck_reports_an_unreachable_portal(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        report = await self._adapter(handler).healthcheck()

        assert report.reachable is False
        assert report.detail

    async def test_healthcheck_reports_a_healthy_portal(self) -> None:
        adapter = self._adapter(lambda _: httpx.Response(200, text=LISTING))

        assert (await adapter.healthcheck()).reachable is True


class TestFetchDetail:
    async def test_it_keeps_the_listing_row_alongside_the_detail(self) -> None:
        adapter = EgpBdAdapter(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, text=DETAIL))
            ),
            config={"request_delay_seconds": 0},
        )
        ref = NoticeRef(external_id="1", url="https://x", listing_data=rows()[0])

        documents = await adapter.fetch_detail(ref)

        kinds = {document.kind for document in documents}
        assert DocumentKind.LISTING_ROW in kinds
        assert DocumentKind.DETAIL_HTML in kinds

    async def test_a_failed_detail_still_returns_the_listing_row(self) -> None:
        """The notice survives on what the listing already gave us."""

        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("timeout")

        adapter = EgpBdAdapter(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            config={"request_delay_seconds": 0},
        )
        ref = NoticeRef(external_id="1", url="https://x", listing_data=rows()[0])

        documents = await adapter.fetch_detail(ref)

        assert [document.kind for document in documents] == [DocumentKind.LISTING_ROW]
