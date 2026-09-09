"""Load the synthetic dataset into the database.

Idempotent: run it as often as you like. It registers the portals, imports the
notices through the same path the scrapers use, and reports what changed.

Usage: ``uv run python -m scripts.seed_demo`` (or ``make seed``)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, session_scope
from app.ingestion.importer import import_tenders
from app.modules.tenders.models import TenderSource

logger = get_logger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_FILE = DATA_DIR / "seed" / "tenders.json"

SOURCES: list[dict[str, Any]] = [
    {
        "code": "egp_bd",
        "name": "e-GP Bangladesh",
        "adapter_key": "egp_bd",
        "base_url": "https://www.eprocure.gov.bd",
        "country": "BD",
        # Four passes a day, off-peak in Dhaka, to stay polite to an old portal.
        "schedule_cron": "0 2,8,14,20 * * *",
        "config": {
            "listing_endpoint": "/TenderDetailsServlet",
            "detail_path": "/resources/common/ViewTender.jsp",
            "page_size": 100,
            "max_pages": 20,
        },
    },
    {
        "code": "wb",
        "name": "World Bank procurement notices",
        "adapter_key": "worldbank",
        "base_url": "https://search.worldbank.org",
        "country": None,
        "schedule_cron": "30 3,15 * * *",
        "config": {
            "endpoint": "/api/v2/procnotices",
            "rows": 100,
            # The endpoint intermittently returns 500 when `fl` is omitted.
            "fields": [
                "id",
                "notice_type",
                "noticedate",
                "submission_deadline_date",
                "project_id",
                "project_name",
                "project_ctry_name",
                "procurement_method_name",
                "bid_reference_no",
                "bid_description",
                "notice_text",
            ],
        },
    },
    {
        "code": "manual",
        "name": "Manually added",
        "adapter_key": "manual",
        "base_url": "",
        "country": None,
        "enabled": False,
        "config": {},
    },
]


async def ensure_sources() -> dict[str, TenderSource]:
    """Create the portals, leaving any existing configuration untouched."""
    created: list[str] = []
    async with session_scope() as session:
        for spec in SOURCES:
            existing = await session.scalar(
                select(TenderSource).where(TenderSource.code == spec["code"])
            )
            if existing is None:
                session.add(TenderSource(**spec))
                created.append(str(spec["code"]))
        await session.flush()

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
