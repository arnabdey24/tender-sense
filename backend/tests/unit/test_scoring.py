"""Scoring, grading, urgency and the recommendation matrix.

All pure functions, so these are exhaustive rather than representative — the
recommendation matrix in particular is asserted cell by cell, because a wrong
cell is a wrong business decision shown to a customer with no error anywhere.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import time_machine

from app.ai.fake_client import deterministic_embedding
from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    Recommendation,
    Urgency,
)
from app.modules.matching.scoring import (
    Thresholds,
    cosine,
    grade_for,
    inputs_fingerprint,
    recommend,
    score_facets,
    urgency_for,
)

DIMS = 768
DHAKA = "Asia/Dhaka"


def facet(label: str, text: str, kind: str = "service") -> tuple[str, str, list[float]]:
    return (kind, label, deterministic_embedding(text, DIMS))


def chunk(text: str, kind: str = "title_summary") -> tuple[str, list[float]]:
    return (kind, deterministic_embedding(text, DIMS))


class TestCosine:
    def test_a_vector_against_itself_is_one(self) -> None:
        vector = deterministic_embedding("network switches", DIMS)

        assert cosine(vector, vector) == pytest.approx(1.0)

    def test_unrelated_text_scores_lower_than_related_text(self) -> None:
        probe = deterministic_embedding("network switches", DIMS)
        related = deterministic_embedding("network switch installation", DIMS)
        unrelated = deterministic_embedding("dairy cattle feed", DIMS)

        assert cosine(probe, related) > cosine(probe, unrelated)


class TestScoreFacets:
    def test_no_facets_scores_zero_rather_than_failing(self) -> None:
        """A brand-new organization has no profile yet; it must not crash."""
        result = score_facets(facet_vectors=[], chunk_vectors=[chunk("anything")])

        assert result.similarity == 0.0
        assert result.facets == []

    def test_no_chunks_scores_zero(self) -> None:
        result = score_facets(facet_vectors=[facet("A", "a")], chunk_vectors=[])

        assert result.similarity == 0.0

    def test_each_facet_takes_its_best_chunk(self) -> None:
        """A service matching the scope must not be dragged down by the title."""
        result = score_facets(
            facet_vectors=[facet("Networking", "enterprise network switches routers")],
            chunk_vectors=[
                chunk("annual procurement notice reference number", "title_summary"),
                chunk("supply enterprise network switches routers", "scope_requirements"),
            ],
        )

        assert result.facets[0].chunk_kind == "scope_requirements"

    def test_a_relevant_profile_outscores_an_irrelevant_one(self) -> None:
        tender = [chunk("supply and installation of enterprise network switches")]
        relevant = score_facets(
            facet_vectors=[facet("Networking", "enterprise network switches routers cabling")],
            chunk_vectors=tender,
        )
        irrelevant = score_facets(
            facet_vectors=[facet("Printing", "offset printing school textbooks binding")],
            chunk_vectors=tender,
        )

        assert relevant.similarity > irrelevant.similarity

    def test_one_strong_facet_cannot_carry_an_otherwise_poor_profile(self) -> None:
        """Otherwise a single boilerplate line makes every tender an S."""
        tender = [chunk("supply and installation of enterprise network switches")]
        strong = facet("Networking", "enterprise network switches routers cabling")
        noise = [
            facet("Catering", "canteen catering meals"),
            facet("Landscaping", "garden landscaping lawn"),
            facet("Tailoring", "uniform tailoring stitching"),
        ]

        focused = score_facets(facet_vectors=[strong], chunk_vectors=tender)
        diluted = score_facets(facet_vectors=[strong, *noise], chunk_vectors=tender)

        assert diluted.similarity < focused.similarity

    def test_similarity_never_exceeds_one(self) -> None:
        """Float error at the top of the range would read as a bug in the UI."""
        identical = deterministic_embedding("exactly the same words", DIMS)
        result = score_facets(
            facet_vectors=[("service", "A", identical)],
            chunk_vectors=[("title_summary", identical)],
        )

        assert result.similarity <= 1.0

    def test_the_breakdown_names_what_drove_the_score(self) -> None:
        result = score_facets(
            facet_vectors=[
                facet("Networking", "enterprise network switches"),
                facet("Catering", "canteen meals"),
            ],
            chunk_vectors=[chunk("supply of enterprise network switches")],
        )

        breakdown = result.breakdown()
        assert breakdown["facet_count"] == 2
        assert breakdown["top_facets"][0]["label"] == "Networking"  # type: ignore[index]
        assert result.best_facet is not None
        assert result.best_facet.label == "Networking"


class TestGrading:
    @pytest.mark.parametrize(
        ("similarity", "expected"),
        [
            (1.00, MatchGrade.S),
            (0.79, MatchGrade.S),
            (0.78, MatchGrade.S),  # boundary is inclusive
            (0.7799, MatchGrade.A),
            (0.70, MatchGrade.A),
            (0.6999, MatchGrade.B),
            (0.62, MatchGrade.B),
            (0.6199, MatchGrade.C),
            (0.0, MatchGrade.C),
            (-1.0, MatchGrade.C),
        ],
    )
    def test_grade_boundaries(self, similarity: float, expected: MatchGrade) -> None:
        assert grade_for(similarity) is expected

    def test_thresholds_can_be_retuned_without_touching_code(self) -> None:
        """Calibration writes new thresholds; re-grading must follow them."""
        lenient = Thresholds(grade_s=0.5, grade_a=0.4, grade_b=0.3)

        assert grade_for(0.55, lenient) is MatchGrade.S
        assert grade_for(0.55) is MatchGrade.C


class TestUrgency:
    def test_a_notice_with_no_deadline_is_unknown(self) -> None:
        assert urgency_for(None, timezone=DHAKA) is Urgency.UNKNOWN

    @time_machine.travel("2026-09-10T06:00:00Z", tick=False)
    @pytest.mark.parametrize(
        ("days_ahead", "expected"),
        [
            (-1, Urgency.EXPIRED),
            (1, Urgency.CRITICAL),
            (3, Urgency.CRITICAL),
            (4, Urgency.HIGH),
            (7, Urgency.HIGH),
            (8, Urgency.NORMAL),
            (21, Urgency.NORMAL),
            (22, Urgency.LOW),
            (365, Urgency.LOW),
        ],
    )
    def test_bands(self, days_ahead: int, expected: Urgency) -> None:
        deadline = datetime(2026, 9, 10, 6, 0, tzinfo=UTC) + timedelta(days=days_ahead)

        assert urgency_for(deadline, timezone=DHAKA) is expected

    @time_machine.travel("2026-09-10T20:00:00Z", tick=False)
    def test_a_deadline_is_judged_in_the_organizations_own_day(self) -> None:
        """20:00 UTC is already the 11th in Dhaka (UTC+6).

        A deadline at 02:00 UTC on the 11th is still the 11th locally — the
        same day — so it is critical, not a day away. Judging it in UTC would
        put it a day out and tell a Dhaka bidder they had longer than they do.
        """
        deadline = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)

        assert urgency_for(deadline, timezone=DHAKA) is Urgency.CRITICAL

    @time_machine.travel("2026-09-10T06:00:00Z", tick=False)
    def test_the_same_instant_bands_differently_across_timezones(self) -> None:
        """The whole reason urgency takes a timezone at all."""
        deadline = datetime(2026, 9, 13, 20, 0, tzinfo=UTC)

        # 13 Sep 20:00 UTC is the 14th in Dhaka: four days out, so HIGH.
        assert urgency_for(deadline, timezone=DHAKA) is Urgency.HIGH
        # Still the 13th in London: three days out, so CRITICAL.
        assert urgency_for(deadline, timezone="Europe/London") is Urgency.CRITICAL

    @time_machine.travel("2026-09-10T06:00:00Z", tick=False)
    def test_a_deadline_that_has_just_passed_is_expired(self) -> None:
        deadline = datetime(2026, 9, 10, 5, 59, tzinfo=UTC)

        assert urgency_for(deadline, timezone=DHAKA) is Urgency.EXPIRED


class TestRecommendation:
    @pytest.mark.parametrize(
        ("grade", "eligibility", "expected"),
        [
            (MatchGrade.S, EligibilityStatus.ELIGIBLE, Recommendation.BID),
            (MatchGrade.S, EligibilityStatus.NEEDS_VERIFICATION, Recommendation.HOLD),
            (MatchGrade.S, EligibilityStatus.INELIGIBLE, Recommendation.SKIP),
            (MatchGrade.A, EligibilityStatus.ELIGIBLE, Recommendation.BID),
            (MatchGrade.A, EligibilityStatus.NEEDS_VERIFICATION, Recommendation.HOLD),
            (MatchGrade.A, EligibilityStatus.INELIGIBLE, Recommendation.SKIP),
            (MatchGrade.B, EligibilityStatus.ELIGIBLE, Recommendation.HOLD),
            (MatchGrade.B, EligibilityStatus.NEEDS_VERIFICATION, Recommendation.HOLD),
            (MatchGrade.B, EligibilityStatus.INELIGIBLE, Recommendation.SKIP),
            (MatchGrade.C, EligibilityStatus.ELIGIBLE, Recommendation.SKIP),
            (MatchGrade.C, EligibilityStatus.NEEDS_VERIFICATION, Recommendation.SKIP),
            (MatchGrade.C, EligibilityStatus.INELIGIBLE, Recommendation.SKIP),
        ],
    )
    def test_every_cell_of_the_matrix(
        self, grade: MatchGrade, eligibility: EligibilityStatus, expected: Recommendation
    ) -> None:
        assert recommend(grade, eligibility, Urgency.NORMAL) is expected

    @pytest.mark.parametrize("grade", list(MatchGrade))
    @pytest.mark.parametrize("eligibility", list(EligibilityStatus))
    def test_an_expired_deadline_overrides_everything(
        self, grade: MatchGrade, eligibility: EligibilityStatus
    ) -> None:
        """There is nothing to recommend about a tender that cannot be bid on."""
        assert recommend(grade, eligibility, Urgency.EXPIRED) is Recommendation.SKIP

    def test_a_perfect_but_ineligible_match_is_never_a_bid(self) -> None:
        """The single most costly wrong answer: telling someone to chase a
        tender they are barred from."""
        assert (
            recommend(MatchGrade.S, EligibilityStatus.INELIGIBLE, Urgency.CRITICAL)
            is Recommendation.SKIP
        )

    def test_uncertainty_is_a_hold_not_a_rejection(self) -> None:
        """An unverifiable requirement must surface for a human, not vanish."""
        assert (
            recommend(MatchGrade.S, EligibilityStatus.NEEDS_VERIFICATION, Urgency.HIGH)
            is Recommendation.HOLD
        )


class TestFingerprint:
    def _fingerprint(self, **overrides: object) -> str:
        defaults: dict[str, object] = {
            "profile_version": 1,
            "rule_set_version_id": "rs-1",
            "extraction_id": "ex-1",
            "embedding_model": "gemini-embedding-2",
            "thresholds_version": 1,
            "tender_content_hash": "abc",
        }
        return inputs_fingerprint(**(defaults | overrides))  # type: ignore[arg-type]

    def test_identical_inputs_give_an_identical_fingerprint(self) -> None:
        assert self._fingerprint() == self._fingerprint()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("profile_version", 2),
            ("rule_set_version_id", "rs-2"),
            ("extraction_id", "ex-2"),
            ("embedding_model", "gemini-embedding-001"),
            ("thresholds_version", 2),
            ("tender_content_hash", "def"),
        ],
    )
    def test_every_input_changes_the_fingerprint(self, field: str, value: object) -> None:
        """Anything that can change a verdict must force a recompute."""
        assert self._fingerprint(**{field: value}) != self._fingerprint()

    def test_a_missing_rule_set_is_distinct_from_a_present_one(self) -> None:
        assert self._fingerprint(rule_set_version_id=None) != self._fingerprint()
