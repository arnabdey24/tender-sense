"""Request and response bodies for the shared tender pool."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.jobs.runs import RunStatus
from app.modules.tenders.models import ProcurementCategory, SourceHealth, TenderStatus


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    country: str | None = None
    enabled: bool
    health: SourceHealth
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int


class PortalSyncState(BaseModel):
    """One portal, as the sync control needs to describe it.

    ``last_run_at`` on its own cannot tell a waiting person whether anything is
    happening — a timestamp from four hours ago looks the same whether a pass is
    running right now or the portal has been silent since. So the run in flight
    is reported separately from the last one that finished.
    """

    id: UUID
    code: str
    name: str
    enabled: bool
    health: SourceHealth
    running: bool
    """A pass over this portal is in flight."""
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_status: RunStatus | None = None
    last_notices_added: int | None = None
    """Notices the last finished pass added, so "it worked" is a number."""


class SyncState(BaseModel):
    """What the sync control shows, and what pressing it did.

    The same shape answers both the poll and the press, so the interface has one
    thing to render rather than a status and a result that can disagree.
    """

    portals: list[PortalSyncState]
    running: bool
    """Any portal is mid-pass."""
    retry_after_seconds: int
    """Seconds until a sync may be started. ``0`` means now."""
    cooldown_seconds: int
    """The configured gap, so the interface can say how long the wait will be."""
    auto_sync: bool
    """Whether this deployment pulls an empty pool by itself.

    Carried here rather than read from a second endpoint, because the control
    that would act on it is already rendering this payload."""
    pool_size: int
    """Notices held, across every portal.

    Reported here so one request answers both "may I sync" and "is there
    anything to sync for". Zero is the only emptiness a sync can fix: an
    organization with a full pool and no matches has a profile or a rule
    problem, and pulling the portals again would change nothing for it."""
    queued: list[str] = []
    """Portal codes this request put on the queue. Empty on a poll, and empty on
    a press that was refused or found every portal already running."""


class TenderSummary(BaseModel):
    """A row in a list. Deliberately narrow so listing stays cheap."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_code: str
    external_id: str
    title: str
    summary: str | None = None
    procuring_entity: str | None = None
    country: str | None = None
    procurement_method: str | None = None
    procurement_category: ProcurementCategory
    published_at: datetime | None = None
    deadline_at: datetime | None = None
    currency: str | None = None
    estimated_value: float | None = None
    status: TenderStatus
    canonical_url: str
    days_to_deadline: int | None = None


class TenderDetail(TenderSummary):
    description: str | None = None
    language: str | None = None
    portal_metadata: dict[str, Any] = Field(default_factory=dict)
    version: int
    first_seen_at: datetime
    last_seen_at: datetime
    extraction: dict[str, Any] | None = None
    """Structured requirements, when the extraction step has run."""


class TenderSortField(StrEnum):
    """Columns a client may order by.

    An allowlist rather than a free string: the value reaches an ORDER BY.
    """

    PUBLISHED_AT = "published_at"
    DEADLINE_AT = "deadline_at"
    TITLE = "title"
    ESTIMATED_VALUE = "estimated_value"


class TenderFilters(BaseModel):
    q: str | None = None
    source: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    category: list[ProcurementCategory] = Field(default_factory=list)
    status: list[TenderStatus] = Field(default_factory=list)
    deadline_from: datetime | None = None
    deadline_to: datetime | None = None
    deadline_within_days: int | None = None
    open_only: bool = False
    sort: TenderSortField = TenderSortField.PUBLISHED_AT
    descending: bool = True


def tender_filters(
    q: Annotated[
        str | None, Query(description="Free-text search over title, summary and buyer")
    ] = None,
    source: Annotated[list[str] | None, Query(description="Source codes")] = None,
    country: Annotated[list[str] | None, Query(description="ISO 3166-1 alpha-2 codes")] = None,
    category: Annotated[list[ProcurementCategory] | None, Query()] = None,
    status: Annotated[list[TenderStatus] | None, Query()] = None,
    deadline_from: Annotated[datetime | None, Query()] = None,
    deadline_to: Annotated[datetime | None, Query()] = None,
    deadline_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    open_only: Annotated[bool, Query(description="Exclude closed and expired notices")] = False,
    sort: Annotated[TenderSortField, Query()] = TenderSortField.PUBLISHED_AT,
    descending: Annotated[bool, Query()] = True,
) -> TenderFilters:
    return TenderFilters(
        q=q,
        source=source or [],
        country=country or [],
        category=category or [],
        status=status or [],
        deadline_from=deadline_from,
        deadline_to=deadline_to,
        deadline_within_days=deadline_within_days,
        open_only=open_only,
        sort=sort,
        descending=descending,
    )


class TenderFacets(BaseModel):
    """Counts for the filter sidebar, so options can show their sizes."""

    by_source: dict[str, int] = Field(default_factory=dict)
    by_category: dict[str, int] = Field(default_factory=dict)
    by_country: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    closing_within_7_days: int = 0
    total: int = 0
