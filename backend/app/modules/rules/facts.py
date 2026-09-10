"""Turning stored rows into the flat view the engine reads.

This is the only place that knows an attribute key maps to a column here and an
extraction field there. Keeping it in one function means the engine stays pure
and the catalogue stays the single list of what exists.

The precedence rule matters: **portal metadata always wins over extraction.**
A scraped deadline is a fact and an inferred one is a guess, so where both
exist the scraped value is used and the model's is discarded rather than
averaged or preferred by confidence.
"""

from __future__ import annotations

from typing import Any

from app.modules.profiles.models import (
    CompanyProfile,
    ProfileCertification,
    ProfilePastProject,
)
from app.modules.rules.engine import ProfileFacts, TenderFacts
from app.modules.tenders.models import Tender

#: Extraction fields the portal also provides. The portal's value is used and
#: the model's is dropped — see the module docstring.
_PORTAL_WINS = frozenset({"deadline_at", "procurement_method", "procurement_category", "country"})


def _money(value: Any, fallback_currency: str | None = None) -> dict[str, Any] | None:
    """Normalise whatever the extraction produced into `{amount, currency}`."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return {"amount": float(value), "currency": fallback_currency}
    if isinstance(value, dict):
        amount = value.get("amount")
        if amount is None:
            return None
        return {"amount": float(amount), "currency": value.get("currency") or fallback_currency}
    return None


def tender_facts(
    tender: Tender,
    *,
    attributes: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
) -> TenderFacts:
    """Everything a rule may read about one tender.

    A key that is absent from ``values`` is unknown to the engine, which is
    different from being present and ``None``. Only set a key when there is
    genuinely something to say.
    """
    extracted = attributes or {}
    values: dict[str, Any] = {}

    # -- from the model, where it offered anything ---------------------------
    for key in (
        "min_annual_turnover",
        "bid_security",
        "estimated_value",
    ):
        money = _money(extracted.get(key), tender.currency)
        if money is not None:
            values[key] = money

    for key in ("required_certifications", "eligible_countries", "sectors"):
        listed = extracted.get(key)
        if listed is not None:
            values[key] = list(listed)

    for key in ("min_years_experience", "similar_projects_required"):
        number = extracted.get(key)
        if isinstance(number, int | float):
            values[key] = number

    for key in ("jv_allowed", "local_registration_required"):
        flag = extracted.get(key)
        if isinstance(flag, bool):
            values[key] = flag

    # -- from the portal, which wins ----------------------------------------
    if tender.estimated_value is not None:
        values["estimated_value"] = {
            "amount": float(tender.estimated_value),
            "currency": tender.currency,
        }
    if tender.deadline_at is not None:
        values["deadline_at"] = tender.deadline_at
    if tender.country:
        values["country"] = tender.country
    if tender.procurement_method:
        values["procurement_method"] = tender.procurement_method
    values["procurement_category"] = tender.procurement_category.value
    if tender.language:
        values["language"] = tender.language
    if tender.title:
        values["title"] = tender.title
    if tender.procuring_entity:
        values["procuring_entity"] = tender.procuring_entity

    values["full_text"] = " ".join(
        part for part in (tender.title, tender.summary, tender.description) if part
    )

    # A confidence for a field the portal supplied would be misleading: the
    # value in `values` is not the one the model scored.
    scores = {
        key: float(score)
        for key, score in (confidence or {}).items()
        if key not in _PORTAL_WINS and isinstance(score, int | float)
    }
    quotes = {
        key: str(quote)
        for key, quote in (evidence or {}).items()
        if key not in _PORTAL_WINS and quote
    }

    return TenderFacts(values=values, confidence=scores, evidence=quotes, currency=tender.currency)


def profile_facts(
    profile: CompanyProfile,
    *,
    certifications: list[ProfileCertification] | None = None,
    projects: list[ProfilePastProject] | None = None,
) -> ProfileFacts:
    """Everything a rule may compare against."""
    values: dict[str, Any] = {}

    if profile.annual_turnover is not None:
        values["annual_turnover"] = {
            "amount": float(profile.annual_turnover),
            "currency": profile.turnover_currency,
        }
    if profile.years_in_business is not None:
        values["years_in_business"] = profile.years_in_business
    if profile.employee_count is not None:
        values["employee_count"] = profile.employee_count

    values["accepts_jv"] = profile.accepts_jv
    values["sectors"] = list(profile.sectors or [])
    values["geographies"] = list(profile.geographies or [])
    values["keywords"] = list(profile.keywords or [])
    values["certification_codes"] = [c.code for c in certifications or []]
    values["past_project_count"] = len(projects or [])

    return ProfileFacts(values=values, currency=profile.turnover_currency)
