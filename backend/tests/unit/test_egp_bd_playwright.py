"""The browser fallback for e-GP.

It exists for the day the servlet stops answering plain HTTP clients, so the
things worth pinning are the ones that would rot silently until that day: that
it is registered, that it does not carry a second copy of the parser, and that
an image without Playwright says so instead of failing obscurely.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.adapters import ADAPTERS, build_adapter
from app.ingestion.adapters.base import NoticeRef, RawDocument
from app.ingestion.adapters.egp_bd import EgpBdAdapter
from app.ingestion.adapters.egp_bd_playwright import EgpBdPlaywrightAdapter
from app.modules.tenders.models import DocumentKind

FIXTURES = Path(__file__).parent.parent / "fixtures" / "egp_bd"


def detail_html() -> str:
    return (FIXTURES / "detail.html").read_text(encoding="utf-8", errors="replace")


class TestRegistration:
    def test_it_is_registered_under_its_own_key(self) -> None:
        assert ADAPTERS["egp_bd_playwright"] is EgpBdPlaywrightAdapter

    def test_switching_to_it_is_a_source_row_edit(self) -> None:
        """The whole point of the fallback: a config change, not a deploy."""
        adapter = build_adapter("egp_bd_playwright", base_url="https://portal.invalid")

        assert isinstance(adapter, EgpBdPlaywrightAdapter)
        assert adapter.base_url == "https://portal.invalid"


class TestParsingIsNotDuplicated:
    def test_normalize_produces_what_the_http_adapter_produces(self) -> None:
        """Two copies of this parser would drift the moment one was fixed."""
        ref = NoticeRef(external_id="12345", url="https://portal.invalid/x")
        documents = [RawDocument(kind=DocumentKind.DETAIL_HTML, content=detail_html().encode())]

        browser = EgpBdPlaywrightAdapter(base_url="https://portal.invalid")
        http = EgpBdAdapter(base_url="https://portal.invalid")

        assert browser.normalize(ref, documents) == http.normalize(ref, documents)

    def test_it_submits_the_same_form_fields(self) -> None:
        browser = EgpBdPlaywrightAdapter(config={"page_size": 25})

        assert browser._http_adapter.listing_form(2, None)["pageNo"] == "2"
        assert browser._http_adapter.listing_form(1, None)["size"] == "25"


class TestListingPayloadIsReplayable:
    def test_the_stored_listing_row_is_json(self) -> None:
        """It is kept so a parser fix can be replayed over it offline.

        A ``repr`` can only be read back by ``eval``, which would make the
        stored bytes useless for the one job they are stored for.
        """
        ref = NoticeRef(
            external_id="7",
            url="https://portal.invalid/7",
            listing_data={"id": "7", "title": "Supply of pumps"},
        )

        document = EgpBdAdapter.listing_document(ref)

        assert document.kind is DocumentKind.LISTING_ROW
        assert json.loads(document.content) == {"id": "7", "title": "Supply of pumps"}


class TestMissingPlaywright:
    async def test_a_health_probe_explains_how_to_install_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An image without the browser must say so, not time out mysteriously."""
        import builtins

        real_import = builtins.__import__

        def refuse(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("playwright"):
                raise ImportError("No module named 'playwright'")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", refuse)

        report = await EgpBdPlaywrightAdapter().healthcheck()

        assert report.reachable is False
        assert "uv sync --extra scrape" in (report.detail or "")
