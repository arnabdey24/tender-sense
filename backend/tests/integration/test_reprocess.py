"""Replaying stored payloads through a fixed parser.

This is the whole reason raw bytes are captured before they are parsed. The
scenario: a portal changes its markup overnight, notices arrive with missing
fields, someone fixes the selectors — and every notice already ingested by the
broken parser has to be corrected without asking the portal for any of it again.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import session_scope
from app.ingestion.adapters.base import ADAPTERS, NoticeRef, RawDocument, TenderIn
from app.ingestion.blobstore import LocalFileBlobStore, set_blob_store
from app.ingestion.reprocess import (
    NoStoredDocumentsError,
    load_documents,
    rebuild_ref,
    reparse_tender,
)
from app.ingestion.service import upsert_tender
from app.jobs.tasks.reprocessing import reparse_source
from app.modules.tenders.models import DocumentKind, Tender, TenderSource


class ReplayAdapter:
    """Parses the stored JSON payload, with a title prefix a test can change."""

    key = "replay_portal"

    #: Stands in for a selector fix: change it and the same bytes parse anew.
    title_prefix = ""

    def __init__(self, **_: Any) -> None: ...

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> TenderIn:
        payload: dict[str, Any] = {}
        for document in documents:
            if document.kind is DocumentKind.API_JSON:
                payload = json.loads(document.content)
                break
        return TenderIn(
            external_id=ref.external_id,
            canonical_url=ref.url,
            title=f"{type(self).title_prefix}{payload.get('title', ref.title or '')}",
            description=payload.get("description"),
        )


@pytest.fixture(autouse=True)
def blob_store(tmp_path: Any) -> AsyncIterator[None]:
    set_blob_store(LocalFileBlobStore(tmp_path))
    yield
    set_blob_store(None)


@pytest.fixture
def replay_adapter() -> AsyncIterator[type[ReplayAdapter]]:
    ADAPTERS["replay_portal"] = ReplayAdapter
    ReplayAdapter.title_prefix = ""
    yield ReplayAdapter
    ADAPTERS.pop("replay_portal", None)


@pytest.fixture
async def source(replay_adapter: type[ReplayAdapter]) -> AsyncIterator[TenderSource]:
    record = TenderSource(
        code=f"replay-{uuid4().hex[:8]}",
        name="Replay portal",
        adapter_key="replay_portal",
        base_url="https://portal.invalid",
    )
    async with session_scope() as session:
        session.add(record)
        await session.flush()
        await session.refresh(record)
    yield record
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == record.id))


async def ingest(source: TenderSource, external_id: str, title: str) -> Tender:
    """Store one notice exactly as a scrape would, payload and all."""
    payload = {"id": external_id, "title": title, "description": "As published."}
    documents = [
        RawDocument(
            kind=DocumentKind.API_JSON,
            content=json.dumps(payload).encode(),
            url=f"https://portal.invalid/{external_id}",
            content_type="application/json",
        )
    ]
    async with session_scope() as session:
        fresh = await session.get(TenderSource, source.id)
        assert fresh is not None
        result = await upsert_tender(
            session,
            source=fresh,
            data=TenderIn(
                external_id=external_id,
                canonical_url=f"https://portal.invalid/{external_id}",
                title=title,
                description="As published.",
            ),
            documents=documents,
        )
        tender = await session.get(Tender, result.tender_id)
        assert tender is not None
        await session.refresh(tender)
        return tender


async def reload(tender_id: Any) -> Tender | None:
    async with session_scope() as session:
        return await session.get(Tender, tender_id)


class TestLoadingStoredPayloads:
    async def test_it_reads_back_the_bytes_that_were_captured(self, source: TenderSource) -> None:
        tender = await ingest(source, "n-1", "Original title")

        async with session_scope() as session:
            documents = await load_documents(session, tender.id)

        assert [d.kind for d in documents] == [DocumentKind.API_JSON]
        assert json.loads(documents[0].content)["title"] == "Original title"

    async def test_a_payload_the_store_lost_does_not_sink_the_replay(
        self, source: TenderSource, tmp_path: Any
    ) -> None:
        """One unreadable blob must cost one payload, not the whole notice."""
        tender = await ingest(source, "n-2", "Original title")
        for path in tmp_path.rglob("*.gz"):
            path.unlink()

        async with session_scope() as session:
            documents = await load_documents(session, tender.id)

        assert documents == []


class TestRebuildingTheReference:
    async def test_the_stored_listing_payload_becomes_listing_data(
        self, source: TenderSource
    ) -> None:
        """Adapters read fields from the listing row that never reach the tender."""
        tender = await ingest(source, "n-3", "Original title")

        async with session_scope() as session:
            documents = await load_documents(session, tender.id)
            fresh = await session.get(Tender, tender.id)
            assert fresh is not None
            ref = rebuild_ref(fresh, documents)

        assert ref.external_id == "n-3"
        assert ref.listing_data["title"] == "Original title"

    async def test_a_notice_with_no_readable_payload_still_yields_a_reference(
        self, source: TenderSource
    ) -> None:
        tender = await ingest(source, "n-4", "Original title")

        async with session_scope() as session:
            fresh = await session.get(Tender, tender.id)
            assert fresh is not None
            ref = rebuild_ref(fresh, [])

        assert ref.external_id == "n-4"
        assert ref.listing_data == {}


class TestReparsing:
    async def test_a_fixed_parser_corrects_the_stored_notice(
        self, source: TenderSource, replay_adapter: type[ReplayAdapter]
    ) -> None:
        tender = await ingest(source, "n-5", "Original title")
        replay_adapter.title_prefix = "Fixed: "

        async with session_scope() as session:
            fresh_tender = await session.get(Tender, tender.id)
            fresh_source = await session.get(TenderSource, source.id)
            assert fresh_tender and fresh_source
            result = await reparse_tender(session, tender=fresh_tender, source=fresh_source)

        assert result.changed
        assert result.outcome == "updated"
        stored = await reload(tender.id)
        assert stored is not None
        assert stored.title == "Fixed: Original title"
        assert stored.version == 2

    async def test_an_unchanged_parse_changes_nothing(self, source: TenderSource) -> None:
        """Replay is cheap to run over a whole portal only if it is a no-op."""
        tender = await ingest(source, "n-6", "Original title")

        async with session_scope() as session:
            fresh_tender = await session.get(Tender, tender.id)
            fresh_source = await session.get(TenderSource, source.id)
            assert fresh_tender and fresh_source
            result = await reparse_tender(session, tender=fresh_tender, source=fresh_source)

        assert result.outcome == "unchanged"
        assert not result.changed
        stored = await reload(tender.id)
        assert stored is not None
        assert stored.version == 1

    async def test_a_notice_with_nothing_stored_says_so(self, source: TenderSource) -> None:
        """Distinct from "parsed to the same thing": there was nothing to parse."""
        async with session_scope() as session:
            fresh_source = await session.get(TenderSource, source.id)
            assert fresh_source is not None
            result = await upsert_tender(
                session,
                source=fresh_source,
                data=TenderIn(
                    external_id="n-7",
                    canonical_url="https://portal.invalid/n-7",
                    title="Hand entered",
                ),
            )
            tender = await session.get(Tender, result.tender_id)
            assert tender is not None

            with pytest.raises(NoStoredDocumentsError):
                await reparse_tender(session, tender=tender, source=fresh_source)

    async def test_replaying_does_not_duplicate_the_stored_payloads(
        self, source: TenderSource, replay_adapter: type[ReplayAdapter]
    ) -> None:
        tender = await ingest(source, "n-8", "Original title")
        replay_adapter.title_prefix = "Fixed: "

        async with session_scope() as session:
            fresh_tender = await session.get(Tender, tender.id)
            fresh_source = await session.get(TenderSource, source.id)
            assert fresh_tender and fresh_source
            await reparse_tender(session, tender=fresh_tender, source=fresh_source)

        async with session_scope() as session:
            documents = await load_documents(session, tender.id)
        assert len(documents) == 1


class TestReparseJob:
    async def test_it_reports_what_changed_and_what_did_not(
        self, source: TenderSource, replay_adapter: type[ReplayAdapter]
    ) -> None:
        await ingest(source, "j-1", "First notice")
        await ingest(source, "j-2", "Second notice")
        replay_adapter.title_prefix = "Fixed: "

        result = await reparse_source({}, str(source.id))

        assert result["examined"] == 2
        assert result["changed"] == 2
        assert result["failed"] == 0

    async def test_a_notice_that_still_fails_does_not_lose_the_repaired_ones(
        self, source: TenderSource, replay_adapter: type[ReplayAdapter]
    ) -> None:
        """The point of a replay is that some notices parse differently now."""
        await ingest(source, "j-3", "Parses fine")
        await ingest(source, "j-4", "BROKEN")

        original = ReplayAdapter.normalize

        def selective(self: ReplayAdapter, ref: NoticeRef, documents: Any) -> TenderIn:
            parsed = original(self, ref, documents)
            if "BROKEN" in parsed.title:
                raise ValueError("selector matched nothing")
            return parsed.model_copy(update={"title": f"Fixed: {parsed.title}"})

        ReplayAdapter.normalize = selective  # type: ignore[method-assign]
        try:
            result = await reparse_source({}, str(source.id))
        finally:
            ReplayAdapter.normalize = original  # type: ignore[method-assign]

        assert result["failed"] == 1
        assert result["changed"] == 1

    async def test_an_unknown_source_is_reported_not_silently_skipped(self) -> None:
        result = await reparse_source({}, str(uuid4()))

        assert result["error"] == "source_not_found"

    async def test_a_notice_with_no_payload_is_counted_separately(
        self, source: TenderSource
    ) -> None:
        async with session_scope() as session:
            fresh_source = await session.get(TenderSource, source.id)
            assert fresh_source is not None
            await upsert_tender(
                session,
                source=fresh_source,
                data=TenderIn(
                    external_id="j-5",
                    canonical_url="https://portal.invalid/j-5",
                    title="Hand entered",
                ),
            )

        result = await reparse_source({}, str(source.id))

        assert result["no_payload"] == 1
        assert result["failed"] == 0
