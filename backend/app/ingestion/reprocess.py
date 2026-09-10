"""Re-parsing notices from bytes already stored, without touching the portal.

This is the payoff for capturing raw payloads before parsing them. When a portal
changes its markup, the sequence is: fix the parser, replay it over what is
already held, deploy. No re-scraping — which matters because these portals are
slow, rate limited, and drop notices once they close, so the bytes on disk are
sometimes the only copy left.

Replay goes through the same :func:`~app.ingestion.service.upsert_tender` as a
live scrape, so a re-parsed notice is indistinguishable from a freshly fetched
one: unchanged content stays unchanged, a corrected parse bumps the version and
re-triggers extraction and matching for every tenant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.ingestion.adapters import build_adapter
from app.ingestion.adapters.base import NoticeRef, RawDocument
from app.ingestion.blobstore import BlobStore, get_blob_store
from app.ingestion.service import UpsertOutcome, upsert_tender
from app.modules.tenders.models import DocumentKind, Tender, TenderDocument, TenderSource

logger = get_logger(__name__)

#: Payload kinds that carry the listing row an adapter started from.
_LISTING_KINDS = (DocumentKind.LISTING_ROW, DocumentKind.API_JSON)


@dataclass(frozen=True, slots=True)
class ReparseResult:
    tender_id: UUID
    outcome: str
    version: int
    documents: int
    """How many stored payloads were replayed."""

    @property
    def changed(self) -> bool:
        return self.outcome != UpsertOutcome.UNCHANGED.value


class NoStoredDocumentsError(LookupError):
    """Nothing was captured for this notice, so there is nothing to replay."""


async def load_documents(
    session: AsyncSession, tender_id: UUID, *, blob_store: BlobStore | None = None
) -> list[RawDocument]:
    """Read every stored payload for one notice back out of the blob store.

    Newest capture per kind wins: an amended notice keeps its earlier bytes
    alongside the new ones, and replaying the old ones would resurrect the
    superseded text.
    """
    store = blob_store or get_blob_store()
    rows = list(
        (
            await session.scalars(
                select(TenderDocument)
                .where(TenderDocument.tender_id == tender_id)
                .order_by(TenderDocument.created_at.desc())
            )
        ).all()
    )

    documents: list[RawDocument] = []
    seen_kinds: set[DocumentKind] = set()
    for row in rows:
        if row.kind in seen_kinds:
            continue
        try:
            content = await store.get(row.storage_key)
        except Exception as exc:
            # A payload the store lost must not sink the rest of the replay.
            logger.warning(
                "blob_unreadable", tender_id=str(tender_id), key=row.storage_key, error=str(exc)
            )
            continue
        seen_kinds.add(row.kind)
        documents.append(
            RawDocument(
                kind=row.kind,
                content=content,
                url=row.url,
                content_type=row.content_type,
            )
        )
    return documents


def rebuild_ref(tender: Tender, documents: list[RawDocument]) -> NoticeRef:
    """Reconstruct the listing reference the adapter originally normalised from.

    The stored listing payload is preferred, because an adapter reads fields
    from it that never make it onto the tender row. When it is missing or
    unreadable the tender's own columns stand in, which is enough for every
    adapter to normalise a detail page.
    """
    listing_data: dict[str, Any] = {}
    for document in documents:
        if document.kind in _LISTING_KINDS:
            try:
                parsed = json.loads(document.content.decode("utf-8", errors="replace"))
            except ValueError:
                # Payloads captured before listing rows were stored as JSON.
                logger.info("listing_payload_not_json", tender_id=str(tender.id))
                continue
            if isinstance(parsed, dict):
                listing_data = parsed
            break

    return NoticeRef(
        external_id=tender.external_id,
        url=tender.canonical_url,
        title=tender.title,
        published_at=tender.published_at,
        deadline_at=tender.deadline_at,
        listing_data=listing_data,
    )


async def reparse_tender(
    session: AsyncSession,
    *,
    tender: Tender,
    source: TenderSource,
    blob_store: BlobStore | None = None,
) -> ReparseResult:
    """Re-run the adapter's parser over stored bytes and upsert the result.

    Raises:
        LookupError: the source names an adapter that does not exist.
        NoStoredDocumentsError: nothing was captured for this notice.
    """
    documents = await load_documents(session, tender.id, blob_store=blob_store)
    if not documents:
        raise NoStoredDocumentsError(
            f"No stored payloads for tender {tender.id}; it cannot be re-parsed."
        )

    adapter = build_adapter(
        source.adapter_key, base_url=source.base_url, config=dict(source.config or {})
    )
    data = adapter.normalize(rebuild_ref(tender, documents), documents)

    # No documents passed through: they are already stored, and storing them
    # again would be a no-op that still hits the blob store once per payload.
    result = await upsert_tender(session, source=source, data=data)
    logger.info(
        "tender_reparsed",
        tender_id=str(tender.id),
        source=source.code,
        outcome=result.outcome.value,
        documents=len(documents),
    )
    return ReparseResult(
        tender_id=result.tender_id,
        outcome=result.outcome.value,
        version=result.version,
        documents=len(documents),
    )
