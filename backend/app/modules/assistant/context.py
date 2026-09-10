"""Load authoritative context once per turn, with checkable source references."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.matching import repository as match_repo
from app.modules.matching.router import _to_read
from app.modules.profiles.service import read_profile
from app.modules.tenders.service import get_tender_detail


async def load_context(db: AsyncSession, org_id: UUID, tender_id: UUID) -> dict[str, Any]:
    tender = await get_tender_detail(db, tender_id)
    profile = await read_profile(db, org_id)
    row = await match_repo.get_match(db, org_id=org_id, tender_id=tender_id)
    match: dict[str, Any] | None = None
    if row:
        assessment, notice, code = row
        match = _to_read(assessment, notice, code).model_dump(mode="json")
        match["profile_version"] = assessment.profile_version
        match["thresholds_version"] = assessment.thresholds_version
        match["fingerprint"] = assessment.inputs_fingerprint
    sources = [
        {
            "id": "tender",
            "label": "Tender notice",
            "quote": (tender.description or tender.summary or tender.title)[:16000],
            "url": tender.canonical_url,
        },
        {
            "id": "profile",
            "label": "Company profile",
            "quote": profile.overview or "Company profile fields",
            "url": None,
        },
    ]
    if match:
        sources.append(
            {
                "id": "assessment",
                "label": "Recorded assessment",
                "quote": match.get("explanation_text") or str(match["explanation"]),
                "url": None,
            }
        )
        for rule in match["rule_results"]:
            sources.append(
                {
                    "id": f"rule:{rule['rule_id']}",
                    "label": rule["label"],
                    "quote": rule.get("evidence") or rule["reason"],
                    "url": tender.canonical_url if rule.get("evidence") else None,
                }
            )
    identity = {
        "tender": tender.version,
        "profile": profile.version,
        "match": match.get("fingerprint") if match else None,
    }
    return {
        "version": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16],
        "tender": tender.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "match": match,
        "sources": sources,
        "profile_changed": bool(match and match["profile_version"] != profile.version),
    }
