"""Turning fetched notices into rows in the shared pool.

Every ingestion path goes through :func:`upsert_tender`: the scrapers, the
JSON/CSV importer and the admin "add a tender" endpoint. That keeps change
detection, versioning and raw-payload capture in one place, so a hand-imported
notice behaves exactly like a scraped one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.time import utcnow
from app.ingestion.adapters.base import RawDocument, TenderIn
from app.ingestion.blobstore import BlobStore, get_blob_store, tender_document_key
from app.modules.tenders.models import Tender, TenderDocument, TenderSource

logger = get_logger(__name__)


class UpsertOutcome(enum.StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    """The portal edited the notice; downstream work must re-run."""
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class UpsertResult:
    tender_id: UUID
    outcome: UpsertOutcome
    version: int

    @property
    def needs_processing(self) -> bool:
        """Whether extraction, embedding and matching should run."""
        return self.outcome is not UpsertOutcome.UNCHANGED


async def store_documents(
    session: AsyncSession,
    *,
    tender: Tender,
    source_code: str,
    documents: list[RawDocument],
    blob_store: BlobStore | None = None,
) -> int:
    """Persist raw payloads, skipping bytes already captured.

    Content-addressed, so re-scraping an unchanged notice adds nothing, while a
    genuine amendment is kept alongside the earlier capture rather than
    replacing it.
    """
    store = blob_store or get_blob_store()
    stored = 0

    for document in documents:
        key, digest = tender_document_key(
            source_code=source_code,
            tender_external_id=tender.external_id,
            kind=document.kind.value,
            data=document.content,
        )
        already_have = await session.scalar(
            select(TenderDocument).where(
                TenderDocument.tender_id == tender.id, TenderDocument.sha256 == digest
            )
        )
        if already_have is not None:
            continue

        size = await store.put(key, document.content)
        session.add(
            TenderDocument(
                tender_id=tender.id,
                kind=document.kind,
                url=document.url,
                storage_key=key,
                content_type=document.content_type,
                sha256=digest,
                size_bytes=size,
            )
        )
        stored += 1

    if stored:
        await session.flush()
    return stored


async def upsert_tender(
    session: AsyncSession,
    *,
    source: TenderSource,
    data: TenderIn,
    documents: list[RawDocument] | None = None,
    blob_store: BlobStore | None = None,
) -> UpsertResult:
    """Insert or update one notice.

    Identity is ``(source, external_id)``. A notice whose content hash is
    unchanged only has ``last_seen_at`` touched, which is what keeps a daily
    scrape from re-running the language model over thousands of unchanged rows.
    """
    now = utcnow()
    content_hash = data.content_hash()

    existing = await session.scalar(
        select(Tender).where(Tender.source_id == source.id, Tender.external_id == data.external_id)
    )

    if existing is None:
        tender = Tender(
            source_id=source.id,
            content_hash=content_hash,
            first_seen_at=now,
            last_seen_at=now,
            version=1,
            **data.model_dump(exclude={"external_id"}),
            external_id=data.external_id,
        )
        session.add(tender)
        await session.flush()
        outcome = UpsertOutcome.CREATED
    else:
        tender = existing
        tender.last_seen_at = now
        if tender.content_hash == content_hash:
            await session.flush()
            logger.debug("tender_unchanged", tender_id=str(tender.id))
            return UpsertResult(tender.id, UpsertOutcome.UNCHANGED, tender.version)

        for field, value in data.model_dump(exclude={"external_id"}).items():
            setattr(tender, field, value)
        tender.content_hash = content_hash
        tender.version += 1
        await session.flush()
        outcome = UpsertOutcome.UPDATED

    if documents:
        await store_documents(
            session,
            tender=tender,
            source_code=source.code,
            documents=documents,
            blob_store=blob_store,
        )

    logger.info(
        "tender_upserted",
        tender_id=str(tender.id),
        source=source.code,
        external_id=data.external_id,
        outcome=outcome.value,
        version=tender.version,
    )
    return UpsertResult(tender.id, outcome, tender.version)


async def get_source_by_code(session: AsyncSession, code: str) -> TenderSource | None:
    result = await session.scalar(select(TenderSource).where(TenderSource.code == code))
    return result
