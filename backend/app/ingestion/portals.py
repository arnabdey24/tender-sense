"""The portals this product ships with, and the one place that names them.

A source row is what makes ingestion happen at all: the schedule walks
``tender_sources`` and queues one job per enabled row, so a deployment with an
empty table scrapes nothing, four times a day, forever. Until now these rows
were created only by ``scripts.seed_demo``, which also loads forty synthetic
notices — a development fixture nobody runs on a production VM. The result was
a real deployment where every user saw an empty pool and no control anywhere
would have filled it.

So the portals are deployment data, and this module is where they are defined.
Both the migration that installs them and the demo seeder read this list, which
means a change to a selector or an endpoint is made once. Adding a portal is
this list plus a migration that calls :func:`ensure_default_sources` again.

What this deliberately does not do is update a row that already exists. Config
here is a starting point; ``PATCH /admin/sources/{id}`` is how an operator
retunes a portal that changed its markup, and a redeploy silently reverting that
would take the product down at exactly the moment someone had just fixed it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tenders.models import TenderSource

#: Portals scraped on every deployment.
DEFAULT_PORTALS: list[dict[str, Any]] = [
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
        "code": "adb",
        "name": "ADB procurement notices",
        "adapter_key": "adb",
        "base_url": "https://searchcloud-2-ap-southeast-1.searchstax.com",
        "country": None,
        "schedule_cron": "0 4,16 * * *",
        "config": {
            "select_path": "/29847/tenders-11959/emselect",
            "rows": 100,
            # Active only. The index holds every notice since 2015 and would
            # otherwise bury the pool in ones that closed years ago.
            "filter": "tm_X3b_en_status:Active",
            # ADB's public read key, theirs to rotate. Held here rather than in
            # code so a portal that starts refusing us can be fixed from the
            # admin console instead of a deploy.
            "token": "2a076eb3a48fd68fc78506c1a16a5d5000da76e4",
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
]

#: The hand-entry bucket. Disabled, because there is nothing to scrape: it exists
#: so ``POST /admin/tenders`` and the JSON/CSV importer have a source to attach a
#: notice to. Registered alongside the portals so an operator adding a notice by
#: hand on a fresh deployment is not told there is nowhere to put it.
MANUAL_SOURCE: dict[str, Any] = {
    "code": "manual",
    "name": "Manually added",
    "adapter_key": "manual",
    "base_url": "",
    "country": None,
    "enabled": False,
    "config": {},
}

#: Everything a deployment should have on first boot.
DEFAULT_SOURCES: list[dict[str, Any]] = [*DEFAULT_PORTALS, MANUAL_SOURCE]


async def ensure_default_sources(
    session: AsyncSession, specs: list[dict[str, Any]] | None = None
) -> list[str]:
    """Register any shipped source the database does not already have.

    Returns the codes created, so a caller can report what it did rather than
    claiming work it skipped. Existing rows are left exactly as they are.
    """
    wanted = specs if specs is not None else DEFAULT_SOURCES
    existing = set(
        (
            await session.scalars(
                select(TenderSource.code).where(
                    TenderSource.code.in_([spec["code"] for spec in wanted])
                )
            )
        ).all()
    )
    created: list[str] = []
    for spec in wanted:
        if spec["code"] in existing:
            continue
        session.add(TenderSource(**spec))
        created.append(str(spec["code"]))
    await session.flush()
    return created
