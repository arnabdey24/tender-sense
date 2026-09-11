"""The ADB adapter's normaliser, against a real captured response.

Same contract as the World Bank tests: `normalize` is pure, so the parser can
be fixed and replayed over payloads already stored rather than re-scraped. The
fixture is an unedited SearchStax page — including the awkward parts, which are
the reason several of these assertions exist.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.adapters.adb import SITE_URL, AdbAdapter, _first, _node_id, _parse_date
from app.ingestion.adapters.base import NoticeRef, RawDocument
from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus

FIXTURE = Path(__file__).parent.parent / "fixtures" / "adb" / "listing.json"


def payload() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())


def docs() -> list[dict[str, Any]]:
    return payload()["response"]["docs"]


def normalize(doc: dict[str, Any]) -> Any:
    adapter = AdbAdapter()
    ref = NoticeRef(
        external_id=_node_id(doc) or "x",
        url=f"{SITE_URL}{doc['ss_url']}",
        listing_data=doc,
    )
    document = RawDocument(
        kind=DocumentKind.API_JSON, content=json.dumps(doc, sort_keys=True).encode()
    )
    return adapter.normalize(ref, [document])


def by_type(name: str) -> dict[str, Any]:
    for doc in docs():
        if (doc.get("tm_X3b_en_type") or [None])[0] == name:
            return doc
    raise AssertionError(f"fixture carries no {name!r} notice")


class TestSolrShapes:
    def test_multi_valued_fields_are_unwrapped(self) -> None:
        assert _first(["Bangladesh"]) == "Bangladesh"
        assert _first("Bangladesh") == "Bangladesh"

    @pytest.mark.parametrize("empty", [None, [], "", "   "])
    def test_absent_and_blank_read_as_none(self, empty: Any) -> None:
        assert _first(empty) is None

    def test_dates_parse(self) -> None:
        assert _parse_date("2026-11-02T12:00:00Z") == datetime(2026, 11, 2, 12, tzinfo=UTC)

    @pytest.mark.parametrize("bad", [None, "", "02 Nov 2026", "not-a-date"])
    def test_unparseable_dates_are_none_not_an_error(self, bad: Any) -> None:
        assert _parse_date(bad) is None


class TestIdentity:
    def test_external_id_is_the_node_id(self) -> None:
        assert _node_id({"ss_url": "/node/1174256"}) == "1174256"

    def test_solr_id_is_not_used_as_the_identity(self) -> None:
        """It embeds a build prefix, so a reindex would re-ingest the portal."""
        doc = dict(docs()[0])
        doc["id"] = "different-build-prefix-entity:node/1174256:en"
        assert normalize(doc).external_id == _node_id(doc)

    def test_a_notice_with_no_node_url_has_no_identity(self) -> None:
        assert _node_id({"ss_url": "/somewhere/else"}) is None

    def test_canonical_url_is_adbs_own_permalink(self) -> None:
        tender = normalize(docs()[0])
        assert tender.canonical_url == f"{SITE_URL}/node/{tender.external_id}"


class TestNormalisation:
    def test_every_fixture_row_normalises(self) -> None:
        for doc in docs():
            tender = normalize(doc)
            assert tender.title
            assert tender.external_id
            assert tender.canonical_url.startswith(SITE_URL)

    def test_consulting_notices_are_categorised(self) -> None:
        assert normalize(by_type("Firm")).procurement_category is ProcurementCategory.CONSULTING
        assert (
            normalize(by_type("Individual")).procurement_category is ProcurementCategory.CONSULTING
        )

    def test_a_bid_invitation_is_not_guessed_into_a_category(self) -> None:
        """Goods or works — the document does not say, and a rule may filter on it."""
        tender = normalize(by_type("Invitation for Bids"))
        assert tender.procurement_category is ProcurementCategory.UNKNOWN

    def test_active_is_open(self) -> None:
        assert normalize(docs()[0]).status is TenderStatus.OPEN

    def test_anything_not_active_is_closed(self) -> None:
        doc = dict(docs()[0])
        doc["tm_X3b_en_status"] = ["Closed"]
        assert normalize(doc).status is TenderStatus.CLOSED

    def test_country_names_map_to_iso_codes(self) -> None:
        found = {n.country for n in (normalize(d) for d in docs()) if n.country}
        assert "BD" in found

    def test_regional_notices_carry_no_country(self) -> None:
        """Not a country, so a country-eligibility rule must not match it."""
        doc = dict(docs()[0])
        doc["tm_X3b_en_country"] = ["Regional"]
        assert normalize(doc).country is None

    def test_summary_is_assembled_from_facets_not_invented(self) -> None:
        doc = by_type("Firm")
        summary = normalize(doc).summary or ""
        assert "Firm" in summary
        for part in doc.get("tm_X3b_en_sector") or []:
            assert part in summary

    def test_relative_document_links_are_absolute(self) -> None:
        tender = normalize(by_type("Invitation for Bids"))
        url = tender.portal_metadata.get("document_url")
        assert url is None or url.startswith("https://")

    def test_normalising_is_pure(self) -> None:
        doc = docs()[0]
        assert normalize(doc).content_hash() == normalize(doc).content_hash()


class TestListing:
    """The parts that touch HTTP, against a transport that never leaves the box."""

    def adapter(self, handler: Any) -> AdbAdapter:
        return AdbAdapter(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    @pytest.mark.anyio
    async def test_only_active_notices_are_requested(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.url.params)
            return httpx.Response(200, json=payload())

        async for _ in self.adapter(handler).list_notices(limit_pages=1):
            pass
        assert "Active" in seen["fq"]
        assert seen["sort"].startswith("ds_date_posted")

    @pytest.mark.anyio
    async def test_the_public_token_is_sent(self) -> None:
        headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            headers.update(request.headers)
            return httpx.Response(200, json=payload())

        async for _ in self.adapter(handler).list_notices(limit_pages=1):
            pass
        assert headers["authorization"].startswith("Token ")

    @pytest.mark.anyio
    async def test_a_configured_token_overrides_the_shipped_one(self) -> None:
        headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            headers.update(request.headers)
            return httpx.Response(200, json=payload())

        adapter = AdbAdapter(
            config={"token": "rotated"},
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        async for _ in adapter.list_notices(limit_pages=1):
            pass
        assert headers["authorization"] == "Token rotated"

    @pytest.mark.anyio
    async def test_iteration_stops_at_a_notice_already_held(self) -> None:
        first = _node_id(docs()[0])

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload())

        refs = [
            ref
            async for ref in self.adapter(handler).list_notices(
                cursor={"seen_ids": [first]}, limit_pages=1
            )
        ]
        assert refs == []

    @pytest.mark.anyio
    async def test_an_empty_page_ends_the_pass(self) -> None:
        calls = {"n": 0}

        def handler(_: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"response": {"numFound": 0, "docs": []}})

        async for _ in self.adapter(handler).list_notices(limit_pages=5):
            pass
        assert calls["n"] == 1

    @pytest.mark.anyio
    async def test_health_is_false_when_the_index_is_empty(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"response": {"numFound": 0, "docs": []}})

        report = await self.adapter(handler).healthcheck()
        assert report.reachable is False
        assert report.detail

    @pytest.mark.anyio
    async def test_health_reports_the_cause_rather_than_raising(self) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="challenge")

        report = await self.adapter(handler).healthcheck()
        assert report.reachable is False
        assert report.detail
