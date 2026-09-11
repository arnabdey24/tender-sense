"""Load the synthetic dataset into the database.

Idempotent: run it as often as you like. It registers the portals, imports the
notices through the same path the scrapers use, and reports what changed.

Usage: ``uv run python -m scripts.seed_demo`` (or ``make seed``)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, session_scope
from app.ingestion.importer import import_tenders
from app.ingestion.portals import ensure_default_sources
from app.modules.tenders.models import TenderSource

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_FILE = DATA_DIR / "seed" / "tenders.json"


async def ensure_sources() -> dict[str, TenderSource]:
    """Create the portals, leaving any existing configuration untouched.

    Migration ``0012_default_sources`` already does this on every deployment, so
    on a migrated database this finds nothing to do. It stays because a test
    database built from ``Base.metadata`` never ran a migration, and because
    saying so out loud is cheaper than a seeder that assumes.
    """
    async with session_scope() as session:
        created = await ensure_default_sources(session)

    async with session_scope() as session:
        rows = (await session.execute(select(TenderSource))).scalars().all()

    if created:
        print(f"registered sources: {', '.join(created)}")
    return {row.code: row for row in rows}


async def seed_tenders() -> None:
    if not SEED_FILE.exists():
        raise SystemExit(
            f"{SEED_FILE} is missing. Generate it with:\n  uv run python -m scripts.gen_synthetic"
        )

    rows = json.loads(SEED_FILE.read_text())
    async with session_scope() as session:
        report = await import_tenders(session, rows)

    print(
        f"tenders: {report.created} created, {report.updated} updated, "
        f"{report.unchanged} unchanged, {report.failed} failed"
    )
    for error in report.errors[:5]:
        print(f"  row {error['row']}: {error['error']}")


async def main() -> None:
    configure_logging()
    await ensure_sources()
    await seed_tenders()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
