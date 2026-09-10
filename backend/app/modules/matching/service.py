"""Producing and storing one organization's verdict on one tender.

The expensive work is guarded by `inputs_fingerprint`: if the profile, rules,
extraction, embedding model, thresholds and tender content are all unchanged,
the previous verdict still stands and nothing is recomputed. Urgency is the one
exception — it moves with the clock rather than with any input — so it is
refreshed even on a skipped match, which is what lets a daily sweep age a
deadline from "normal" to "critical" without re-scoring anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.explanation import explanation_to_text, templated_explanation
from app.core.logging import get_logger
from app.core.observability import matches_scored
from app.core.time import utcnow
from app.modules.matching.embedding_store import load_profile_vectors, load_tender_vectors
from app.modules.matching.models import (
    ExplanationKind,
    MatchGrade,
    MatchingConfig,
    TenderMatch,
    TenderMatchHistory,
)
from app.modules.matching.scoring import (
    Thresholds,
    grade_for,
    inputs_fingerprint,
    recommend,
    score_facets,
    urgency_for,
)
from app.modules.orgs.models import Organization
from app.modules.profiles.models import CompanyProfile
from app.modules.rules.service import active_version, definition_of, evaluate_for_tender
from app.modules.tenders.models import Tender, TenderExtraction

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    match_id: UUID | None
    created: bool = False
    updated: bool = False
    skipped: bool = False
    not_scorable: bool = False
    """One side had no vectors, so no verdict was stored."""
    grade: MatchGrade | None = None

    @property
    def changed(self) -> bool:
        return self.created or self.updated


async def active_thresholds(session: AsyncSession) -> Thresholds:
    """Scoring parameters from the database, falling back to the defaults.

    Kept in a row rather than in code so calibration can retune grading without
    a deployment — and so a re-grade is a background job, not a release.
    """
    config = await session.scalar(
        select(MatchingConfig)
        .where(MatchingConfig.is_active.is_(True))
        .order_by(MatchingConfig.created_at.desc())
        .limit(1)
    )
    if config is None:
        return Thresholds()
    return Thresholds(
        grade_s=config.grade_s_threshold,
        grade_a=config.grade_a_threshold,
        grade_b=config.grade_b_threshold,
        max_facet_weight=config.max_facet_weight,
        mean_facet_weight=config.mean_facet_weight,
        top_facets=config.top_facets,
        version=config.thresholds_version,
    )


async def current_extraction(session: AsyncSession, tender_id: UUID) -> TenderExtraction | None:
    result: TenderExtraction | None = await session.scalar(
        select(TenderExtraction).where(
            TenderExtraction.tender_id == tender_id, TenderExtraction.is_current.is_(True)
        )
    )
    return result


async def match_tender_for_org(
    session: AsyncSession,
    *,
    tender: Tender,
    org: Organization,
    profile: CompanyProfile,
    embedding_model: str,
    thresholds: Thresholds | None = None,
    reason: str = "",
    force: bool = False,
) -> MatchOutcome:
    """Score, grade and store one match.

    Eligibility comes from the organization's active rule set. An organization
    that has written no rules gets "eligible" — they have not failed to answer
    anything — while an undecidable hard rule surfaces as "needs verification"
    rather than a rejection.
    """
    config = thresholds or await active_thresholds(session)
    extraction = await current_extraction(session, tender.id)
    rule_version = await active_version(session, org.id)

    fingerprint = inputs_fingerprint(
        profile_version=profile.version,
        rule_set_version_id=str(rule_version.id) if rule_version else None,
        extraction_id=str(extraction.id) if extraction else None,
        embedding_model=embedding_model,
        thresholds_version=config.version,
        tender_content_hash=tender.content_hash,
    )

    existing = await session.scalar(
        select(TenderMatch).where(TenderMatch.org_id == org.id, TenderMatch.tender_id == tender.id)
    )

    urgency = urgency_for(tender.deadline_at, timezone=org.timezone)

    if existing is not None and existing.inputs_fingerprint == fingerprint and not force:
        # Nothing that feeds the score changed. Urgency still might have, since
        # it moves with the clock rather than with any input.
        if existing.urgency is not urgency:
            existing.urgency = urgency
            existing.recommendation = recommend(
                existing.grade, existing.eligibility_status, urgency
            )
            await session.flush()
        return MatchOutcome(match_id=existing.id, skipped=True, grade=existing.grade)

    facet_vectors = await load_profile_vectors(session, profile.id, model=embedding_model)
    chunk_vectors = await load_tender_vectors(session, tender.id, model=embedding_model)

    # Scoring against nothing yields 0.0, which would be stored as a C grade —
    # a confident-looking "weak fit" for a comparison that never happened. A
    # brand-new organization hits this on every tender that arrives before its
    # first profile embedding, so the whole feed would read as rejections.
    # Store nothing instead; the match appears once both sides have vectors.
    if not facet_vectors or not chunk_vectors:
        logger.info(
            "match_not_scorable",
            org_id=str(org.id),
            tender_id=str(tender.id),
            profile_facets=len(facet_vectors),
            tender_chunks=len(chunk_vectors),
        )
        return MatchOutcome(match_id=existing.id if existing else None, not_scorable=True)

    score = score_facets(
        facet_vectors=facet_vectors, chunk_vectors=chunk_vectors, thresholds=config
    )

    grade = grade_for(score.similarity, config)

    evaluation = await evaluate_for_tender(
        session,
        tender=tender,
        profile=profile,
        org_id=org.id,
        definition=definition_of(rule_version),
        extraction=extraction,
    )
    eligibility = evaluation.status
    recommendation = recommend(grade, eligibility, urgency)
    explanation = templated_explanation(
        grade=grade,
        eligibility=eligibility,
        urgency=urgency,
        recommendation=recommendation,
        score=score,
        rule_results=evaluation.as_json(),
    )

    now = utcnow()
    if existing is None:
        match = TenderMatch(
            org_id=org.id,
            tender_id=tender.id,
            first_matched_at=now,
        )
        session.add(match)
        created = True
    else:
        match = existing
        created = False

    previous = None if created else (match.grade, match.eligibility_status, match.recommendation)

    match.similarity = score.similarity
    match.score_breakdown = score.breakdown()
    ranked_scores = sorted((facet.score for facet in score.facets), reverse=True)
    match.score_breakdown["calculation"] = {
        "best_score": ranked_scores[0],
        "top_scores": ranked_scores[: max(1, config.top_facets)],
        "max_weight": config.max_facet_weight,
        "mean_weight": config.mean_facet_weight,
        "top_n": config.top_facets,
        "thresholds": {"S": config.grade_s, "A": config.grade_a, "B": config.grade_b},
    }
    match.grade = grade
    match.eligibility_status = eligibility
    match.rule_results = evaluation.as_json()
    match.recommendation = recommendation
    match.urgency = urgency
    match.explanation = explanation
    match.explanation_text = explanation_to_text(explanation)
    match.explanation_kind = ExplanationKind.TEMPLATED
    match.inputs_fingerprint = fingerprint
    match.profile_version = profile.version
    match.extraction_id = extraction.id if extraction else None
    match.rule_set_version_id = rule_version.id if rule_version else None
    match.embedding_model = embedding_model
    match.thresholds_version = config.version
    await session.flush()

    # History records movement, not recomputation — otherwise a nightly sweep
    # would bury the one time a verdict actually changed under identical rows.
    moved = previous is not None and previous != (grade, eligibility, recommendation)
    if created or moved:
        session.add(
            TenderMatchHistory(
                match_id=match.id,
                org_id=org.id,
                similarity=score.similarity,
                grade=grade,
                eligibility_status=eligibility,
                recommendation=recommendation,
                reason=reason or ("first_match" if created else "inputs_changed"),
            )
        )
        await session.flush()

    matches_scored.labels(grade=grade.value).inc()
    logger.info(
        "tender_matched",
        org_id=str(org.id),
        tender_id=str(tender.id),
        grade=grade.value,
        similarity=round(score.similarity, 4),
        created=created,
    )
    return MatchOutcome(match_id=match.id, created=created, updated=not created, grade=grade)


async def orgs_with_profiles(session: AsyncSession) -> list[tuple[Organization, CompanyProfile]]:
    """Every tenant that can actually be matched.

    An organization with no profile has nothing to score against, so it is
    skipped rather than given a row of zeroes it would have to look at.
    """
    rows = await session.execute(
        select(Organization, CompanyProfile)
        .join(CompanyProfile, CompanyProfile.org_id == Organization.id)
        .where(Organization.is_active.is_(True))
    )
    return [(org, profile) for org, profile in rows.all()]
