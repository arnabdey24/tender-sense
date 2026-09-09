"""What one organization thinks of one tender.

A match is per-tenant even though the tender is shared, and it is deliberately
a *derived* row: everything on it can be recomputed from the profile version,
rule-set version, extraction, embedding model and thresholds it records. That is
what `inputs_fingerprint` captures — if none of those changed, the match cannot
have changed, and the whole expensive path is skipped.

Keeping the provenance on the row is also what makes a score defensible months
later: "graded A" is not useful, "graded A against profile v7 and rule set v3,
using extraction #412 and thresholds v2" is.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def _pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )


class MatchGrade(enum.StrEnum):
    """How well the tender fits, before eligibility is considered."""

    S = "S"
    A = "A"
    B = "B"
    C = "C"


class EligibilityStatus(enum.StrEnum):
    ELIGIBLE = "eligible"
    NEEDS_VERIFICATION = "needs_verification"
    """A hard rule could not be decided — usually a missing or low-confidence
    attribute. Never treated as a rejection: the tender surfaces for a human."""
    INELIGIBLE = "ineligible"


class Recommendation(enum.StrEnum):
    BID = "bid"
    HOLD = "hold"
    SKIP = "skip"


class Urgency(enum.StrEnum):
    """Derived from the deadline in the organization's own timezone."""

    EXPIRED = "expired"
    CRITICAL = "critical"
    """Three days or fewer."""
    HIGH = "high"
    """A week or fewer."""
    NORMAL = "normal"
    LOW = "low"
    UNKNOWN = "unknown"
    """No deadline on the notice."""


class ExplanationKind(enum.StrEnum):
    TEMPLATED = "templated"
    """Built from structured data. Always present."""
    LLM = "llm"
    """Written by the model, for matches worth the tokens."""


class TenderMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One organization's verdict on one tender."""

    __tablename__ = "tender_matches"
    __table_args__ = (
        UniqueConstraint("org_id", "tender_id"),
        # Every feed query leads with org_id, so each index does too.
        Index("ix_tender_matches_org_id_grade", "org_id", "grade"),
        Index("ix_tender_matches_org_id_created_at", "org_id", "created_at"),
        Index("ix_tender_matches_org_id_similarity", "org_id", "similarity"),
        Index("ix_tender_matches_tender_id", "tender_id"),
    )

    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    tender_id: Mapped[UUID] = mapped_column(ForeignKey("tenders.id", ondelete="CASCADE"))

    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    #: Per-facet scores behind the headline number, so the UI can say *which*
    #: service or past project made this look like a fit.
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    grade: Mapped[MatchGrade] = mapped_column(_pg_enum(MatchGrade, "match_grade"))

    eligibility_status: Mapped[EligibilityStatus] = mapped_column(
        _pg_enum(EligibilityStatus, "eligibility_status"),
        default=EligibilityStatus.NEEDS_VERIFICATION,
    )
    #: One entry per evaluated rule: status, the tender's value, what was
    #: expected, and why. This is what the eligibility tab renders.
    rule_results: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")

    recommendation: Mapped[Recommendation] = mapped_column(
        _pg_enum(Recommendation, "recommendation"), default=Recommendation.HOLD
    )
    urgency: Mapped[Urgency] = mapped_column(_pg_enum(Urgency, "urgency"), default=Urgency.UNKNOWN)

    explanation_kind: Mapped[ExplanationKind] = mapped_column(
        _pg_enum(ExplanationKind, "explanation_kind"), default=ExplanationKind.TEMPLATED
    )
    explanation_text: Mapped[str | None] = mapped_column(Text, default=None)
    #: Structured form (summary, why_matched, gaps, risks, next_step) when the
    #: model wrote it; the templated version fills the same shape.
    explanation: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")

    # -- provenance: everything needed to decide whether to recompute --------
    #: sha256 over profile version, rule set version, extraction, embedding
    #: model, thresholds version and the tender's content hash. Unchanged means
    #: the match cannot have changed, so the expensive path is skipped.
    inputs_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1)
    rule_set_version_id: Mapped[UUID | None] = mapped_column(default=None)
    extraction_id: Mapped[UUID | None] = mapped_column(default=None)
    embedding_model: Mapped[str] = mapped_column(String(100), default="")
    thresholds_version: Mapped[int] = mapped_column(Integer, default=1)

    #: Set when an instant alert went out, so it can never go out twice.
    instant_notified_at: Mapped[datetime | None] = mapped_column(default=None)
    #: Distinguishes "new since your last digest" from "seen before".
    first_matched_at: Mapped[datetime | None] = mapped_column(default=None)


class TenderMatchHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A row per time a match's verdict actually moved.

    Written only when grade, eligibility or recommendation changes — not on
    every recompute — so the timeline shows decisions, not noise.
    """

    __tablename__ = "tender_match_history"
    __table_args__ = (
        Index("ix_tender_match_history_match_id_created_at", "match_id", "created_at"),
    )

    match_id: Mapped[UUID] = mapped_column(ForeignKey("tender_matches.id", ondelete="CASCADE"))
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    similarity: Mapped[float] = mapped_column(Float, default=0.0)
    grade: Mapped[MatchGrade] = mapped_column(_pg_enum(MatchGrade, "match_grade"))
    eligibility_status: Mapped[EligibilityStatus] = mapped_column(
        _pg_enum(EligibilityStatus, "eligibility_status")
    )
    recommendation: Mapped[Recommendation] = mapped_column(
        _pg_enum(Recommendation, "recommendation")
    )
    #: Why it moved: "profile_edited", "rules_changed", "tender_amended".
    reason: Mapped[str] = mapped_column(String(100), default="")


class MatchingConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tunable scoring parameters, in the database rather than in code.

    A single active row. Thresholds are fitted by `scripts/calibrate_thresholds.py`
    against the labelled set; bumping ``thresholds_version`` re-grades every
    match without a single AI call, because grading is pure arithmetic over
    similarities that are already stored.
    """

    __tablename__ = "matching_config"

    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", index=True)
    thresholds_version: Mapped[int] = mapped_column(Integer, default=1)

    grade_s_threshold: Mapped[float] = mapped_column(Float, default=0.78)
    grade_a_threshold: Mapped[float] = mapped_column(Float, default=0.70)
    grade_b_threshold: Mapped[float] = mapped_column(Float, default=0.62)

    #: `sim = max_weight * best_facet + mean_weight * mean(top N facets)`.
    #: The best facet alone rewards a single strong overlap; the mean of the
    #: top few stops one lucky sentence from carrying an otherwise poor fit.
    max_facet_weight: Mapped[float] = mapped_column(Float, default=0.6)
    mean_facet_weight: Mapped[float] = mapped_column(Float, default=0.4)
    top_facets: Mapped[int] = mapped_column(Integer, default=3)

    #: Optional hybrid keyword term blended into the semantic score.
    keyword_weight: Mapped[float] = mapped_column(Float, default=0.0)

    embedding_model: Mapped[str] = mapped_column(String(100), default="")
    generation_model: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str | None] = mapped_column(Text, default=None)
