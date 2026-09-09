"""Schema behaviour the matching pipeline depends on.

These check the parts of the tender pool that are easy to get wrong in a
migration and expensive to discover later: the generated search vector, the
vector index, and the uniqueness rules that make ingestion idempotent.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.security import hash_token
from app.db.session import session_scope
from app.modules.tenders.models import (
    EmbeddingChunk,
    Tender,
    TenderEmbedding,
    TenderSource,
)

DIMS = 768


async def make_source() -> TenderSource:
    source = TenderSource(
        code=f"test-{uuid4().hex[:8]}",
        name="Test Portal",
        adapter_key="test",
        base_url="https://example.invalid",
    )
    async with session_scope() as session:
        session.add(source)
        await session.flush()
        await session.refresh(source)
    return source


async def _cleanup(source_id: object) -> None:
    async with session_scope() as session:
        await session.execute(delete(TenderSource).where(TenderSource.id == source_id))


def make_tender(source_id: object, **overrides: object) -> Tender:
    defaults: dict[str, object] = {
        "source_id": source_id,
        "external_id": uuid4().hex,
        "canonical_url": "https://example.invalid/notice/1",
        "title": "Supply and installation of solar water pumps",
        "summary": "Procurement of solar irrigation pumps for Rangpur division.",
        "procuring_entity": "Local Government Engineering Department",
        "content_hash": hash_token("seed"),
    }
    defaults.update(overrides)
    return Tender(**defaults)  # type: ignore[arg-type]


async def test_the_search_vector_is_generated_from_the_text_fields() -> None:
    source = await make_source()
    try:
        async with session_scope() as session:
            session.add(make_tender(source.id))

        async with session_scope() as session:
            matched = await session.scalar(
                select(func.count())
                .select_from(Tender)
                .where(
                    Tender.source_id == source.id,
                    Tender.search_tsv.op("@@")(func.plainto_tsquery("simple", "solar pumps")),
                )
            )

        assert matched == 1
    finally:
        await _cleanup(source.id)


async def test_the_search_vector_updates_when_the_notice_is_edited() -> None:
    """Portals amend notices, and the index must follow without extra code."""
    source = await make_source()
    try:
        async with session_scope() as session:
            tender = make_tender(source.id)
            session.add(tender)
            await session.flush()
            tender_id = tender.id

        async with session_scope() as session:
            tender = await session.get(Tender, tender_id)
            assert tender is not None
            tender.title = "Construction of a rural health complex"
            tender.summary = "Civil works for a district hospital."

        async with session_scope() as session:
            still_solar = await session.scalar(
                select(func.count())
                .select_from(Tender)
                .where(
                    Tender.id == tender_id,
                    Tender.search_tsv.op("@@")(func.plainto_tsquery("simple", "solar")),
                )
            )
            now_hospital = await session.scalar(
                select(func.count())
                .select_from(Tender)
                .where(
                    Tender.id == tender_id,
                    Tender.search_tsv.op("@@")(func.plainto_tsquery("simple", "hospital")),
                )
            )

        assert (still_solar, now_hospital) == (0, 1)
    finally:
        await _cleanup(source.id)


async def test_the_same_notice_cannot_be_ingested_twice() -> None:
    """Re-running a scrape must not duplicate rows."""
    source = await make_source()
    external_id = uuid4().hex
    try:
        async with session_scope() as session:
            session.add(make_tender(source.id, external_id=external_id))

        with pytest.raises(IntegrityError):
            async with session_scope() as session:
                session.add(make_tender(source.id, external_id=external_id))
    finally:
        await _cleanup(source.id)


async def test_the_same_external_id_from_another_portal_is_a_different_tender() -> None:
    first = await make_source()
    second = await make_source()
    external_id = uuid4().hex
    try:
        async with session_scope() as session:
            session.add(make_tender(first.id, external_id=external_id))
            session.add(make_tender(second.id, external_id=external_id))

        async with session_scope() as session:
            count = await session.scalar(
                select(func.count()).select_from(Tender).where(Tender.external_id == external_id)
            )

        assert count == 2
    finally:
        await _cleanup(first.id)
        await _cleanup(second.id)


async def test_vectors_round_trip_and_rank_by_cosine_distance() -> None:
    """The core matching operation: nearest neighbours by cosine distance."""
    source = await make_source()
    try:
        async with session_scope() as session:
            tender = make_tender(source.id)
            session.add(tender)
            await session.flush()

            near = [1.0] + [0.0] * (DIMS - 1)
            far = [0.0, 1.0] + [0.0] * (DIMS - 2)
            for index, vector in enumerate((near, far)):
                session.add(
                    TenderEmbedding(
                        tender_id=tender.id,
                        chunk_kind=EmbeddingChunk.TITLE_SUMMARY,
                        chunk_index=index,
                        model="test-model",
                        dims=DIMS,
                        embedding=vector,
                        text_hash=hash_token(f"chunk-{index}"),
                    )
                )
            tender_id = tender.id

        async with session_scope() as session:
            query = [1.0] + [0.0] * (DIMS - 1)
            rows = (
                await session.execute(
                    select(
                        TenderEmbedding.chunk_index,
                        TenderEmbedding.embedding.cosine_distance(query).label("distance"),
                    )
                    .where(TenderEmbedding.tender_id == tender_id)
                    .order_by(text("distance"))
                )
            ).all()

        assert [row.chunk_index for row in rows] == [0, 1]
        assert rows[0].distance == pytest.approx(0.0, abs=1e-6)
        assert rows[1].distance > 0.9
    finally:
        await _cleanup(source.id)


async def test_deleting_a_source_removes_its_tenders_and_vectors() -> None:
    source = await make_source()
    async with session_scope() as session:
        tender = make_tender(source.id)
        session.add(tender)
        await session.flush()
        session.add(
            TenderEmbedding(
                tender_id=tender.id,
                chunk_kind=EmbeddingChunk.TITLE_SUMMARY,
                chunk_index=0,
                model="test-model",
                dims=DIMS,
                embedding=[0.5] * DIMS,
                text_hash=hash_token("chunk"),
            )
        )
        tender_id = tender.id

    await _cleanup(source.id)

    async with session_scope() as session:
        remaining_tenders = await session.scalar(
            select(func.count()).select_from(Tender).where(Tender.id == tender_id)
        )
        remaining_vectors = await session.scalar(
            select(func.count())
            .select_from(TenderEmbedding)
            .where(TenderEmbedding.tender_id == tender_id)
        )

    assert (remaining_tenders, remaining_vectors) == (0, 0)
