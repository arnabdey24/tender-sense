"""The scrape job, mostly through its failure paths.

The happy path is easy. What matters is that a portal having a bad day costs us
some notices rather than the whole run, and that a portal that has genuinely
broken becomes visible instead of looking like a quiet week.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.ingestion.adapters import build_adapter
from app.ingestion.adapters.base import ADAPTERS, NoticeRef, RawDocument, SourceHealthReport
from app.ingestion.adapters.worldbank import WorldBankAdapter
from app.ingestion.blobstore import LocalFileBlobStore
from app.ingestion.service import upsert_tender
from app.jobs.runs import RunStatus, ScraperRun
from app.jobs.tasks.scraping import scrape_due_sources, scrape_source
from app.modules.tenders.models import SourceHealth, Tender, TenderDocument, TenderSource

FIXTURE = Path(__file__).parent.parent / "fixtures" / "worldbank" / "listing.json"


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"wb-{uuid4().hex[:8]}",
        name="World Bank (test)",
        adapter_key="worldbank",
        base_url="https://portal.invalid",
        config={"rows": 6, "max_pages": 1},
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


async def reload(source_id: Any) -> TenderSource | None:
    async with session_scope() as session:
        return await session.get(TenderSource, source_id)


async def runs_for(source_id: Any) -> list[ScraperRun]:
    async with session_scope() as session:
        rows = await session.scalars(
            select(ScraperRun)
            .where(ScraperRun.source_id == source_id)
            .order_by(ScraperRun.started_at.desc())
        )
        return list(rows.all())


class FakeAdapter:
    """An adapter whose behaviour a test dictates outright."""

    key = "fake_portal"

    #: Set by each test before the job builds one.
    notices: list[dict[str, Any]] = []
    detail_error_after: int | None = None
    listing_error: bool = False

    def __init__(self, **_: Any) -> None:
        self._served = 0

    async def list_notices(self, **_: Any) -> AsyncIterator[NoticeRef]:
        if type(self).listing_error:
            raise httpx.ConnectError("portal refused the connection")
        for row in type(self).notices:
            yield NoticeRef(
                external_id=row["id"], url=f"https://portal.invalid/{row['id']}", listing_data=row
            )

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        limit = type(self).detail_error_after
        if limit is not None and self._served >= limit:
            raise httpx.ReadTimeout("detail page timed out")
        self._served += 1
        return []

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> Any:
        from app.ingestion.adapters.base import TenderIn

        return TenderIn(
            external_id=ref.external_id,
            canonical_url=ref.url,
            title=ref.listing_data.get("title", f"Notice {ref.external_id}"),
        )

    async def healthcheck(self) -> SourceHealthReport:
        return SourceHealthReport(reachable=not type(self).listing_error)


@pytest.fixture
def fake_portal() -> AsyncIterator[type[FakeAdapter]]:
    ADAPTERS["fake_portal"] = FakeAdapter
    FakeAdapter.notices = []
    FakeAdapter.detail_error_after = None
    FakeAdapter.listing_error = False
    yield FakeAdapter
    ADAPTERS.pop("fake_portal", None)


@pytest.fixture
async def fake_source(fake_portal: type[FakeAdapter]) -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"fake-{uuid4().hex[:8]}",
        name="Fake portal",
        adapter_key="fake_portal",
        base_url="https://portal.invalid",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


class TestBuildAdapter:
    def test_it_builds_the_adapter_a_source_names(self) -> None:
        adapter = build_adapter("worldbank", base_url="https://x", config={"rows": 5})

        assert isinstance(adapter, WorldBankAdapter)
        assert adapter.base_url == "https://x"

    def test_an_empty_base_url_leaves_the_adapter_its_default(self) -> None:
        """Passing None would hand the adapter nothing instead of its default."""
        adapter = build_adapter("worldbank", base_url="", config={})

        assert adapter.base_url.startswith("https://")

    def test_an_unknown_adapter_key_is_a_clear_error(self) -> None:
        """The message names what *is* known, so a typo is obvious."""
        with pytest.raises(LookupError, match="Unknown adapter 'not_a_portal'"):
            build_adapter("not_a_portal")

    def test_every_shipped_adapter_is_registered_by_importing_the_package(self) -> None:
        """The API resolves adapters too, for health probes and validation.

        Registration happens by import side effect, so a process that never
        imported these modules sees an empty registry and reports every portal
        unreachable — which is why the package does the importing, not the
        entrypoint that happened to remember.
        """
        assert {"worldbank", "egp_bd", "egp_bd_playwright"} <= set(ADAPTERS)


class TestScrapeRun:
    async def test_a_successful_run_stores_notices_and_records_itself(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        fake_portal.notices = [
            {"id": f"n-{uuid4().hex[:8]}", "title": "Supply of switches"},
            {"id": f"n-{uuid4().hex[:8]}", "title": "Road works"},
        ]

        result = await scrape_source({}, str(fake_source.id))

        assert result["created"] == 2
        assert result["failed"] == 0
        runs = await runs_for(fake_source.id)
        assert runs[0].status is RunStatus.SUCCEEDED
        assert runs[0].notices_seen == 2
        assert runs[0].finished_at is not None

    async def test_a_healthy_run_marks_the_source_ok(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        fake_portal.notices = [{"id": f"n-{uuid4().hex[:8]}", "title": "A notice"}]

        await scrape_source({}, str(fake_source.id))

        fresh = await reload(fake_source.id)
        assert fresh is not None
        assert fresh.health is SourceHealth.OK
        assert fresh.consecutive_failures == 0
        assert fresh.last_success_at is not None

    async def test_rerunning_leaves_unchanged_notices_alone(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        """A daily scrape must not re-run the language model over the same pool."""
        fake_portal.notices = [{"id": f"n-{uuid4().hex[:8]}", "title": "A notice"}]

        first = await scrape_source({}, str(fake_source.id))
        second = await scrape_source({}, str(fake_source.id))

        assert first["created"] == 1
        assert second["created"] == 0
        assert second["unchanged"] == 1

    async def test_one_broken_notice_does_not_cost_the_others(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        fake_portal.notices = [
            {"id": f"n-{uuid4().hex[:8]}", "title": f"Notice {i}"} for i in range(4)
        ]
        fake_portal.detail_error_after = 2  # the third and fourth fail

        result = await scrape_source({}, str(fake_source.id))

        assert result["created"] == 2
        assert result["failed"] == 2
        runs = await runs_for(fake_source.id)
        # Finished, but lossy: worth seeing, not worth alerting.
        assert runs[0].status is RunStatus.PARTIAL

    async def test_it_gives_up_after_enough_consecutive_failures(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        """A portal that has started refusing us will not relent because we
        asked forty more times."""
        fake_portal.notices = [
            {"id": f"n-{uuid4().hex[:8]}", "title": f"Notice {i}"} for i in range(40)
        ]
        fake_portal.detail_error_after = 0

        result = await scrape_source({}, str(fake_source.id))

        assert result["failed"] == 5
        assert "consecutive failures" in result["error"]

    async def test_a_listing_failure_marks_the_source_degraded(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        fake_portal.listing_error = True

        await scrape_source({}, str(fake_source.id))

        fresh = await reload(fake_source.id)
        assert fresh is not None
        assert fresh.health is SourceHealth.DEGRADED
        assert fresh.consecutive_failures == 1

    async def test_repeated_failures_mark_the_source_down(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        """One timeout is weather; three in a row is a broken portal."""
        fake_portal.listing_error = True

        for _ in range(3):
            await scrape_source({}, str(fake_source.id))

        fresh = await reload(fake_source.id)
        assert fresh is not None
        assert fresh.health is SourceHealth.DOWN

    async def test_recovering_clears_the_failure_count(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        fake_portal.listing_error = True
        await scrape_source({}, str(fake_source.id))

        fake_portal.listing_error = False
        fake_portal.notices = [{"id": f"n-{uuid4().hex[:8]}", "title": "Back up"}]
        await scrape_source({}, str(fake_source.id))

        fresh = await reload(fake_source.id)
        assert fresh is not None
        assert fresh.health is SourceHealth.OK
        assert fresh.consecutive_failures == 0

    async def test_a_disabled_source_is_not_scraped(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        async with session_scope() as session:
            fresh = await session.get(TenderSource, fake_source.id)
            assert fresh is not None
            fresh.enabled = False

        result = await scrape_source({}, str(fake_source.id))

        assert result["error"] == "source_disabled"
        assert await runs_for(fake_source.id) == []

    async def test_an_unknown_source_returns_cleanly(self) -> None:
        result = await scrape_source({}, str(uuid4()))

        assert result["error"] == "source_not_found"

    async def test_an_unregistered_adapter_fails_the_run_visibly(
        self, source: TenderSource
    ) -> None:
        """Silently doing nothing would look exactly like a quiet portal."""
        async with session_scope() as session:
            fresh = await session.get(TenderSource, source.id)
            assert fresh is not None
            fresh.adapter_key = "not_a_portal"

        result = await scrape_source({}, str(source.id))

        assert "Unknown adapter 'not_a_portal'" in result["error"]
        runs = await runs_for(source.id)
        assert runs[0].status is RunStatus.FAILED


class TestDispatch:
    async def test_it_queues_only_enabled_sources_with_real_adapters(
        self, fake_portal: type[FakeAdapter], fake_source: TenderSource
    ) -> None:
        result = await scrape_due_sources({})

        assert result["queued"] >= 1
        assert result["queued"] <= result["sources"]


class TestStoredPayloads:
    async def test_the_raw_payload_is_kept_for_replay(
        self, source: TenderSource, tmp_path: Path
    ) -> None:
        """When the portal changes shape, the parser is fixed and replayed over
        these bytes rather than re-scraped."""
        import json

        payload = json.loads(FIXTURE.read_text())

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=payload)

        adapter = WorldBankAdapter(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            config={"rows": 6},
        )
        refs = [ref async for ref in adapter.list_notices(limit_pages=1)]
        documents = await adapter.fetch_detail(refs[0])
        data = adapter.normalize(refs[0], documents)

        # The configured blob directory is a container volume; give this run a
        # writable one so the test exercises storage rather than permissions.
        async with session_scope() as session:
            fresh = await session.get(TenderSource, source.id)
            assert fresh is not None
            outcome = await upsert_tender(
                session,
                source=fresh,
                data=data,
                documents=documents,
                blob_store=LocalFileBlobStore(tmp_path),
            )

        async with session_scope() as session:
            stored = await session.get(Tender, outcome.tender_id)
            documents_kept = await session.scalars(
                select(TenderDocument).where(TenderDocument.tender_id == outcome.tender_id)
            )
            kept = list(documents_kept.all())

        assert stored is not None
        assert stored.external_id == refs[0].external_id
        # The bytes are on disk, which is what makes an offline reparse possible.
        assert kept and (tmp_path / kept[0].storage_key).exists()
