"""The match feed: this organization's graded view of the shared pool."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from app.core.deps import CurrentOrg, DbSession
from app.core.exceptions import NotFoundError
from app.core.pagination import Page, PageParams, page_params
from app.core.time import to_timezone, utcnow
from app.modules.matching import repository as repo
from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    Recommendation,
    TenderMatch,
    Urgency,
)
from app.modules.matching.schemas import (
    MatchDetail,
    MatchFilters,
    MatchRead,
    MatchSortField,
    MatchStats,
    match_filters,
)
from app.modules.tenders.models import Tender
from app.modules.tenders.service import to_summary

router = APIRouter(tags=["matches"])

Filters = Annotated[MatchFilters, Depends(match_filters)]
Pagination = Annotated[PageParams, Depends(page_params)]
TenderId = Annotated[UUID, Path(description="Tender identifier")]


def _to_read(match: TenderMatch, tender: Tender, source_code: str) -> MatchRead:
    return MatchRead(
        id=match.id,
        tender_id=match.tender_id,
        similarity=match.similarity,
        grade=match.grade,
        eligibility_status=match.eligibility_status,
        recommendation=match.recommendation,
        urgency=match.urgency,
        explanation_kind=match.explanation_kind,
        explanation=match.explanation,
        explanation_text=match.explanation_text,
        score_breakdown=match.score_breakdown,
        rule_results=match.rule_results,
        first_matched_at=match.first_matched_at,
        created_at=match.created_at,
        tender=to_summary(tender, source_code),
    )


@router.get("/matches", response_model=Page[MatchRead], summary="The match feed")
async def list_matches(
    ctx: CurrentOrg, db: DbSession, filters: Filters, params: Pagination
) -> Page[MatchRead]:
    """This organization's graded tenders, best fit first by default.

    Defaults to open notices only: a feed leading with tenders that already
    closed wastes the reader's attention on decisions they cannot make.
    """
    rows, total = await repo.list_matches(db, org_id=ctx.org_id, filters=filters, params=params)
    return Page[MatchRead].build(
        [_to_read(match, tender, code) for match, tender, code in rows], params, total
    )


@router.get("/matches/stats", response_model=MatchStats, summary="Feed counts")
async def match_stats(ctx: CurrentOrg, db: DbSession, filters: Filters) -> MatchStats:
    """Counts under the same filters as the list, for chips and the dashboard."""
    by_grade = await repo.count_by(db, org_id=ctx.org_id, column=TenderMatch.grade, filters=filters)
    # Midnight in the organization's own timezone, so "new today" means their
    # today rather than UTC's.
    local_midnight = to_timezone(utcnow(), ctx.org.timezone).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    return MatchStats(
        total=sum(by_grade.values()),
        by_grade=by_grade,
        by_eligibility=await repo.count_by(
            db, org_id=ctx.org_id, column=TenderMatch.eligibility_status, filters=filters
        ),
        by_recommendation=await repo.count_by(
            db, org_id=ctx.org_id, column=TenderMatch.recommendation, filters=filters
        ),
        by_urgency=await repo.count_by(
            db, org_id=ctx.org_id, column=TenderMatch.urgency, filters=filters
        ),
        closing_within_7_days=await repo.count_closing_within(
            db, org_id=ctx.org_id, days=7, filters=filters
        ),
        new_today=await repo.count_since(
            db, org_id=ctx.org_id, moment=local_midnight, filters=filters
        ),
    )


@router.get("/matches/today", response_model=Page[MatchRead], summary="Today's shortlist")
async def today_shortlist(
    ctx: CurrentOrg, db: DbSession, filters: Filters, params: Pagination
) -> Page[MatchRead]:
    """What arrived since yesterday, worth acting on.

    Narrower than the feed on purpose: S and A grades that are not already
    ruled out. The point of a shortlist is that it is short.
    """
    shortlist = filters.model_copy(
        update={
            "grade": filters.grade or [MatchGrade.S, MatchGrade.A],
            "eligibility": filters.eligibility
            or [EligibilityStatus.ELIGIBLE, EligibilityStatus.NEEDS_VERIFICATION],
            "since": filters.since or (utcnow() - timedelta(days=1)),
            "open_only": True,
        }
    )
    rows, total = await repo.list_matches(db, org_id=ctx.org_id, filters=shortlist, params=params)
    return Page[MatchRead].build(
        [_to_read(match, tender, code) for match, tender, code in rows], params, total
    )


@router.get("/matches/{tender_id}", response_model=MatchDetail, summary="One match")
async def get_match(tender_id: TenderId, ctx: CurrentOrg, db: DbSession) -> MatchDetail:
    """This organization's verdict on one tender, with its provenance."""
    row = await repo.get_match(db, org_id=ctx.org_id, tender_id=tender_id)
    if row is None:
        raise NotFoundError("No match for this tender.", code="match_not_found")
    match, tender, code = row
    return MatchDetail(
        **_to_read(match, tender, code).model_dump(),
        profile_version=match.profile_version,
        thresholds_version=match.thresholds_version,
        embedding_model=match.embedding_model,
        extraction_id=match.extraction_id,
    )


@router.get("/pipeline", response_model=Page[MatchRead], summary="Matches worth acting on")
async def pipeline(
    ctx: CurrentOrg, db: DbSession, filters: Filters, params: Pagination
) -> Page[MatchRead]:
    """Everything recommended as a bid or a hold, soonest deadline first."""
    working = filters.model_copy(
        update={
            "recommendation": filters.recommendation or [Recommendation.BID, Recommendation.HOLD],
            "urgency": filters.urgency
            or [Urgency.CRITICAL, Urgency.HIGH, Urgency.NORMAL, Urgency.LOW, Urgency.UNKNOWN],
            "sort": MatchSortField.DEADLINE,
            "descending": False,
        }
    )
    rows, total = await repo.list_matches(db, org_id=ctx.org_id, filters=working, params=params)
    return Page[MatchRead].build(
        [_to_read(match, tender, code) for match, tender, code in rows], params, total
    )
