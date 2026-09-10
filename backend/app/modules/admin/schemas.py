"""Request and response bodies for the superuser admin surface."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.adapters.base import TenderIn
from app.modules.tenders.models import SourceHealth


class SourceCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    adapter_key: str = Field(min_length=1, max_length=50)
    base_url: str = Field(default="", max_length=500)
    country: str | None = Field(default=None, max_length=2)
    enabled: bool = True
    schedule_cron: str | None = Field(default=None, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)


class SourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    adapter_key: str | None = Field(default=None, min_length=1, max_length=50)
    base_url: str | None = Field(default=None, max_length=500)
    country: str | None = Field(default=None, max_length=2)
    enabled: bool | None = None
    schedule_cron: str | None = Field(default=None, max_length=100)
    config: dict[str, Any] | None = None


class SourceAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    adapter_key: str
    base_url: str
    country: str | None = None
    enabled: bool
    schedule_cron: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    cursor: dict[str, Any] = Field(default_factory=dict)
    health: SourceHealth
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    consecutive_failures: int


class SourceRunResponse(BaseModel):
    source_code: str
    job_id: str | None = None
    enqueued: bool


class TenderCreate(TenderIn):
    """A hand-entered notice. ``source_code`` picks the pool it lands in."""

    source_code: str = "manual"


class TenderCreateResponse(BaseModel):
    tender_id: UUID
    outcome: str
    version: int


class ImportResponse(BaseModel):
    total: int
    created: int
    updated: int
    unchanged: int
    failed: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


class ScraperRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    notices_seen: int
    created: int
    updated: int
    unchanged: int
    failed: int
    error: str | None = None


class SourceHealthCheck(BaseModel):
    """A live probe, distinct from the health recorded by past runs."""

    source_code: str
    reachable: bool
    detail: str | None = None


class ReprocessResponse(BaseModel):
    tender_id: UUID
    enqueued: bool
    job_id: str | None = None


class ReparseResponse(BaseModel):
    """A replay of stored payloads through the adapter's parser."""

    source_code: str
    enqueued: bool
    job_id: str | None = None


class JobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class JobTriggerRequest(BaseModel):
    job: str = Field(min_length=1, max_length=100)


class JobTriggerResponse(BaseModel):
    job: str
    job_id: str | None = None
    enqueued: bool


class EmailOutboxRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    to_email: str
    template_key: str
    subject: str
    status: str
    attempts: int
    next_attempt_at: datetime
    last_error: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class EmailRetryResponse(BaseModel):
    email_id: UUID
    requeued: bool


class AiUsageRow(BaseModel):
    day: date
    purpose: str
    model: str
    calls: int
    tokens_in: int
    tokens_out: int


class AiUsageSummary(BaseModel):
    """Spend against the daily cap, so an exhausted budget is visible."""

    daily_token_budget: int
    spent_today: int
    rows: list[AiUsageRow] = Field(default_factory=list)
