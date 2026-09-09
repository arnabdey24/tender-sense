"""Request and response bodies for the match feed."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.modules.matching.models import (
    EligibilityStatus,
    ExplanationKind,
    MatchGrade,
    Recommendation,
    Urgency,
)
from app.modules.tenders.schemas import TenderSummary


class MatchSortField(StrEnum):
    """Columns a client may order by. An allowlist: the value reaches ORDER BY."""

    SIMILARITY = "similarity"
    DEADLINE = "deadline_at"
    PUBLISHED = "published_at"
    CREATED = "created_at"


class MatchRead(BaseModel):
    """One graded tender, with enough of the notice to render a feed row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tender_id: UUID
    similarity: float
    grade: MatchGrade
    eligibility_status: EligibilityStatus
    recommendation: Recommendation
    urgency: Urgency
    explanation_kind: ExplanationKind
    explanation: dict[str, Any] = Field(default_factory=dict)
    explanation_text: str | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    rule_results: list[Any] = Field(default_factory=list)
    first_matched_at: datetime | None = None
    created_at: datetime
    tender: TenderSummary


class MatchDetail(MatchRead):
    profile_version: int
    thresholds_version: int
    embedding_model: str
    extraction_id: UUID | None = None


class MatchFilters(BaseModel):
    grade: list[MatchGrade] = Field(default_factory=list)
    eligibility: list[EligibilityStatus] = Field(default_factory=list)
    recommendation: list[Recommendation] = Field(default_factory=list)
    urgency: list[Urgency] = Field(default_factory=list)
    q: str | None = None
    deadline_within_days: int | None = None
    open_only: bool = True
    """Feeds default to what can still be bid on; the pool browser does not."""
    since: datetime | None = None
    sort: MatchSortField = MatchSortField.SIMILARITY
    descending: bool = True


def match_filters(
    grade: Annotated[list[MatchGrade] | None, Query()] = None,
    eligibility: Annotated[list[EligibilityStatus] | None, Query()] = None,
    recommendation: Annotated[list[Recommendation] | None, Query()] = None,
    urgency: Annotated[list[Urgency] | None, Query()] = None,
    q: Annotated[str | None, Query(description="Search the notice title and buyer")] = None,
    deadline_within_days: Annotated[int | None, Query(ge=0, le=365)] = None,
    open_only: Annotated[bool, Query(description="Exclude closed and expired")] = True,
    since: Annotated[
        datetime | None, Query(description="Only matches first seen after this moment")
    ] = None,
    sort: Annotated[MatchSortField, Query()] = MatchSortField.SIMILARITY,
    descending: Annotated[bool, Query()] = True,
) -> MatchFilters:
    return MatchFilters(
        grade=grade or [],
        eligibility=eligibility or [],
        recommendation=recommendation or [],
        urgency=urgency or [],
        q=q,
        deadline_within_days=deadline_within_days,
        open_only=open_only,
        since=since,
        sort=sort,
        descending=descending,
    )


class MatchStats(BaseModel):
    """Counts for the dashboard and the feed's filter chips."""

    total: int = 0
    by_grade: dict[str, int] = Field(default_factory=dict)
    by_eligibility: dict[str, int] = Field(default_factory=dict)
    by_recommendation: dict[str, int] = Field(default_factory=dict)
    by_urgency: dict[str, int] = Field(default_factory=dict)
    closing_within_7_days: int = 0
    new_today: int = 0
