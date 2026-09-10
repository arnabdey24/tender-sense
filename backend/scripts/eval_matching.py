"""Does semantic matching actually beat keyword search?

Runs both over the labelled set and prints precision@5, recall@10 and nDCG@10
side by side. The keyword baseline is deliberately a fair one — the company's
own profile terms against the notice text — because beating a straw man proves
nothing, and if semantic matching cannot beat a decent keyword search the
product does not have a reason to exist.

Usage:
    uv run python -m scripts.eval_matching                # whichever org has a profile
    uv run python -m scripts.eval_matching --org <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import math
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.logging import configure_logging
from app.core.text import comparison_key
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import dispose_engine, session_scope
from app.modules.matching.models import TenderMatch
from app.modules.profiles.models import CompanyProfile, ProfileService
from app.modules.tenders.models import Tender

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LABELS_FILE = DATA_DIR / "eval" / "labels.csv"

#: A label of 2 is "clearly relevant", 1 is "arguable", 0 is "not for us".
#: Only a 2 counts as a hit for precision and recall; nDCG uses the full scale,
#: because ranking an arguable tender above an irrelevant one is worth credit.
RELEVANT = 2


def load_labels() -> dict[str, int]:
    if not LABELS_FILE.exists():
        raise SystemExit(f"{LABELS_FILE} is missing.")
    labels: dict[str, int] = {}
    with LABELS_FILE.open() as handle:
        for row in csv.DictReader(handle):
            external_id = (row.get("external_id") or row.get("tender_id") or "").strip()
            raw = (row.get("relevance") or row.get("label") or "0").strip()
            if external_id:
                labels[external_id] = int(raw or 0)
    return labels


def precision_at_k(ranked: list[int], k: int) -> float:
    top = ranked[:k]
    if not top:
        return 0.0
    return sum(1 for score in top if score >= RELEVANT) / len(top)


def recall_at_k(ranked: list[int], k: int, total_relevant: int) -> float:
    if total_relevant == 0:
        return 0.0
    return sum(1 for score in ranked[:k] if score >= RELEVANT) / total_relevant


def ndcg_at_k(ranked: list[int], k: int) -> float:
    """Graded relevance, discounted by position.

    Rewards putting the best tender first rather than merely somewhere in the
    top ten — which is what a daily shortlist actually needs.
    """

    def dcg(scores: list[int]) -> float:
        total = 0.0
        for index, score in enumerate(scores[:k]):
            total += (2**score - 1) / math.log2(index + 2)
        return total

    ideal = dcg(sorted(ranked, reverse=True))
    return dcg(ranked) / ideal if ideal else 0.0


def keyword_score(profile_terms: set[str], tender: Tender) -> float:
    """A fair baseline: how many profile terms appear in the notice.

    Normalised by the number of terms so a longer profile does not
    automatically win, and folded through the same comparison key the rule
    engine uses so punctuation does not decide the outcome.
    """
    if not profile_terms:
        return 0.0
    haystack = " ".join(
        part for part in (tender.title, tender.summary, tender.description) if part
    ).lower()
    hits = sum(1 for term in profile_terms if term and term.lower() in haystack)
    return hits / len(profile_terms)


async def profile_terms(profile: CompanyProfile) -> set[str]:
    terms: set[str] = set()
    terms.update(profile.keywords or [])
    terms.update(profile.sectors or [])
    async with session_scope() as session:
        services = await session.scalars(
            select(ProfileService).where(ProfileService.profile_id == profile.id)
        )
        for service in services.all():
            terms.update(word for word in service.name.split() if len(word) > 3)
    return {term for term in terms if len(comparison_key(term)) > 2}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", help="Organization id; defaults to the first with matches")
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    configure_logging()
    labels = load_labels()

    async with session_scope() as session:
        if args.org:
            org_id: UUID | None = UUID(args.org)
        else:
            org_id = await session.scalar(select(TenderMatch.org_id).limit(1))
        if org_id is None:
            raise SystemExit("No matches found. Run the pipeline first.")

        profile = await session.scalar(
            select(CompanyProfile).where(CompanyProfile.org_id == org_id)
        )
        if profile is None:
            raise SystemExit(f"Organization {org_id} has no profile.")

        rows = (
            await session.execute(
                select(TenderMatch, Tender)
                .join(Tender, Tender.id == TenderMatch.tender_id)
                .where(TenderMatch.org_id == org_id)
            )
        ).all()

    if not rows:
        raise SystemExit("No matches for that organization.")

    terms = await profile_terms(profile)

    scored: dict[str, list[tuple[float, int]]] = defaultdict(list)
    labelled = 0
    for match, tender in rows:
        label = labels.get(tender.external_id)
        if label is None:
            continue
        labelled += 1
        scored["semantic"].append((match.similarity, label))
        scored["keyword"].append((keyword_score(terms, tender), label))

    if not labelled:
        raise SystemExit("No matched tenders appear in the label file; nothing to evaluate.")

    total_relevant = sum(1 for _, label in scored["semantic"] if label >= RELEVANT)

    print(f"\norganization: {org_id}")
    print(f"labelled tenders matched: {labelled}   clearly relevant: {total_relevant}\n")
    print(f"{'strategy':<12}{'P@5':>8}{'R@' + str(args.k):>8}{'nDCG@' + str(args.k):>10}")
    print("-" * 38)

    for strategy in ("keyword", "semantic"):
        ranked = [
            label for _, label in sorted(scored[strategy], key=lambda pair: pair[0], reverse=True)
        ]
        print(
            f"{strategy:<12}"
            f"{precision_at_k(ranked, 5):>8.2f}"
            f"{recall_at_k(ranked, args.k, total_relevant):>8.2f}"
            f"{ndcg_at_k(ranked, args.k):>10.3f}"
        )
    print()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
