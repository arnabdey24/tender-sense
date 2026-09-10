"""Writing the model-authored explanation for matches that earn one.

Runs after matching rather than inside it, for two reasons: a match must exist
and be readable even if the model is unavailable, and explanations are the one
part of the pipeline worth rationing. Every match already carries a templated
explanation, so this only ever upgrades the prose.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import get_ai_client
from app.ai.base import AIClient, AIError
from app.ai.explanation import should_use_llm
from app.ai.prompts.explanation import SYSTEM_INSTRUCTION, build_prompt
from app.ai.schemas import MatchExplanation
from app.core.logging import get_logger
from app.db.session import session_scope
from app.modules.matching.ai_usage import record, within_budget
from app.modules.matching.models import ExplanationKind, TenderMatch
from app.modules.profiles.models import CompanyProfile
from app.modules.tenders.models import Tender

logger = get_logger(__name__)

#: Rough ceiling for one explanation, used to leave headroom in the budget
#: check rather than discovering mid-call that there was none.
ESTIMATED_TOKENS_PER_EXPLANATION = 1200


def _client(ctx: dict[str, Any]) -> AIClient:
    client: AIClient | None = ctx.get("ai_client")
    return client or get_ai_client()


async def _write_one(session: AsyncSession, match: TenderMatch, *, client: AIClient) -> bool:
    """Generate and store one explanation. Returns whether it was written."""
    tender = await session.get(Tender, match.tender_id)
    profile = await session.scalar(
        select(CompanyProfile).where(CompanyProfile.org_id == match.org_id)
    )
    if tender is None or profile is None:
        return False

    breakdown = match.score_breakdown or {}
    prompt = build_prompt(
        title=tender.title,
        procuring_entity=tender.procuring_entity,
        deadline=tender.deadline_at.date().isoformat() if tender.deadline_at else None,
        grade=match.grade.value,
        similarity=match.similarity,
        eligibility=match.eligibility_status.value,
        recommendation=match.recommendation.value,
        matched_facets=list(breakdown.get("top_facets") or []),
        rule_results=[dict(result) for result in (match.rule_results or [])],
        profile_overview=profile.overview,
    )

    try:
        result = await client.generate_structured(
            prompt=prompt,
            schema=MatchExplanation,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.3,
        )
    except AIError as exc:
        # The templated explanation is already on the row, so a failure here
        # costs prose quality and nothing else.
        logger.warning("explanation_failed", match_id=str(match.id), error=str(exc))
        return False

    explanation = result.parsed
    match.explanation = explanation.model_dump(mode="json")
    match.explanation_text = _to_text(explanation)
    match.explanation_kind = ExplanationKind.LLM
    await record(session, result.usage, purpose="explanation", org_id=match.org_id)
    await session.flush()
    return True


def _to_text(explanation: MatchExplanation) -> str:
    lines = [explanation.summary]
    for heading, items in (
        ("Why it matches", explanation.why_matched),
        ("Gaps", explanation.gaps),
        ("Worth checking", explanation.risks),
    ):
        if items:
            lines.append(f"\n{heading}:")
            lines.extend(f"- {item}" for item in items)
    if explanation.next_step:
        lines.append(f"\nNext: {explanation.next_step}")
    return "\n".join(lines).strip()


async def generate_explanations(
    ctx: dict[str, Any], tender_id: str, limit: int = 50
) -> dict[str, Any]:
    """Upgrade the explanations for one tender's matches, where worth it."""
    client = _client(ctx)
    result: dict[str, Any] = {
        "tender_id": tender_id,
        "written": 0,
        "skipped": 0,
        "over_budget": 0,
    }

    async with session_scope() as session:
        matches = list(
            (
                await session.scalars(
                    select(TenderMatch)
                    .where(TenderMatch.tender_id == UUID(tender_id))
                    .order_by(TenderMatch.similarity.desc())
                    .limit(limit)
                )
            ).all()
        )
        candidates = [
            match
            for match in matches
            if should_use_llm(match.grade, match.eligibility_status, match.urgency)
            # Regenerating identical prose for an unchanged verdict is pure
            # spend, so only a templated explanation is upgraded here.
            and match.explanation_kind is ExplanationKind.TEMPLATED
        ]
        result["skipped"] = len(matches) - len(candidates)

        for match in candidates:
            if not await within_budget(session, headroom=ESTIMATED_TOKENS_PER_EXPLANATION):
                result["over_budget"] += 1
                continue
            if await _write_one(session, match, client=client):
                result["written"] += 1

    if result["over_budget"]:
        logger.warning("explanation_budget_exhausted", **result)
    logger.info("explanations_generated", **result)
    return result
