"""Ranking metrics and threshold fitting.

Pure arithmetic, but arithmetic that decides whether we can claim semantic
matching beats keyword search — so it is worth being sure of.
"""

from __future__ import annotations

import pytest

from scripts.calibrate_thresholds import best_threshold, f1
from scripts.eval_matching import ndcg_at_k, precision_at_k, recall_at_k


class TestPrecision:
    def test_a_perfect_top_five(self) -> None:
        assert precision_at_k([2, 2, 2, 2, 2, 0, 0], 5) == 1.0

    def test_half_the_top_five(self) -> None:
        assert precision_at_k([2, 0, 2, 0, 2, 0], 5) == pytest.approx(0.6)

    def test_an_arguable_label_is_not_a_hit(self) -> None:
        """Only "clearly relevant" counts; otherwise the number flatters us."""
        assert precision_at_k([1, 1, 1, 1, 1], 5) == 0.0

    def test_an_empty_ranking_scores_zero_rather_than_dividing_by_zero(self) -> None:
        assert precision_at_k([], 5) == 0.0


class TestRecall:
    def test_finding_everything(self) -> None:
        assert recall_at_k([2, 2, 0, 0], 10, total_relevant=2) == 1.0

    def test_finding_half(self) -> None:
        assert recall_at_k([2, 0, 0, 0], 10, total_relevant=2) == pytest.approx(0.5)

    def test_nothing_relevant_exists(self) -> None:
        assert recall_at_k([0, 0], 10, total_relevant=0) == 0.0

    def test_a_relevant_item_outside_k_does_not_count(self) -> None:
        assert recall_at_k([0, 0, 0, 2], 3, total_relevant=1) == 0.0


class TestNdcg:
    def test_a_perfect_ranking_scores_one(self) -> None:
        assert ndcg_at_k([2, 2, 1, 0], 10) == pytest.approx(1.0)

    def test_order_matters_not_just_membership(self) -> None:
        """The whole point: a shortlist has to put the best one first."""
        good = ndcg_at_k([2, 1, 0], 10)
        bad = ndcg_at_k([0, 1, 2], 10)

        assert good > bad

    def test_a_ranking_with_nothing_relevant_scores_zero(self) -> None:
        assert ndcg_at_k([0, 0, 0], 10) == 0.0

    def test_graded_relevance_is_used(self) -> None:
        """Ranking an arguable item above an irrelevant one earns credit."""
        assert ndcg_at_k([1, 0], 10) > 0.0


class TestThresholdFitting:
    def test_it_finds_a_clean_separation(self) -> None:
        scored = [(0.9, 2), (0.85, 2), (0.4, 0), (0.3, 0)]

        threshold, score = best_threshold(scored)

        assert score == pytest.approx(1.0)
        assert 0.4 < threshold <= 0.85

    def test_f1_punishes_a_threshold_that_accepts_everything(self) -> None:
        """Accuracy would reward calling the whole pool relevant; F1 does not."""
        scored = [(0.9, 2)] + [(0.5, 0)] * 20

        assert f1(scored, 0.3) < f1(scored, 0.8)

    def test_f1_is_zero_when_nothing_is_predicted(self) -> None:
        assert f1([(0.5, 2)], 0.9) == 0.0

    def test_f1_is_zero_when_nothing_is_relevant(self) -> None:
        assert f1([(0.9, 0)], 0.5) == 0.0
