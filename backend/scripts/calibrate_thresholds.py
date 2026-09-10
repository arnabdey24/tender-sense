"""Fit the grade cut-offs to the labelled set.

Grading is pure arithmetic over similarities that are already stored, so
re-calibrating costs nothing but a `thresholds_version` bump — no AI calls, no
re-embedding. That is the whole reason thresholds live in a table.

The search is deliberately simple: try every plausible cut-off and keep the one
that separates "clearly relevant" from the rest best. With a few dozen labels
anything cleverer would be fitting noise.

Usage:
    uv run python -m scripts.calibrate_thresholds            # report only
    uv run python -m scripts.calibrate_thresholds --write    # store the result
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import UUID

from sqlalchemy import select, update

from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import dispose_engine, session_scope
from app.modules.matching.models import MatchingConfig, TenderMatch
from app.modules.tenders.models import Tender
from scripts.eval_matching import RELEVANT, load_labels

#: Cut-offs are searched on this grid. Finer than the differences the labels can
#: actually resolve would be false precision.
STEP = 0.01
LOWER, UPPER = 0.30, 0.95


def f1(scored: list[tuple[float, int]], threshold: float) -> float:
    """Balance of precision and recall at one cut-off.

    F1 rather than accuracy because the classes are lopsided: most of the pool
    is irrelevant, and a threshold that calls everything a C would score well on
    accuracy while being useless.
    """
    predicted = [(score, label) for score, label in scored if score >= threshold]
    hits = sum(1 for _, label in predicted if label >= RELEVANT)
    relevant = sum(1 for _, label in scored if label >= RELEVANT)
    if not predicted or not relevant or not hits:
        return 0.0
    precision = hits / len(predicted)
    recall = hits / relevant
    return 2 * precision * recall / (precision + recall)


def best_threshold(scored: list[tuple[float, int]]) -> tuple[float, float]:
    """The cut-off with the highest F1, and that score."""
    candidates = [LOWER + STEP * i for i in range(int((UPPER - LOWER) / STEP) + 1)]
    ranked = sorted(((f1(scored, t), t) for t in candidates), reverse=True)
    score, threshold = ranked[0]
    return round(threshold, 2), round(score, 3)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", help="Organization id; defaults to the first with matches")
    parser.add_argument("--write", action="store_true", help="Store the fitted thresholds")
    args = parser.parse_args()

    configure_logging()
    labels = load_labels()

    async with session_scope() as session:
        org_id = (
            UUID(args.org)
            if args.org
            else await session.scalar(select(TenderMatch.org_id).limit(1))
        )
        if org_id is None:
            raise SystemExit("No matches found. Run the pipeline first.")

        rows = (
            await session.execute(
                select(TenderMatch.similarity, Tender.external_id)
                .join(Tender, Tender.id == TenderMatch.tender_id)
                .where(TenderMatch.org_id == org_id)
            )
        ).all()

    scored = [
        (float(similarity), labels[external_id])
        for similarity, external_id in rows
        if external_id in labels
    ]
    if len(scored) < 10:
        raise SystemExit(f"Only {len(scored)} labelled matches; too few to calibrate against.")

    s_threshold, s_f1 = best_threshold(scored)
    # A and B sit below S on the same curve; fit them against the looser
    # "arguable or better" bar so the bands stay ordered.
    arguable = [(score, 2 if label >= 1 else 0) for score, label in scored]
    a_threshold, a_f1 = best_threshold(arguable)
    b_threshold = round(max(LOWER, a_threshold - 0.08), 2)

    print(f"\norganization: {org_id}")
    print(f"labelled matches: {len(scored)}\n")
    print(f"  S >= {s_threshold:.2f}   (F1 {s_f1:.3f} against 'clearly relevant')")
    print(f"  A >= {a_threshold:.2f}   (F1 {a_f1:.3f} against 'arguable or better')")
    print(f"  B >= {b_threshold:.2f}   (one band below A)")
    print("\nThese fit a small, synthetic, self-labelled set. Treat them as a")
    print("starting point and refit once real bid/skip decisions accumulate.\n")

    if not args.write:
        print("Run again with --write to store them.\n")
        await dispose_engine()
        return

    if not (b_threshold < a_threshold < s_threshold):
        raise SystemExit("Fitted thresholds are not ordered; refusing to store them.")

    async with session_scope() as session:
        current = await session.scalar(
            select(MatchingConfig)
            .where(MatchingConfig.is_active.is_(True))
            .order_by(MatchingConfig.created_at.desc())
            .limit(1)
        )
        version = (current.thresholds_version + 1) if current else 1
        # Deactivate rather than update: the old row is what previous matches
        # were graded against, and their `thresholds_version` points at it.
        await session.execute(
            update(MatchingConfig).where(MatchingConfig.is_active.is_(True)).values(is_active=False)
        )
        session.add(
            MatchingConfig(
                is_active=True,
                thresholds_version=version,
                grade_s_threshold=s_threshold,
                grade_a_threshold=a_threshold,
                grade_b_threshold=b_threshold,
                notes=f"Fitted on {len(scored)} labelled matches.",
            )
        )

    print(f"stored as thresholds_version {version}.")
    print("Re-grading needs no AI calls — run rematch_org to apply.\n")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
