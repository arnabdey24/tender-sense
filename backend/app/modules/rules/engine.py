"""Deciding whether a company may bid.

Three outcomes, not two. A rule whose attribute could not be determined returns
``unknown`` and becomes whatever the rule's ``on_missing`` says — by default
"verify", which surfaces the tender for a human rather than deciding for them.
That is the single most important behaviour in this module: the cost of a false
"ineligible" is a contract the customer never sees, and it is silent.

Nothing here touches the database or the network. It takes a rule set, a
resolved view of the tender, and a resolved view of the profile, and returns a
list of per-rule outcomes. That makes it exhaustively testable, and it is why
the preview endpoint can run a draft over 2,000 tenders without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.ai.schemas import MIN_USABLE_CONFIDENCE
from app.core.text import comparison_key
from app.core.time import utcnow
from app.modules.matching.models import EligibilityStatus
from app.modules.rules.catalogue import (
    AttributeSource,
    AttributeType,
    OnMissing,
    Operator,
    Severity,
)
from app.modules.rules.schemas import (
    LiteralValue,
    ProfileValue,
    RuleDefinition,
    RuleSetDefinition,
    RuleStatus,
)


class Unknown:
    """Distinct from ``None``.

    ``None`` can be a real answer — "this notice places no country restriction"
    — while Unknown means "we could not find out". Collapsing the two is how a
    rule ends up confidently rejecting a tender nobody actually checked.
    """

    _instance: Unknown | None = None

    def __new__(cls) -> Unknown:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "UNKNOWN"

    def __bool__(self) -> bool:
        return False


UNKNOWN = Unknown()


@dataclass(slots=True)
class TenderFacts:
    """Everything a rule may read about one tender, already resolved.

    ``confidence`` and ``evidence`` are only populated for attributes that came
    from the model; a scraped field needs neither.
    """

    values: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    currency: str | None = None

    def get(self, key: str) -> Any:
        return self.values.get(key, UNKNOWN)


@dataclass(slots=True)
class ProfileFacts:
    """Everything a rule may compare against, from our own profile."""

    values: dict[str, Any] = field(default_factory=dict)
    currency: str | None = None

    def get(self, key: str) -> Any:
        return self.values.get(key, UNKNOWN)


@dataclass(slots=True)
class Evaluation:
    results: list[RuleStatus] = field(default_factory=list)

    @property
    def status(self) -> EligibilityStatus:
        """Any hard failure disqualifies; any hard unknown asks a human.

        Order matters: a definite failure outranks an unanswered question,
        because there is nothing to verify once a hard rule has already said no.
        """
        hard = [r for r in self.results if r.severity is Severity.HARD]
        if any(r.status == "fail" for r in hard):
            return EligibilityStatus.INELIGIBLE
        if any(r.status == "unknown" for r in hard):
            return EligibilityStatus.NEEDS_VERIFICATION
        return EligibilityStatus.ELIGIBLE

    @property
    def failing(self) -> list[RuleStatus]:
        return [r for r in self.results if r.status == "fail"]

    @property
    def unresolved(self) -> list[RuleStatus]:
        return [r for r in self.results if r.status in {"unknown", "warn"}]

    def as_json(self) -> list[dict[str, Any]]:
        return [result.model_dump(mode="json") for result in self.results]


# -- normalisation ----------------------------------------------------------


def _amount_and_currency(value: Any, *, base: str) -> tuple[float, str] | None:
    """Pull an amount and its currency out of whatever shape a value has."""
    if isinstance(value, int | float):
        return float(value), base.upper()
    if not isinstance(value, dict):
        return None
    amount = value.get("amount")
    if amount is None:
        return None
    return float(amount), (value.get("currency") or base or "").upper()


def _convert(
    amount: float, currency: str, *, fx: dict[str, float] | None, base: str
) -> float | None:
    if currency == base.upper():
        return amount
    rate = (fx or {}).get(currency)
    if rate is None or rate == 0:
        return None
    return amount / rate


def _comparable_pair(
    left: Any, right: Any, *, fx: dict[str, float] | None, base: str
) -> tuple[float, float] | None:
    """Put two money values on the same scale, or give up.

    Amounts already sharing a currency are compared directly and need no rate
    at all — a Bangladeshi buyer's BDT requirement against a BDT profile is a
    plain comparison. Only a genuine cross-currency pair needs converting, and
    an unconvertible one is unknown rather than compared raw, because BDT
    against USD uncompared is a hundredfold error rather than a near miss.
    """
    a = _amount_and_currency(left, base=base)
    b = _amount_and_currency(right, base=base)
    if a is None or b is None:
        return None

    (left_amount, left_currency), (right_amount, right_currency) = a, b
    if left_currency == right_currency:
        return left_amount, right_amount

    converted_left = _convert(left_amount, left_currency, fx=fx, base=base)
    converted_right = _convert(right_amount, right_currency, fx=fx, base=base)
    if converted_left is None or converted_right is None:
        return None
    return converted_left, converted_right


def _as_list(value: Any) -> list[str] | None:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return None


def _fold(items: list[str]) -> set[str]:
    """Comparison keys, shared with how the profile stores them.

    "ISO 9001" in a notice has to match "iso-9001" in a profile, or every
    certification rule is a coin flip on how someone typed it. Both sides use
    `comparison_key`, so the two can never drift apart.
    """
    return {comparison_key(item) for item in items if item}


def _render(value: Any) -> str:
    if value is UNKNOWN:
        return "not stated"
    if value is None:
        return "none"
    if isinstance(value, dict) and "amount" in value:
        amount = value.get("amount")
        currency = value.get("currency") or ""
        return f"{currency} {amount:,.0f}".strip() if amount is not None else "not stated"
    if isinstance(value, list | tuple | set):
        return ", ".join(str(item) for item in value) or "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


# -- operators --------------------------------------------------------------


def _compare(
    operator: Operator,
    attribute_type: AttributeType,
    tender_value: Any,
    expected: Any,
    *,
    fx: dict[str, float] | None,
    base_currency: str,
    now: datetime,
) -> bool | None:
    """Apply one operator. ``None`` means "could not decide"."""
    if attribute_type is AttributeType.MONEY:
        if operator is Operator.BETWEEN:
            bounds = expected if isinstance(expected, dict) else {}
            low_pair = _comparable_pair(tender_value, bounds.get("min"), fx=fx, base=base_currency)
            high_pair = _comparable_pair(tender_value, bounds.get("max"), fx=fx, base=base_currency)
            if low_pair is None and high_pair is None:
                return None
            if low_pair is not None and low_pair[0] < low_pair[1]:
                return False
            return not (high_pair is not None and high_pair[0] > high_pair[1])

        pair = _comparable_pair(tender_value, expected, fx=fx, base=base_currency)
        if pair is None:
            return None
        left, right = pair
        return left <= right if operator is Operator.LTE else left >= right

    if attribute_type is AttributeType.INTEGER:
        if not isinstance(tender_value, int | float):
            return None
        if operator is Operator.BETWEEN:
            bounds = expected if isinstance(expected, dict) else {}
            low, high = bounds.get("min"), bounds.get("max")
            if low is None and high is None:
                return None
            if low is not None and tender_value < low:
                return False
            return not (high is not None and tender_value > high)
        if not isinstance(expected, int | float):
            return None
        return tender_value <= expected if operator is Operator.LTE else tender_value >= expected

    if attribute_type in {AttributeType.LIST, AttributeType.ENUM}:
        left_list = _as_list(tender_value)
        right_list = _as_list(expected)
        if left_list is None or right_list is None:
            return None
        left_set, right_set = _fold(left_list), _fold(right_list)
        if operator is Operator.IN:
            return bool(left_set) and left_set <= right_set
        if operator is Operator.NOT_IN:
            return not (left_set & right_set)
        if operator is Operator.INTERSECTS:
            # An empty tender list means "unrestricted", which intersects with
            # anything — a notice naming no eligible countries excludes nobody.
            return True if not left_set else bool(left_set & right_set)
        if operator is Operator.SUBSET_OF:
            return left_set <= right_set
        return None

    if attribute_type is AttributeType.BOOLEAN:
        if not isinstance(tender_value, bool) or not isinstance(expected, bool):
            return None
        return tender_value is expected

    if attribute_type is AttributeType.TEXT:
        if not isinstance(tender_value, str):
            return None
        terms = _as_list(expected) or []
        if not terms:
            return None
        haystack = tender_value.lower()
        hit = any(term.lower().strip() in haystack for term in terms if term.strip())
        return hit if operator is Operator.CONTAINS_ANY else not hit

    if attribute_type is AttributeType.DATETIME:
        if not isinstance(tender_value, datetime):
            return None
        if operator is Operator.WITHIN_DAYS:
            days = expected.get("days") if isinstance(expected, dict) else expected
            if not isinstance(days, int | float):
                return None
            return 0 <= (tender_value - now).total_seconds() <= days * 86400
        if operator is Operator.AFTER:
            if isinstance(expected, dict) and "days_from_now" in expected:
                days = expected["days_from_now"]
                if not isinstance(days, int | float):
                    return None
                return (tender_value - now).total_seconds() >= days * 86400
            if isinstance(expected, datetime):
                return tender_value > expected
            return None

    return None


# -- evaluation -------------------------------------------------------------


def _resolve_expected(rule: RuleDefinition, profile: ProfileFacts) -> Any:
    if isinstance(rule.value, ProfileValue):
        return profile.get(rule.value.field)
    if isinstance(rule.value, LiteralValue):
        return rule.value.data
    return UNKNOWN  # pragma: no cover - the union is closed


def _unknown_status(rule: RuleDefinition, *, reason: str, **extra: Any) -> RuleStatus:
    """Turn an undecidable rule into the outcome its `on_missing` asks for."""
    status = {
        OnMissing.PASS: "pass",
        OnMissing.FAIL: "fail",
        OnMissing.VERIFY: "unknown",
    }[rule.on_missing]
    # A soft rule can never make a tender ineligible, so an undecidable soft
    # rule is a note rather than a question.
    if status == "unknown" and rule.severity is Severity.SOFT:
        status = "warn"
    return RuleStatus(
        rule_id=rule.id,
        label=rule.display_label(),
        attribute=rule.attribute,
        operator=rule.operator,
        severity=rule.severity,
        status=status,
        reason=reason,
        source=rule.catalogue_entry.source.value,
        **extra,
    )


def evaluate_rule(
    rule: RuleDefinition,
    *,
    tender: TenderFacts,
    profile: ProfileFacts,
    fx: dict[str, float] | None = None,
    base_currency: str = "USD",
    now: datetime | None = None,
) -> RuleStatus:
    """Evaluate one rule. Never raises; an undecidable rule is `unknown`."""
    entry = rule.catalogue_entry
    moment = now or utcnow()
    tender_value = tender.get(rule.attribute)
    expected = _resolve_expected(rule, profile)

    confidence = tender.confidence.get(rule.attribute)
    evidence = tender.evidence.get(rule.attribute)
    shared: dict[str, Any] = {
        "tender_value": _render(tender_value),
        "expected": _render(expected),
        "confidence": confidence,
        "evidence": evidence,
    }

    if tender_value is UNKNOWN:
        return _unknown_status(
            rule, reason=f"The notice does not state {entry.label.lower()}.", **shared
        )

    # An extracted attribute the model was unsure about is not evidence. Acting
    # on it would mean rejecting a tender on a guess.
    if (
        entry.source is AttributeSource.AI_EXTRACTION
        and confidence is not None
        and confidence < MIN_USABLE_CONFIDENCE
    ):
        return _unknown_status(
            rule,
            reason=(
                f"{entry.label} was read from the notice with low confidence "
                f"({confidence:.0%}); check it before relying on this."
            ),
            **shared,
        )

    if expected is UNKNOWN:
        source = (
            f"your profile's {rule.value.field.replace('_', ' ')}"
            if isinstance(rule.value, ProfileValue)
            else "this rule"
        )
        return _unknown_status(
            rule, reason=f"Nothing to compare against — {source} is not set.", **shared
        )

    outcome = _compare(
        rule.operator,
        entry.type,
        tender_value,
        expected,
        fx=fx,
        base_currency=base_currency,
        now=moment,
    )
    if outcome is None:
        return _unknown_status(
            rule,
            reason=f"{entry.label} could not be compared with what the rule expects.",
            **shared,
        )

    reason = (
        f"{entry.label}: {shared['tender_value']} meets {shared['expected']}."
        if outcome
        else f"{entry.label}: {shared['tender_value']} does not meet {shared['expected']}."
    )
    return RuleStatus(
        rule_id=rule.id,
        label=rule.display_label(),
        attribute=rule.attribute,
        operator=rule.operator,
        severity=rule.severity,
        status="pass" if outcome else "fail",
        reason=reason,
        source=entry.source.value,
        **shared,
    )


def evaluate(
    definition: RuleSetDefinition,
    *,
    tender: TenderFacts,
    profile: ProfileFacts,
    fx: dict[str, float] | None = None,
    base_currency: str = "USD",
    now: datetime | None = None,
) -> Evaluation:
    """Evaluate a whole rule set.

    An empty rule set is eligible, not unknown: a customer who has written no
    criteria has not failed to answer anything.
    """
    results = [
        evaluate_rule(
            rule,
            tender=tender,
            profile=profile,
            fx=fx,
            base_currency=base_currency,
            now=now,
        )
        for rule in definition.active_rules
    ]
    return Evaluation(results=results)
