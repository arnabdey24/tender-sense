"""Showing what a draft rule set would do before it is saved.

The point is to make an over-broad rule visible *before* it silently hides half
the pool. Per-rule counts matter more than the totals: "42 tenders became
ineligible" is alarming but useless, while "the certification rule rejected 42"
tells the customer exactly which line to relax.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.modules.matching.models import EligibilityStatus
from app.modules.profiles.models import CompanyProfile
from app.modules.rules.engine import evaluate
from app.modules.rules.facts import profile_facts, tender_facts
from app.modules.rules.schemas import (
    PreviewCounts,
    PreviewSample,
    RulePreview,
    RuleSetDefinition,
    RuleTestResult,
)
from app.modules.rules.service import BASE_CURRENCY, fx_rates, profile_children
from app.modules.tenders.models import Tender, TenderExtraction, TenderStatus

#: Hard ceiling on a preview. Beyond this the numbers stop changing but the
#: request keeps getting slower, and a customer is waiting on it.
MAX_PREVIEW_TENDERS = 2000

CLOSED_STATUSES = (TenderStatus.CLOSED, TenderStatus.CANCELLED, TenderStatus.AWARDED)


async def _load_pool(
    session: AsyncSession, limit: int
) -> list[tuple[Tender, dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """Open tenders with their current extraction, newest first."""
    now = utcnow()
    rows = await session.execute(
        select(Tender, TenderExtraction)
        .outerjoin(
            TenderExtraction,
            (TenderExtraction.tender_id == Tender.id) & (TenderExtraction.is_current.is_(True)),
        )
        .where(
            Tender.status.not_in(CLOSED_STATUSES),
            (Tender.deadline_at.is_(None)) | (Tender.deadline_at > now),
        )
        .order_by(Tender.published_at.desc().nulls_last())
        .limit(min(limit, MAX_PREVIEW_TENDERS))
    )
    pool: list[tuple[Tender, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for tender, extraction in rows.all():
        pool.append(
            (
                tender,
                extraction.attributes if extraction else {},
                extraction.field_confidence if extraction else {},
                extraction.evidence if extraction else {},
            )
        )
    return pool


async def preview(
    session: AsyncSession,
    *,
    definition: RuleSetDefinition,
    profile: CompanyProfile,
    limit: int = MAX_PREVIEW_TENDERS,
    sample_size: int = 10,
) -> RulePreview:
    """Run a draft over the open pool without storing anything."""
    certifications, projects = await profile_children(session, profile.id)
    facts = profile_facts(profile, certifications=certifications, projects=projects)
    rates = await fx_rates(session)
    pool = await _load_pool(session, limit)

    counts = PreviewCounts()
    per_rule: dict[str, PreviewCounts] = {
        rule.id: PreviewCounts() for rule in definition.active_rules
    }
    samples: list[PreviewSample] = []

    for tender, attributes, confidence, evidence in pool:
        evaluation = evaluate(
            definition,
            tender=tender_facts(
                tender, attributes=attributes, confidence=confidence, evidence=evidence
            ),
            profile=facts,
            fx=rates,
            base_currency=BASE_CURRENCY,
        )

        counts.evaluated += 1
        status = evaluation.status
        if status is EligibilityStatus.ELIGIBLE:
            counts.eligible += 1
        elif status is EligibilityStatus.NEEDS_VERIFICATION:
            counts.needs_verification += 1
        else:
            counts.ineligible += 1

        for result in evaluation.results:
            bucket = per_rule.get(result.rule_id)
            if bucket is None:
                continue
            bucket.evaluated += 1
            if result.status == "pass":
                bucket.eligible += 1
            elif result.status == "fail":
                bucket.ineligible += 1
            else:
                bucket.needs_verification += 1

        # Sample the tenders a customer would want to argue with: the ones the
        # draft would exclude or flag, not the ones it lets through.
        if status is not EligibilityStatus.ELIGIBLE and len(samples) < sample_size:
            samples.append(
                PreviewSample(
                    tender_id=tender.id,
                    title=tender.title,
                    status=status.value,
                    failing_rules=[r.label for r in evaluation.failing],
                    unknown_rules=[r.label for r in evaluation.unresolved],
                )
            )

    return RulePreview(counts=counts, per_rule=per_rule, samples=samples)


async def test_against_tender(
    session: AsyncSession,
    *,
    definition: RuleSetDefinition,
    profile: CompanyProfile,
    tender_id: UUID,
) -> RuleTestResult | None:
    """Evaluate a draft against one named tender, for "why did this fail?"."""
    tender = await session.get(Tender, tender_id)
    if tender is None:
        return None

    extraction = await session.scalar(
        select(TenderExtraction).where(
            TenderExtraction.tender_id == tender_id, TenderExtraction.is_current.is_(True)
        )
    )
    certifications, projects = await profile_children(session, profile.id)

    evaluation = evaluate(
        definition,
        tender=tender_facts(
            tender,
            attributes=extraction.attributes if extraction else {},
            confidence=extraction.field_confidence if extraction else {},
            evidence=extraction.evidence if extraction else {},
        ),
        profile=profile_facts(profile, certifications=certifications, projects=projects),
        fx=await fx_rates(session),
        base_currency=BASE_CURRENCY,
    )
    return RuleTestResult(
        tender_id=tender.id,
        title=tender.title,
        eligibility_status=evaluation.status.value,
        results=evaluation.results,
    )
