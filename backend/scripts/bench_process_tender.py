"""How long does one notice take to go from scraped to scored, per tenant?

The target in the plan is under 60 seconds for one tender across every
organization, because that is the difference between "a notice appears in your
feed while you are still reading the portal" and "some time tomorrow". This
measures the real pipeline — extraction, embedding, scoring, rules,
explanations — rather than a mock of it.

Run it with ``AI_PROVIDER=fake`` to measure everything the code controls, and
with a real key to see what the model adds. Both numbers matter: the first is
the one a regression would show up in, the second is the one a customer feels.

Usage:
    uv run python -m scripts.bench_process_tender --tenders 5
    AI_PROVIDER=fake uv run python -m scripts.bench_process_tender --repeat 3
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.time import utcnow
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import dispose_engine, session_scope
from app.ingestion.adapters.base import TenderIn
from app.ingestion.service import upsert_tender
from app.jobs.tasks.matching import process_tender
from app.modules.matching.models import TenderMatch
from app.modules.orgs.models import Organization
from app.modules.profiles.models import CompanyProfile
from app.modules.tenders.models import Tender, TenderSource

#: The plan's budget. Printed alongside the measurement so the number has a
#: verdict attached rather than being left for the reader to judge.
BUDGET_SECONDS = 60.0

SOURCE_CODE = "bench"


async def _tenant_count() -> int:
    async with session_scope() as session:
        total = await session.scalar(
            select(func.count())
            .select_from(Organization)
            .join(CompanyProfile, CompanyProfile.org_id == Organization.id)
            .where(Organization.is_active.is_(True))
        )
    return int(total or 0)


async def _bench_source() -> UUID:
    async with session_scope() as session:
        source = await session.scalar(select(TenderSource).where(TenderSource.code == SOURCE_CODE))
        if source is None:
            source = TenderSource(
                code=SOURCE_CODE,
                name="Benchmark",
                adapter_key="manual",
                base_url="",
                enabled=False,
            )
            session.add(source)
            await session.flush()
        return source.id


async def _make_tender(source_id: UUID, index: int) -> UUID:
    """A notice with enough real text that extraction and embedding do work.

    Benchmarking a two-word title would measure the framework, not the product.
    """
    async with session_scope() as session:
        source = await session.get(TenderSource, source_id)
        assert source is not None
        result = await upsert_tender(
            session,
            source=source,
            data=TenderIn(
                external_id=f"bench-{uuid4().hex}",
                canonical_url=f"https://bench.invalid/{index}",
                title="Supply, installation and commissioning of core network switches",
                summary="Datacentre network refresh for a government ministry.",
                description=(
                    "The Procuring Entity invites sealed tenders for the supply, "
                    "installation, testing and commissioning of core and distribution "
                    "layer network switches, structured cabling, and three years of "
                    "on-site maintenance. Bidders must demonstrate an average annual "
                    "turnover of at least USD 2,000,000 over the last three financial "
                    "years, ISO 9001 certification, and at least two similar contracts "
                    "completed in the last five years. Joint ventures are permitted. "
                    "Bid security of USD 25,000 is required."
                ),
                procuring_entity="Ministry of Information and Communication Technology",
                country="BD",
                procurement_method="Open Tendering Method",
                deadline_at=utcnow().replace(microsecond=0),
            ),
        )
        return result.tender_id


async def _cleanup(tender_ids: list[UUID]) -> None:
    async with session_scope() as session:
        await session.execute(delete(TenderMatch).where(TenderMatch.tender_id.in_(tender_ids)))
        await session.execute(delete(Tender).where(Tender.id.in_(tender_ids)))


def _verdict(worst: float, tenants: int) -> str:
    if worst <= BUDGET_SECONDS:
        return f"PASS — worst tender took {worst:.2f}s against a {BUDGET_SECONDS:.0f}s budget"
    return (
        f"FAIL — worst tender took {worst:.2f}s, over the {BUDGET_SECONDS:.0f}s budget "
        f"across {tenants} tenant(s)"
    )


async def main(count: int, repeat: int) -> int:
    configure_logging()
    tenants = await _tenant_count()
    if tenants == 0:
        print("No organization has a capability profile; seed one first (make seed).")
        return 1

    source_id = await _bench_source()
    print(f"provider={settings.ai_provider}  tenants={tenants}  tenders={count}  repeat={repeat}")

    timings: list[float] = []
    created: list[UUID] = []
    stats: dict[str, Any] = {}
    try:
        for round_index in range(repeat):
            for index in range(count):
                tender_id = await _make_tender(source_id, index)
                created.append(tender_id)
                started = time.perf_counter()
                stats = await process_tender({}, str(tender_id))
                elapsed = time.perf_counter() - started
                timings.append(elapsed)
                print(
                    f"  round {round_index + 1} tender {index + 1}: {elapsed:6.2f}s  "
                    f"matched={stats.get('matched')} skipped={stats.get('skipped')}"
                )
    finally:
        await _cleanup(created)
        await dispose_engine()

    worst = max(timings)
    print()
    print(f"median {statistics.median(timings):.2f}s   mean {statistics.fmean(timings):.2f}s")
    print(f"worst  {worst:.2f}s   per tenant {worst / max(tenants, 1):.2f}s")
    print(_verdict(worst, tenants))
    return 0 if worst <= BUDGET_SECONDS else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenders", type=int, default=3, help="Notices per round")
    parser.add_argument("--repeat", type=int, default=1, help="Rounds to run")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.tenders, args.repeat)))
