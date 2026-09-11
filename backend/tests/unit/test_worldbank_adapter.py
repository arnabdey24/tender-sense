"""The World Bank adapter's normaliser, against real captured responses.

`normalize` is a pure function of bytes we already hold, which is the whole
point of the adapter contract: when the portal changes its shape, the parser is
fixed and replayed over stored payloads rather than re-scraped. These tests are
that replay.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.adapters.base import NoticeRef, RawDocument
from app.ingestion.adapters.worldbank import (
    DETAIL_URL,
    WorldBankAdapter,
    _html_to_text,
    _parse_date,
)
from app.ingestion.countries import country_code as _country_code
from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "worldbank" / "listing.json"


def notices() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text())["procnotices"]


def ref_for(row: dict[str, Any]) -> NoticeRef:
    return NoticeRef(
        external_id=str(row["id"]),
        url=DETAIL_URL.format(id=row["id"]),
        listing_data=row,
    )


def normalize(row: dict[str, Any]) -> Any:
    adapter = WorldBankAdapter()
    document = RawDocument(
        kind=DocumentKind.API_JSON,
        content=json.dumps(row, sort_keys=True).encode(),
    )
    return adapter.normalize(ref_for(row), [document])


class TestDateParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("08-Sep-2026", datetime(2026, 9, 8, tzinfo=UTC)),
            ("2026-09-08", datetime(2026, 9, 8, tzinfo=UTC)),
            ("2026-09-08T00:00:00Z", datetime(2026, 9, 8, tzinfo=UTC)),
        ],
    )
    def test_the_formats_the_portal_actually_uses(self, raw: str, expected: datetime) -> None:
        assert _parse_date(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "not a date", 12345, []])
    def test_anything_unparseable_is_none_rather_than_a_crash(self, raw: Any) -> None:
        """A single malformed date must not fail a whole scrape run."""
        assert _parse_date(raw) is None

    def test_every_parsed_date_is_timezone_aware(self) -> None:
        """A naive datetime would silently shift the deadline by the server's
        offset when compared against an org's timezone."""
        parsed = _parse_date("08-Sep-2026")

        assert parsed is not None
        assert parsed.tzinfo is not None


class TestHtmlToText:
    def test_markup_is_stripped(self) -> None:
        assert _html_to_text("<p>Hello <b>world</b></p>") == "Hello world"

    def test_whitespace_is_collapsed(self) -> None:
        assert _html_to_text("<p>a\n\n   b</p>") == "a b"

    def test_empty_markup_is_none_not_an_empty_string(self) -> None:
        """`None` means "nothing to embed"; "" would be embedded as noise."""
        assert _html_to_text("<div></div>") is None
        assert _html_to_text(None) is None


class TestCountryCodes:
    def test_a_known_country_maps_to_its_iso_code(self) -> None:
        assert _country_code("Sri Lanka") == "LK"
        assert _country_code("bangladesh") == "BD"

    def test_an_unknown_country_is_none_rather_than_a_guess(self) -> None:
        """A wrong code would silently fail a country-eligibility rule."""
        assert _country_code("Ruritania") is None
        assert _country_code(None) is None


class TestNormalize:
    def test_every_captured_notice_normalises(self) -> None:
        """The fixture is real data; all of it has to survive the parser."""
        for row in notices():
            tender = normalize(row)

            assert tender.external_id == str(row["id"])
            assert tender.title
            assert tender.canonical_url.endswith(str(row["id"]))

    def test_the_notice_body_becomes_plain_text(self) -> None:
        row = next(r for r in notices() if r.get("notice_text"))

        tender = normalize(row)

        assert tender.description
        assert "<" not in tender.description

    def test_a_contract_award_is_not_open_for_bidding(self) -> None:
        """Listing an already-awarded contract as open would waste the reader's
        attention on a decision that has already been made."""
        row = next((r for r in notices() if r.get("notice_type") == "Contract Award"), None)
        if row is None:
            pytest.skip("no contract award in the captured fixture")

        assert normalize(row).status is TenderStatus.CLOSED

    def test_an_open_notice_stays_open(self) -> None:
        row = next(
            (r for r in notices() if r.get("notice_type") == "Request for Expression of Interest"),
            None,
        )
        if row is None:
            pytest.skip("no live notice in the captured fixture")

        assert normalize(row).status is TenderStatus.OPEN

    def test_procurement_groups_map_to_categories(self) -> None:
        by_group = {r.get("procurement_group"): r for r in notices()}
        expected = {
            "GO": ProcurementCategory.GOODS,
            "CW": ProcurementCategory.WORKS,
            "CS": ProcurementCategory.CONSULTING,
        }
        for group, category in expected.items():
            if group in by_group:
                assert normalize(by_group[group]).procurement_category is category

    def test_an_unknown_group_is_not_guessed_into_a_category(self) -> None:
        """A rule filtering on category would silently act on the guess."""
        row = dict(notices()[0]) | {"procurement_group": "ZZ"}

        assert normalize(row).procurement_category is ProcurementCategory.UNKNOWN

    def test_a_missing_deadline_is_none_not_an_error(self) -> None:
        """The endpoint omits absent fields entirely rather than nulling them."""
        row = {k: v for k, v in notices()[0].items() if k != "submission_deadline_date"}

        assert normalize(row).deadline_at is None

    def test_portal_metadata_keeps_what_the_columns_cannot(self) -> None:
        row = notices()[0]

        metadata = normalize(row).portal_metadata

        assert metadata["project_id"] == row.get("project_id")
        assert metadata["notice_type"] == row.get("notice_type")
        assert isinstance(metadata["sectors"], list)

    def test_normalising_is_stable(self) -> None:
        """Same bytes, same row — otherwise re-processing would churn versions."""
        row = notices()[0]

        assert normalize(row).content_hash() == normalize(row).content_hash()

    def test_a_notice_with_almost_nothing_still_produces_a_row(self) -> None:
        """Better a thin tender than a scrape run that dies on one bad record."""
        tender = normalize({"id": "OP123"})

        assert tender.external_id == "OP123"
        assert tender.title
        assert tender.procurement_category is ProcurementCategory.UNKNOWN


class TestListing:
    async def test_it_yields_notices_newest_first(self) -> None:
        payload = json.loads(FIXTURE.read_text())
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        adapter = WorldBankAdapter(
            client=httpx.AsyncClient(transport=transport), config={"rows": 6}
        )

        found = [ref async for ref in adapter.list_notices(limit_pages=1)]

        assert len(found) == len(payload["procnotices"])
        assert found[0].external_id == str(payload["procnotices"][0]["id"])

    async def test_it_stops_at_a_notice_it_already_has(self) -> None:
        """The endpoint's date filters are unreliable, so this is what actually
        bounds a run."""
        payload = json.loads(FIXTURE.read_text())
        second_id = str(payload["procnotices"][1]["id"])
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        adapter = WorldBankAdapter(
            client=httpx.AsyncClient(transport=transport), config={"rows": 6}
        )

        found = [
            ref
            async for ref in adapter.list_notices(cursor={"seen_ids": [second_id]}, limit_pages=1)
        ]

        assert len(found) == 1

    async def test_an_empty_page_ends_the_run(self) -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"procnotices": []}))
        adapter = WorldBankAdapter(client=httpx.AsyncClient(transport=transport))

        assert [ref async for ref in adapter.list_notices(limit_pages=3)] == []

    async def test_the_field_list_is_always_sent(self) -> None:
        """Omitting it intermittently 500s, which is a miserable bug to chase."""
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"procnotices": []})

        adapter = WorldBankAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        [ref async for ref in adapter.list_notices(limit_pages=1)]

        assert "fl=" in str(seen[0].url)

    async def test_healthcheck_reports_an_unreachable_portal(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        adapter = WorldBankAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

        report = await adapter.healthcheck()

        assert report.reachable is False
        assert report.detail

    async def test_healthcheck_reports_a_healthy_portal(self) -> None:
        payload = json.loads(FIXTURE.read_text())
        adapter = WorldBankAdapter(
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
            )
        )

        assert (await adapter.healthcheck()).reachable is True


class TestFetchDetail:
    async def test_the_listing_row_is_stored_for_replay(self) -> None:
        """There is no detail page, but the bytes are kept anyway so a parser
        fix can be replayed exactly as for a scraped portal."""
        row = notices()[0]
        adapter = WorldBankAdapter()

        documents = await adapter.fetch_detail(ref_for(row))

        assert len(documents) == 1
        assert documents[0].kind is DocumentKind.API_JSON
        assert json.loads(documents[0].content.decode())["id"] == row["id"]
