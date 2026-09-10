"""Load authoritative context once per turn, with checkable source references."""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import PageParams
from app.modules.matching import repository as match_repo
from app.modules.matching.router import _to_read
from app.modules.matching.schemas import MatchFilters
from app.modules.profiles.service import read_profile
from app.modules.tenders.service import get_tender_detail

#: How many shortlisted notices a workspace conversation can see at once. Enough
#: to answer "what should I look at today" and to resolve "open the road one",
#: without turning every turn into a full table scan in the prompt.
WORKSPACE_MATCH_LIMIT = 25


async def _shortlist(db: AsyncSession, org_id: UUID) -> tuple[list[dict[str, Any]], int]:
    """The organization's graded shortlist, flattened for the prompt.

    Every conversation gets this, including one opened on a single notice — the
    assistant is asked to open *other* tenders ("show me the road one") far more
    often than it is asked about the one already on screen, and it can only open
    what this turn actually handed it.
    """
    rows, total = await match_repo.list_matches(
        db,
        org_id=org_id,
        filters=MatchFilters(),
        params=PageParams(page=1, page_size=WORKSPACE_MATCH_LIMIT),
    )
    matches = []
    for assessment, notice, code in rows:
        read = _to_read(assessment, notice, code).model_dump(mode="json")
        matches.append(
            {
                "tender_id": str(notice.id),
                "title": notice.title,
                "procuring_entity": notice.procuring_entity,
                "grade": read["grade"],
                "recommendation": read["recommendation"],
                "eligibility_status": read["eligibility_status"],
                "similarity": read["similarity"],
                "deadline_at": read["tender"].get("deadline_at"),
                "days_to_deadline": read["tender"].get("days_to_deadline"),
            }
        )
    return matches, total


async def load_workspace_context(db: AsyncSession, org_id: UUID) -> dict[str, Any]:
    """Context for a conversation that is not pinned to one notice.

    The assistant still answers from recorded assessments only — this is the
    same evidence as a tender conversation, widened from one notice to the
    current shortlist so it can help choose one.
    """
    profile = await read_profile(db, org_id)
    matches, total = await _shortlist(db, org_id)
    sources = [
        {
            "id": "profile",
            "label": "Company profile",
            "quote": profile.overview or "Company profile fields",
            "url": None,
        },
        {
            "id": "shortlist",
            "label": "Your graded shortlist",
            "quote": json.dumps(matches[:WORKSPACE_MATCH_LIMIT])[:16000],
            "url": None,
        },
    ]
    identity = {"profile": profile.version, "matches": [m["tender_id"] for m in matches]}
    return {
        "version": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16],
        "tender": None,
        "profile": profile.model_dump(mode="json"),
        "match": None,
        "matches": matches,
        "match_total": total,
        "sources": sources,
        "profile_changed": False,
    }


async def load_context(
    db: AsyncSession, org_id: UUID, tender_id: UUID | None
) -> dict[str, Any]:
    if tender_id is None:
        return await load_workspace_context(db, org_id)
    tender = await get_tender_detail(db, tender_id)
    profile = await read_profile(db, org_id)
    # The shortlist travels with a tender conversation too, so "open the road
    # one" can be honoured. Without it this turn knows exactly one tender id —
    # the one already on screen — and every other request fell back to it.
    matches, match_total = await _shortlist(db, org_id)
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
    sources.append(
        {
            "id": "shortlist",
            "label": "Your graded shortlist",
            "quote": json.dumps(matches)[:16000],
            "url": None,
        }
    )
    identity = {
        "tender": tender.version,
        "profile": profile.version,
        "match": match.get("fingerprint") if match else None,
        "matches": [m["tender_id"] for m in matches],
    }
    return {
        "version": hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16],
        "tender": tender.model_dump(mode="json"),
        "profile": profile.model_dump(mode="json"),
        "match": match,
        "matches": matches,
        "match_total": match_total,
        "sources": sources,
        "profile_changed": bool(match and match["profile_version"] != profile.version),
    }
