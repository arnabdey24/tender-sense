"""Turning vectors into a verdict.

Everything here is a pure function of already-stored values, which is what makes
re-grading cheap: changing a threshold re-runs this module over similarities
that are already in the database, without a single AI call.

The aggregation is deliberately not "best facet wins". A company's strongest
facet alone rewards one lucky sentence — a boilerplate line about "digital
transformation" would make every IT tender look like an S. Blending the best
facet with the mean of the top few means a tender has to resemble *several*
things the company actually does before it grades highly.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from app.core.time import to_timezone, utcnow
from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    Recommendation,
    Urgency,
)

#: Day boundaries for urgency, evaluated in the organization's own timezone.
CRITICAL_DAYS = 3
HIGH_DAYS = 7
NORMAL_DAYS = 21


@dataclass(frozen=True, slots=True)
class Thresholds:
    """Grade cut-offs and the aggregation weights, from ``matching_config``."""

    grade_s: float = 0.78
    grade_a: float = 0.70
    grade_b: float = 0.62
    max_facet_weight: float = 0.6
    mean_facet_weight: float = 0.4
    top_facets: int = 3
    version: int = 1


@dataclass(frozen=True, slots=True)
class FacetScore:
    """How well one profile facet matched, and which tender chunk did it."""

    facet_kind: str
    label: str
    score: float
    chunk_kind: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "facet_kind": self.facet_kind,
            "label": self.label,
            "score": round(self.score, 4),
            "chunk_kind": self.chunk_kind,
        }


@dataclass(slots=True)
class ScoreResult:
    similarity: float
    facets: list[FacetScore] = field(default_factory=list)

    def breakdown(self, limit: int = 5) -> dict[str, object]:
        """What the UI shows: the headline number and what drove it."""
        ranked = sorted(self.facets, key=lambda f: f.score, reverse=True)
        return {
            "similarity": round(self.similarity, 4),
            "top_facets": [facet.as_dict() for facet in ranked[:limit]],
            "facet_count": len(self.facets),
        }

    @property
    def best_facet(self) -> FacetScore | None:
        return max(self.facets, key=lambda f: f.score, default=None)


def cosine(a: list[float], b: list[float]) -> float:
    """Dot product. Both sides are unit vectors, so this *is* the cosine.

    The embedding client normalises everything it returns, precisely so this
    stays a dot product instead of two square roots per comparison.
    """
    return sum(x * y for x, y in zip(a, b, strict=True))


def score_facets(
    *,
    facet_vectors: list[tuple[str, str, list[float]]],
    chunk_vectors: list[tuple[str, list[float]]],
    thresholds: Thresholds | None = None,
) -> ScoreResult:
    """Score one tender against one profile.

    ``facet_vectors`` is ``(facet_kind, label, vector)`` per profile facet;
    ``chunk_vectors`` is ``(chunk_kind, vector)`` per tender chunk. Each facet
    takes its best chunk, because a facet matching *any* part of the notice is
    a match — a service that fits the scope should not be diluted by also being
    compared against the title.
    """
    config = thresholds or Thresholds()
    if not facet_vectors or not chunk_vectors:
        return ScoreResult(similarity=0.0)

    scored: list[FacetScore] = []
    for facet_kind, label, facet_vector in facet_vectors:
        best_score = -1.0
        best_chunk = ""
        for chunk_kind, chunk_vector in chunk_vectors:
            value = cosine(facet_vector, chunk_vector)
            if value > best_score:
                best_score, best_chunk = value, chunk_kind
        scored.append(
            FacetScore(facet_kind=facet_kind, label=label, score=best_score, chunk_kind=best_chunk)
        )

    ranked = sorted((facet.score for facet in scored), reverse=True)
    top = ranked[: max(1, config.top_facets)]
    similarity = config.max_facet_weight * ranked[0] + config.mean_facet_weight * (
        sum(top) / len(top)
    )
    # Cosine can land just outside [-1, 1] through float error, and a similarity
    # above 1 would read as a bug everywhere it is displayed.
    similarity = max(-1.0, min(1.0, similarity))
    return ScoreResult(similarity=similarity, facets=scored)


def grade_for(similarity: float, thresholds: Thresholds | None = None) -> MatchGrade:
    """Pure arithmetic, so re-grading needs no AI call."""
    config = thresholds or Thresholds()
    if similarity >= config.grade_s:
        return MatchGrade.S
    if similarity >= config.grade_a:
        return MatchGrade.A
    if similarity >= config.grade_b:
        return MatchGrade.B
    return MatchGrade.C


def urgency_for(
    deadline: datetime | None, *, timezone: str, now: datetime | None = None
) -> Urgency:
    """How pressing the deadline is, in the organization's own timezone.

    The timezone matters at the boundary: a deadline at 01:00 UTC is *tomorrow*
    in Dhaka, and a Dhaka company reading "closes today" about something that
    closed yesterday for them would be actively misled.
    """
    if deadline is None:
        return Urgency.UNKNOWN

    moment = now or utcnow()
    if deadline <= moment:
        return Urgency.EXPIRED

    local_now = to_timezone(moment, timezone).date()
    local_deadline = to_timezone(deadline, timezone).date()
    days = (local_deadline - local_now).days

    if days <= CRITICAL_DAYS:
        return Urgency.CRITICAL
    if days <= HIGH_DAYS:
        return Urgency.HIGH
    if days <= NORMAL_DAYS:
        return Urgency.NORMAL
    return Urgency.LOW


#: Grade x eligibility -> what we suggest doing. Kept as data rather than
#: branches so the matrix can be read, tested and argued about as a whole.
_RECOMMENDATIONS: dict[tuple[MatchGrade, EligibilityStatus], Recommendation] = {
    (MatchGrade.S, EligibilityStatus.ELIGIBLE): Recommendation.BID,
    (MatchGrade.S, EligibilityStatus.NEEDS_VERIFICATION): Recommendation.HOLD,
    (MatchGrade.S, EligibilityStatus.INELIGIBLE): Recommendation.SKIP,
    (MatchGrade.A, EligibilityStatus.ELIGIBLE): Recommendation.BID,
    (MatchGrade.A, EligibilityStatus.NEEDS_VERIFICATION): Recommendation.HOLD,
    (MatchGrade.A, EligibilityStatus.INELIGIBLE): Recommendation.SKIP,
    (MatchGrade.B, EligibilityStatus.ELIGIBLE): Recommendation.HOLD,
    (MatchGrade.B, EligibilityStatus.NEEDS_VERIFICATION): Recommendation.HOLD,
    (MatchGrade.B, EligibilityStatus.INELIGIBLE): Recommendation.SKIP,
    (MatchGrade.C, EligibilityStatus.ELIGIBLE): Recommendation.SKIP,
    (MatchGrade.C, EligibilityStatus.NEEDS_VERIFICATION): Recommendation.SKIP,
    (MatchGrade.C, EligibilityStatus.INELIGIBLE): Recommendation.SKIP,
}


def recommend(
    grade: MatchGrade, eligibility: EligibilityStatus, urgency: Urgency
) -> Recommendation:
    """What to suggest doing about this tender.

    An expired deadline overrides everything: there is nothing to recommend
    about a tender that can no longer be bid on, however well it fits.
    """
    if urgency is Urgency.EXPIRED:
        return Recommendation.SKIP
    return _RECOMMENDATIONS[(grade, eligibility)]


def inputs_fingerprint(
    *,
    profile_version: int,
    rule_set_version_id: str | None,
    extraction_id: str | None,
    embedding_model: str,
    thresholds_version: int,
    tender_content_hash: str,
) -> str:
    """Digest of everything a match depends on.

    If this is unchanged the match cannot have changed, so the whole scoring
    path — and the AI calls behind it — is skipped. Deliberately excludes the
    clock: a match does not become stale merely by aging, only urgency does,
    and urgency is recomputed on read.
    """
    parts = [
        str(profile_version),
        rule_set_version_id or "",
        extraction_id or "",
        embedding_model,
        str(thresholds_version),
        tender_content_hash,
    ]
    return hashlib.sha256("␟".join(parts).encode()).hexdigest()
