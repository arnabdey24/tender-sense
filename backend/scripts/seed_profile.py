"""Give an organization the sample capability profile and score the pool.

Turns a fresh sign-up into the demo the milestone promises: a company that can
see a graded feed. Idempotent — re-running replaces the profile's children
rather than duplicating them.

Usage:
    uv run python -m scripts.seed_profile                 # first org without a profile
    uv run python -m scripts.seed_profile --org <uuid>
    uv run python -m scripts.seed_profile --provider fake # skip the real API
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select

from app.ai import build_client, set_ai_client
from app.ai.fake_client import FakeAIClient
from app.core.config import settings
from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401  - configures the ORM registry
from app.db.session import dispose_engine, session_scope
from app.jobs.tasks.matching import process_tender, rematch_org
from app.modules.orgs.models import Organization
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfilePastProject,
    ProfileService,
)
from app.modules.profiles.schemas import canonical_certification
from app.modules.tenders.models import Tender

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPANY_FILE = DATA_DIR / "seed" / "sample_company.json"

#: The sample file predates the sector vocabulary the matcher understands.
SECTOR_ALIASES = {
    "information_technology": "it",
    "public_administration": "other",
    "health": "healthcare",
    "education": "education",
}


async def pick_org(org_id: str | None) -> Organization:
    async with session_scope() as session:
        if org_id:
            org = await session.get(Organization, UUID(org_id))
            if org is None:
                raise SystemExit(f"No organization {org_id}")
        else:
            org = await session.scalar(
                select(Organization)
                .outerjoin(CompanyProfile, CompanyProfile.org_id == Organization.id)
                .where(CompanyProfile.id.is_(None), Organization.is_active.is_(True))
                .order_by(Organization.created_at.desc())
                .limit(1)
            )
            if org is None:
                raise SystemExit(
                    "Every organization already has a profile. Pass --org to overwrite one."
                )
        await session.refresh(org)
        return org


async def apply_profile(org: Organization, company: dict[str, Any]) -> CompanyProfile:
    async with session_scope() as session:
        profile = await session.scalar(
            select(CompanyProfile).where(CompanyProfile.org_id == org.id)
        )
        if profile is None:
            profile = CompanyProfile(org_id=org.id)
            session.add(profile)
            await session.flush()

        turnover = company.get("annual_turnover") or {}
        profile.overview = company.get("description")
        profile.sectors = [
            SECTOR_ALIASES.get(sector, sector) for sector in company.get("sectors", [])
        ]
        profile.geographies = company.get("geographies", [])
        profile.annual_turnover = turnover.get("amount")
        profile.turnover_currency = turnover.get("currency")
        profile.turnover_year = turnover.get("year")
        profile.version += 1

        # Replace rather than append, so re-running does not duplicate.
        for model in (ProfileService, ProfilePastProject, ProfileCertification):
            await session.execute(delete(model).where(model.profile_id == profile.id))

        for index, service in enumerate(company.get("services", [])):
            session.add(
                ProfileService(
                    profile_id=profile.id,
                    name=service["name"],
                    description=service.get("description"),
                    position=index,
                )
            )
        for project in company.get("past_projects", []):
            session.add(
                ProfilePastProject(
                    profile_id=profile.id,
                    title=project.get("title") or project.get("name", "Project"),
                    client=project.get("client"),
                    description=project.get("description"),
                    country=project.get("country"),
                )
            )
        for certification in company.get("certifications", []):
            label = certification.get("name") or certification.get("code", "")
            session.add(
                ProfileCertification(
                    profile_id=profile.id,
                    code=canonical_certification(label),
                    label=label,
                    issuer=certification.get("issuer"),
                )
            )
        await session.flush()
        await session.refresh(profile)
        return profile


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", help="Organization id; defaults to the newest without a profile")
    parser.add_argument(
        "--provider",
        choices=["gemini", "fake"],
        help="Override AI_PROVIDER for this run",
    )
    args = parser.parse_args()

    configure_logging()
    if args.provider == "fake":
        set_ai_client(FakeAIClient(dims=settings.embedding_dims))
    client = (
        build_client() if args.provider != "fake" else FakeAIClient(dims=settings.embedding_dims)
    )
    ctx = {"ai_client": client}

    if not COMPANY_FILE.exists():
        raise SystemExit(f"{COMPANY_FILE} is missing.")
    company = json.loads(COMPANY_FILE.read_text())

    org = await pick_org(args.org)
    profile = await apply_profile(org, company)
    print(f"profile: {org.name} ({org.id}) v{profile.version}")

    async with session_scope() as session:
        tender_ids = list((await session.scalars(select(Tender.id))).all())

    print(f"processing {len(tender_ids)} tenders with {client.embedding_model}…")
    for index, tender_id in enumerate(tender_ids, start=1):
        result = await process_tender(ctx, str(tender_id))
        print(
            f"  [{index}/{len(tender_ids)}] {result.get('extraction', '-')} "
            f"matched={result['matched']} skipped={result['skipped']}"
        )

    summary = await rematch_org(ctx, str(org.id), reason="seed")
    print(f"rematch: matched={summary['matched']} skipped={summary['skipped']}")
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
