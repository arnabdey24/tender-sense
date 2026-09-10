"""Loading rule sets and evaluating them against stored rows.

The seam between the pure engine and the database. Everything that needs an
eligibility verdict — the matcher, the preview endpoint, the per-tender test —
comes through here, so they cannot drift into evaluating things differently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.modules.matching.models import EligibilityStatus
from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfilePastProject,
)
from app.modules.rules.engine import Evaluation, evaluate
from app.modules.rules.facts import profile_facts, tender_facts
from app.modules.rules.models import FxRate, RuleOverride, RuleSet, RuleSetVersion
from app.modules.rules.schemas import (
    RuleSetDefinition,
    RuleStatus,
    RuleValidationError,
    RuleValidationResult,
)
from app.modules.tenders.models import Tender, TenderExtraction

logger = get_logger(__name__)

#: Money rules normalise to this before comparing.
BASE_CURRENCY = "USD"


async def active_version(session: AsyncSession, org_id: UUID) -> RuleSetVersion | None:
    """The rule set version currently in force for an organization."""
    rule_set = await session.scalar(
        select(RuleSet).where(RuleSet.org_id == org_id, RuleSet.is_active.is_(True))
    )
    if rule_set is None or rule_set.current_version_id is None:
        return None
    return await session.get(RuleSetVersion, rule_set.current_version_id)


def definition_of(version: RuleSetVersion | None) -> RuleSetDefinition:
    """Parse a stored definition, tolerating one written by an older schema.

    A definition that no longer validates must not take the whole feed down —
    every tender would lose its verdict. An empty set means "eligible", which
    is the same thing the customer saw before they wrote any rules.
    """
    if version is None:
        return RuleSetDefinition()
    try:
        return RuleSetDefinition.model_validate(version.definition)
    except Exception as exc:
        logger.warning("rule_set_version_unreadable", version_id=str(version.id), error=str(exc))
        return RuleSetDefinition()


async def fx_rates(session: AsyncSession, base: str = BASE_CURRENCY) -> dict[str, float]:
    """Latest rate per currency, as units of that currency per one base unit."""
    rows = await session.scalars(
        select(FxRate).where(FxRate.base == base).order_by(FxRate.as_of.desc())
    )
    rates: dict[str, float] = {}
    for row in rows.all():
        rates.setdefault(row.currency.upper(), row.rate)
    return rates


async def profile_children(
    session: AsyncSession, profile_id: UUID
) -> tuple[list[ProfileCertification], list[ProfilePastProject]]:
    certifications = list(
        (
            await session.scalars(
                select(ProfileCertification).where(ProfileCertification.profile_id == profile_id)
            )
        ).all()
    )
    projects = list(
        (
            await session.scalars(
                select(ProfilePastProject).where(ProfilePastProject.profile_id == profile_id)
            )
        ).all()
    )
    return certifications, projects


def apply_overrides(evaluation: Evaluation, overrides: dict[str, RuleOverride]) -> Evaluation:
    """Let a human's ruling replace the engine's on a rule it could not decide.

    Only unresolved rules are overridable. A person may answer a question the
    engine could not, but silently flipping a rule the engine *did* decide
    would make the stored reasoning a lie.
    """
    if not overrides:
        return evaluation

    updated: list[RuleStatus] = []
    for result in evaluation.results:
        override = overrides.get(result.rule_id)
        if override is None or result.status not in {"unknown", "warn"}:
            updated.append(result)
            continue
        note = f" ({override.note})" if override.note else ""
        updated.append(
            result.model_copy(
                update={
                    "status": override.verdict.value,
                    "reason": f"Confirmed by a teammate{note}.",
                    "source": "override",
                }
            )
        )
    return Evaluation(results=updated)


async def evaluate_for_tender(
    session: AsyncSession,
    *,
    tender: Tender,
    profile: CompanyProfile,
    org_id: UUID,
    definition: RuleSetDefinition | None = None,
    extraction: TenderExtraction | None = None,
    rates: dict[str, float] | None = None,
    now: datetime | None = None,
) -> Evaluation:
    """Evaluate one organization's criteria against one tender."""
    if definition is None:
        definition = definition_of(await active_version(session, org_id))
    if not definition.active_rules:
        return Evaluation(results=[])

    if extraction is None:
        extraction = await session.scalar(
            select(TenderExtraction).where(
                TenderExtraction.tender_id == tender.id,
                TenderExtraction.is_current.is_(True),
            )
        )

    certifications, projects = await profile_children(session, profile.id)
    attributes: dict[str, Any] = extraction.attributes if extraction else {}

    evaluation = evaluate(
        definition,
        tender=tender_facts(
            tender,
            attributes=attributes,
            confidence=extraction.field_confidence if extraction else {},
            evidence=extraction.evidence if extraction else {},
        ),
        profile=profile_facts(profile, certifications=certifications, projects=projects),
        fx=rates if rates is not None else await fx_rates(session),
        base_currency=BASE_CURRENCY,
        now=now,
    )

    overrides = {
        row.rule_id: row
        for row in (
            await session.scalars(
                select(RuleOverride).where(
                    RuleOverride.org_id == org_id, RuleOverride.tender_id == tender.id
                )
            )
        ).all()
    }
    return apply_overrides(evaluation, overrides)


def status_of(evaluation: Evaluation) -> EligibilityStatus:
    return evaluation.status


# -- persistence ------------------------------------------------------------


async def get_or_create_rule_set(session: AsyncSession, org_id: UUID) -> RuleSet:
    """One active rule set per organization, created empty on first use."""
    rule_set = await session.scalar(
        select(RuleSet).where(RuleSet.org_id == org_id, RuleSet.is_active.is_(True))
    )
    if rule_set is None:
        rule_set = RuleSet(org_id=org_id, name="Bidding criteria")
        session.add(rule_set)
        await session.flush()
    return rule_set


async def list_versions(session: AsyncSession, rule_set_id: UUID) -> list[RuleSetVersion]:
    rows = await session.scalars(
        select(RuleSetVersion)
        .where(RuleSetVersion.rule_set_id == rule_set_id)
        .order_by(RuleSetVersion.version_number.desc())
    )
    return list(rows.all())


async def save_version(
    session: AsyncSession,
    *,
    org_id: UUID,
    definition: RuleSetDefinition,
    name: str | None = None,
    note: str | None = None,
    created_by_id: UUID | None = None,
) -> RuleSetVersion:
    """Write a new immutable version and make it the one in force.

    Never mutates an existing version: a match records the version that graded
    it, so editing one in place would rewrite the reasoning behind verdicts a
    customer has already seen.
    """
    rule_set = await get_or_create_rule_set(session, org_id)
    if name:
        rule_set.name = name

    existing = await list_versions(session, rule_set.id)
    next_number = (existing[0].version_number + 1) if existing else 1

    version = RuleSetVersion(
        rule_set_id=rule_set.id,
        org_id=org_id,
        version_number=next_number,
        schema_version=definition.schema_version,
        definition=definition.model_dump(mode="json"),
        note=note,
        created_by_id=created_by_id,
    )
    session.add(version)
    await session.flush()

    rule_set.current_version_id = version.id
    await session.flush()
    logger.info(
        "rule_set_version_saved",
        org_id=str(org_id),
        version=next_number,
        rules=len(definition.rules),
    )
    return version


async def activate_version(
    session: AsyncSession, *, org_id: UUID, version_id: UUID
) -> RuleSetVersion:
    """Roll back to an earlier version by pointing the set at it."""
    rule_set = await get_or_create_rule_set(session, org_id)
    version = await session.get(RuleSetVersion, version_id)
    if version is None or version.rule_set_id != rule_set.id:
        raise NotFoundError("Rule set version not found.", code="rule_version_not_found")
    rule_set.current_version_id = version.id
    await session.flush()
    return version


def validate_definition(payload: dict[str, Any]) -> RuleValidationResult:
    """Check a draft without saving it.

    Errors are returned per rule rather than raised, so the builder can mark
    the offending row instead of showing one message for the whole form.
    """
    try:
        RuleSetDefinition.model_validate(payload)
    except PydanticValidationError as exc:
        errors: list[RuleValidationError] = []
        raw_rules = payload.get("rules") or []
        for detail in exc.errors():
            location = list(detail["loc"])
            rule_id: str | None = None
            if len(location) >= 2 and location[0] == "rules":
                index = location[1]
                if isinstance(index, int) and index < len(raw_rules):
                    rule_id = str(raw_rules[index].get("id") or index)
            errors.append(
                RuleValidationError(
                    rule_id=rule_id,
                    field=".".join(str(part) for part in location[2:]) or None,
                    message=detail["msg"],
                )
            )
        return RuleValidationResult(valid=False, errors=errors)
    return RuleValidationResult(valid=True)
