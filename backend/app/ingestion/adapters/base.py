"""The contract every portal adapter implements.

Adding a portal (UNGM, ADB) means writing one module and inserting one
``tender_sources`` row. Nothing downstream changes, because ingestion,
extraction, embedding and matching all work from :class:`TenderIn`.

Normalisation is deliberately a pure function of the fetched bytes. That is what
makes a broken parser fixable offline: re-run ``normalize`` over the payloads
already in the blob store rather than re-scraping the portal.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.tenders.models import DocumentKind, ProcurementCategory, TenderStatus


class NoticeRef(BaseModel):
    """A notice spotted in a listing, before its detail page is fetched."""

    external_id: str
    url: str
    title: str | None = None
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    #: Whatever the listing row carried; the adapter decides what it means.
    listing_data: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    """Bytes exactly as fetched, kept for replay."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    kind: DocumentKind
    content: bytes
    url: str | None = None
    content_type: str | None = None


class TenderIn(BaseModel):
    """A normalised notice, ready to upsert into the shared pool."""

    # The three fields that make a notice a notice, and the reason they are
    # constrained rather than merely typed: `str` accepts "", so a CSV row of
    # empty cells, or an adapter whose selector stopped matching, wrote a
    # titleless row into the shared pool that every tenant then saw and nobody
    # could search for. Rejecting it costs one row and reports why; accepting it
    # costs a pool nobody trusts. Whitespace-only is the same thing wearing a
    # space, so both ends are stripped first.
    external_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    canonical_url: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    summary: str | None = None
    description: str | None = None
    procuring_entity: str | None = None
    country: str | None = None
    procurement_method: str | None = None
    procurement_category: ProcurementCategory = ProcurementCategory.UNKNOWN
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    currency: str | None = None
    estimated_value: float | None = None
    status: TenderStatus = TenderStatus.OPEN
    language: str | None = None
    portal_metadata: dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        """Digest of the fields that decide whether a notice changed.

        Excludes ``portal_metadata`` and anything the portal touches on every
        render, so a cosmetic edit does not trigger re-extraction and re-scoring
        for every customer.
        """
        parts = [
            self.external_id,
            self.title.strip(),
            (self.summary or "").strip(),
            (self.description or "").strip(),
            (self.procuring_entity or "").strip(),
            self.procurement_method or "",
            self.procurement_category.value,
            self.deadline_at.isoformat() if self.deadline_at else "",
            self.currency or "",
            f"{self.estimated_value:.2f}" if self.estimated_value is not None else "",
            self.status.value,
        ]
        return hashlib.sha256("␟".join(parts).encode()).hexdigest()


class SourceHealthReport(BaseModel):
    reachable: bool
    detail: str | None = None


@runtime_checkable
class SourceAdapter(Protocol):
    """One procurement portal."""

    key: str
    """Matches ``tender_sources.adapter_key``."""

    def list_notices(
        self, *, since: datetime | None, cursor: dict[str, Any] | None, limit_pages: int
    ) -> AsyncIterator[NoticeRef]:
        """Yield notices newest first, stopping at ``limit_pages``.

        Callers stop early once they recognise an identifier they already hold,
        because these portals offer no reliable server-side date filter.
        """
        ...

    async def fetch_detail(self, ref: NoticeRef) -> list[RawDocument]:
        """Fetch everything needed to normalise one notice."""
        ...

    def normalize(self, ref: NoticeRef, documents: list[RawDocument]) -> TenderIn:
        """Pure: same inputs, same output. No network access."""
        ...

    async def healthcheck(self) -> SourceHealthReport:
        """Cheap reachability probe for the admin source list."""
        ...


ADAPTERS: dict[str, type] = {}


def register_adapter(adapter_cls: type) -> type:
    """Class decorator that adds an adapter to the registry by its key."""
    key = getattr(adapter_cls, "key", None)
    if not key:
        raise ValueError(f"{adapter_cls.__name__} must define a `key`")
    ADAPTERS[key] = adapter_cls
    return adapter_cls


def get_adapter_class(adapter_key: str) -> type:
    try:
        return ADAPTERS[adapter_key]
    except KeyError as exc:
        known = ", ".join(sorted(ADAPTERS)) or "none registered"
        raise LookupError(f"Unknown adapter {adapter_key!r}. Known: {known}.") from exc
