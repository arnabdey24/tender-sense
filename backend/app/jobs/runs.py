"""Recording what background work did, so a silent failure is visible.

A scraper that quietly stops returning notices looks exactly like a portal with
nothing new to publish. The only difference is in the run record — which is why
every run is written down whether it succeeded or not, and why a source's health
is derived from consecutive failures rather than from the last one alone.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    """Finished, but some notices were lost. Worth seeing; not worth alerting."""


class JobRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of any background task."""

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_name_started_at", "name", "started_at"),
        Index("ix_job_runs_status", "status"),
    )

    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(
        _pg_enum(RunStatus, "run_status"), default=RunStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    #: Whatever the task returned, so a run can be inspected without log diving.
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text, default=None)


class ScraperRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One pass over one portal, with the counts that show whether it worked."""

    __tablename__ = "scraper_runs"
    __table_args__ = (Index("ix_scraper_runs_source_id_started_at", "source_id", "started_at"),)

    source_id: Mapped[UUID] = mapped_column(ForeignKey("tender_sources.id", ondelete="CASCADE"))
    status: Mapped[RunStatus] = mapped_column(
        _pg_enum(RunStatus, "run_status"), default=RunStatus.RUNNING
    )
    started_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column(default=None)

    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    notices_seen: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
