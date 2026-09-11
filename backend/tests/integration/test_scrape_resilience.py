"""What a scrape leaves behind when it does not finish.

One deployment ingested 1,122 notices and matched none of them: the pass took
an hour, the worker cancelled it at its job timeout, and the enqueue that would
have scheduled extraction sat after the loop. Every organization saw a full
tender list, no matches and an empty dashboard, with no failed job anywhere to
explain it. These tests are about that hour.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.ingestion.adapters.base import NoticeRef, RawDocument, TenderIn
from app.jobs.runs import RunStatus, ScraperRun
from app.jobs.tasks.scraping import scrape_source
from app.modules.tenders.models import DocumentKind, Tender, TenderSource


@pytest.fixture(autouse=True)
def blobs_somewhere_writable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default blob directory is a deployment path; a test run owns none."""
    monkeypatch.setattr(settings, "blob_storage_dir", str(tmp_path))


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    from app.db.session import session_scope

    record = TenderSource(
        code=f"res-{uuid4().hex[:8]}",
        name="Resilience Portal",
        adapter_key="resilience_test",
        base_url="https://example.invalid",
        config={"max_pages": 1},
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


def _adapter(*, notices: int, cancel_after: int | None = None) -> type:
    """An adapter that yields `notices`, optionally cancelled part-way."""
    from app.ingestion.adapters.base import register_adapter

    @register_adapter
    class _Adapter:
        key = "resilience_test"

        def __init__(self, **_: Any) -> None:
            self.served = 0

        async def list_notices(self, **_: Any) -> AsyncIterator[NoticeRef]:
            for index in range(notices):
                yield NoticeRef(
                    external_id=f"res-{index}",
                    url=f"https://example.invalid/{index}",
                )

        async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
            self.served += 1
            if cancel_after is not None and self.served > cancel_after:
                # Exactly what the worker's job timeout does to a long pass.
                raise asyncio.CancelledError
            return [RawDocument(kind=DocumentKind.API_JSON, content=b"{}", url=ref.url)]

        def normalize(self, ref: NoticeRef, _documents: list[RawDocument]) -> TenderIn:
            return TenderIn(
                external_id=ref.external_id,
                canonical_url=ref.url or "https://example.invalid",
                title=f"Resilience notice {ref.external_id}",
                published_at=datetime.now().astimezone(),
            )

        async def health_check(self, **_: Any) -> Any:  # pragma: no cover
            raise NotImplementedError

    return _Adapter


class TestCancellation:
    async def test_a_cancelled_pass_does_not_leave_the_run_saying_running(
        self, source: TenderSource
    ) -> None:
        """A run stuck at "running" never updates health, and tells the sync
        control a pass is in flight that nothing will ever finish."""
        from app.db.session import session_scope

        _adapter(notices=4, cancel_after=2)

        with pytest.raises(asyncio.CancelledError):
            await scrape_source({}, str(source.id))

        async with session_scope() as session:
            run = await session.scalar(select(ScraperRun).where(ScraperRun.source_id == source.id))
            assert run is not None
            assert run.status is not RunStatus.RUNNING
            assert run.finished_at is not None
            assert run.error and "Cancelled" in run.error

    async def test_notices_committed_before_the_cancellation_are_kept(
        self, source: TenderSource
    ) -> None:
        """They are durable already; losing the work that followed them is the
        bug, not the commit."""
        from app.db.session import session_scope

        _adapter(notices=4, cancel_after=2)

        with pytest.raises(asyncio.CancelledError):
            await scrape_source({}, str(source.id))

        async with session_scope() as session:
            kept = (
                await session.scalars(
                    select(Tender.external_id).where(Tender.source_id == source.id)
                )
            ).all()
        assert len(kept) == 2


class TestFailureReporting:
    async def test_a_failure_with_no_message_still_records_its_kind(
        self, source: TenderSource
    ) -> None:
        """`str(exc)` is empty for a bare timeout, and a failed run carrying no
        reason is the one thing a run record exists not to be."""
        from app.db.session import session_scope
        from app.ingestion.adapters.base import register_adapter

        @register_adapter
        class _Timeout:
            key = "resilience_test"

            def __init__(self, **_: Any) -> None: ...

            async def list_notices(self, **_: Any) -> AsyncIterator[NoticeRef]:
                raise TimeoutError  # no message at all
                yield  # pragma: no cover

            async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]: ...

            def normalize(self, *_: Any) -> TenderIn: ...

        await scrape_source({}, str(source.id))

        async with session_scope() as session:
            run = await session.scalar(select(ScraperRun).where(ScraperRun.source_id == source.id))
        assert run is not None
        assert run.status is RunStatus.FAILED
        assert run.error == "TimeoutError"
