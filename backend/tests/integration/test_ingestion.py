"""The shared ingestion path used by scrapers, the importer and admin adds."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.db.session import session_scope
from app.ingestion.adapters.base import RawDocument, TenderIn
from app.ingestion.blobstore import LocalFileBlobStore
from app.ingestion.service import UpsertOutcome, upsert_tender
from app.modules.tenders.models import (
    DocumentKind,
    ProcurementCategory,
    Tender,
    TenderDocument,
    TenderSource,
)

DETAIL_HTML = b"<html><body>Notice 1331101: solar water pumps</body></html>"


@pytest.fixture
async def source() -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"test-{uuid4().hex[:8]}",
        name="Test Portal",
        adapter_key="test",
        base_url="https://example.invalid",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


@pytest.fixture
def blob_store(tmp_path: Path) -> LocalFileBlobStore:
    return LocalFileBlobStore(tmp_path)


def notice(**overrides: object) -> TenderIn:
    defaults: dict[str, object] = {
        "external_id": "1331101",
        "canonical_url": "https://example.invalid/notice/1331101",
        "title": "Supply and installation of solar water pumps",
        "summary": "Solar irrigation pumps for Rangpur division.",
        "procuring_entity": "Local Government Engineering Department",
        "country": "BD",
        "procurement_category": ProcurementCategory.GOODS,
        "deadline_at": datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
        "currency": "BDT",
        "estimated_value": 12_500_000.0,
    }
    defaults.update(overrides)
    return TenderIn(**defaults)  # type: ignore[arg-type]


async def test_a_new_notice_is_created(source: TenderSource) -> None:
    async with session_scope() as session:
        result = await upsert_tender(session, source=source, data=notice())

    assert result.outcome is UpsertOutcome.CREATED
    assert result.version == 1
    assert result.needs_processing is True


async def test_rescraping_an_unchanged_notice_does_nothing(source: TenderSource) -> None:
    """The daily scrape must not re-run the language model over the whole pool."""
    async with session_scope() as session:
        first = await upsert_tender(session, source=source, data=notice())

    async with session_scope() as session:
        second = await upsert_tender(session, source=source, data=notice())

    assert second.outcome is UpsertOutcome.UNCHANGED
    assert second.tender_id == first.tender_id
    assert second.version == 1
    assert second.needs_processing is False


async def test_rescraping_still_records_that_the_notice_is_live(
    source: TenderSource,
) -> None:
    async with session_scope() as session:
        result = await upsert_tender(session, source=source, data=notice())
    async with session_scope() as session:
        tender = await session.get(Tender, result.tender_id)
        assert tender is not None
        first_seen = tender.last_seen_at

    async with session_scope() as session:
        await upsert_tender(session, source=source, data=notice())

    async with session_scope() as session:
        tender = await session.get(Tender, result.tender_id)
        assert tender is not None
        assert tender.last_seen_at > first_seen


async def test_an_amended_notice_is_updated_and_versioned(source: TenderSource) -> None:
    async with session_scope() as session:
        first = await upsert_tender(session, source=source, data=notice())

    async with session_scope() as session:
        second = await upsert_tender(
            session,
            source=source,
            data=notice(deadline_at=datetime(2026, 10, 15, 12, 0, tzinfo=UTC)),
        )

    assert second.outcome is UpsertOutcome.UPDATED
    assert second.tender_id == first.tender_id
    assert second.version == 2
    assert second.needs_processing is True


async def test_an_update_overwrites_the_changed_fields(source: TenderSource) -> None:
    async with session_scope() as session:
        result = await upsert_tender(session, source=source, data=notice())

    async with session_scope() as session:
        await upsert_tender(
            session, source=source, data=notice(title="Supply of diesel pumps instead")
        )

    async with session_scope() as session:
        tender = await session.get(Tender, result.tender_id)
        assert tender is not None
        assert tender.title == "Supply of diesel pumps instead"


async def test_raw_payloads_are_stored_for_replay(
    source: TenderSource, blob_store: LocalFileBlobStore
) -> None:
    """A parser fix must be replayable without going back to the portal."""
    async with session_scope() as session:
        result = await upsert_tender(
            session,
            source=source,
            data=notice(),
            documents=[
                RawDocument(
                    kind=DocumentKind.DETAIL_HTML,
                    content=DETAIL_HTML,
                    url="https://example.invalid/notice/1331101",
                    content_type="text/html",
                )
            ],
            blob_store=blob_store,
        )

    async with session_scope() as session:
        document = await session.scalar(
            select(TenderDocument).where(TenderDocument.tender_id == result.tender_id)
        )

    assert document is not None
    assert document.kind is DocumentKind.DETAIL_HTML
    assert await blob_store.get(document.storage_key) == DETAIL_HTML


async def test_identical_payloads_are_stored_once(
    source: TenderSource, blob_store: LocalFileBlobStore
) -> None:
    document = RawDocument(kind=DocumentKind.DETAIL_HTML, content=DETAIL_HTML)

    for _ in range(3):
        async with session_scope() as session:
            result = await upsert_tender(
                session,
                source=source,
                data=notice(),
                documents=[document],
                blob_store=blob_store,
            )

    async with session_scope() as session:
        stored = await session.scalar(
            select(func.count())
            .select_from(TenderDocument)
            .where(TenderDocument.tender_id == result.tender_id)
        )

    assert stored == 1


async def test_an_amended_payload_is_kept_alongside_the_original(
    source: TenderSource, blob_store: LocalFileBlobStore
) -> None:
    """Both captures are needed to explain why a score changed."""
    async with session_scope() as session:
        result = await upsert_tender(
            session,
            source=source,
            data=notice(),
            documents=[RawDocument(kind=DocumentKind.DETAIL_HTML, content=DETAIL_HTML)],
            blob_store=blob_store,
        )

    async with session_scope() as session:
        await upsert_tender(
            session,
            source=source,
            data=notice(title="Amended: supply of solar pumps"),
            documents=[
                RawDocument(
                    kind=DocumentKind.DETAIL_HTML, content=DETAIL_HTML + b"<p>corrigendum</p>"
                )
            ],
            blob_store=blob_store,
        )

    async with session_scope() as session:
        stored = await session.scalar(
            select(func.count())
            .select_from(TenderDocument)
            .where(TenderDocument.tender_id == result.tender_id)
        )

    assert stored == 2
