"""The eligibility engine, operator by operator.

Exhaustive rather than representative. A wrong operator silently hides tenders
a customer could have won, or waves through ones they are barred from, and
neither failure shows up as an error anywhere — so the coverage has to come
from here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.modules.matching.models import EligibilityStatus
from app.modules.rules.catalogue import (
    ATTRIBUTES,
    OPERATORS_BY_TYPE,
    PRESETS,
    OnMissing,
    Operator,
    Severity,
    get_attribute,
)
from app.modules.rules.engine import (
    UNKNOWN,
    ProfileFacts,
    TenderFacts,
    evaluate,
    evaluate_rule,
)
from app.modules.rules.schemas import RuleDefinition, RuleSetDefinition

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def rule(**overrides: Any) -> RuleDefinition:
    defaults: dict[str, Any] = {
        "id": "r1",
        "attribute": "min_annual_turnover",
        "operator": Operator.LTE,
        "value": {"source": "profile", "field": "annual_turnover"},
        "severity": Severity.HARD,
        "on_missing": OnMissing.VERIFY,
    }
    return RuleDefinition.model_validate(defaults | overrides)


def run(
    definition: RuleDefinition,
    *,
    tender: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    confidence: dict[str, float] | None = None,
    fx: dict[str, float] | None = None,
) -> str:
    result = evaluate_rule(
        definition,
        tender=TenderFacts(values=tender or {}, confidence=confidence or {}),
        profile=ProfileFacts(values=profile or {}),
        fx=fx,
        now=NOW,
    )
    return result.status


class TestCatalogueIntegrity:
    def test_every_attribute_has_usable_operators(self) -> None:
        for attribute in ATTRIBUTES:
            assert attribute.allowed_operators, attribute.key
            assert set(attribute.allowed_operators) <= set(OPERATORS_BY_TYPE[attribute.type]), (
                attribute.key
            )

    def test_every_preset_is_a_valid_rule(self) -> None:
        """A preset the engine would reject is worse than no preset."""
        for preset in PRESETS:
            built = RuleDefinition.model_validate(
                {
                    "id": preset.key,
                    "attribute": preset.attribute,
                    "operator": preset.operator,
                    "value": preset.value,
                    "severity": preset.severity,
                    "on_missing": preset.on_missing,
                    "template": preset.key,
                }
            )
            assert built.attribute == preset.attribute

    def test_an_unknown_attribute_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown attribute"):
            rule(attribute="not_a_thing")

    def test_an_operator_the_attribute_cannot_take_is_rejected(self) -> None:
        """The builder reads the same catalogue, so this should be unreachable
        from the UI — which is exactly why it must fail loudly if it happens."""
        with pytest.raises(ValueError, match="does not support"):
            rule(attribute="jv_allowed", operator=Operator.BETWEEN)


class TestMoney:
    @pytest.mark.parametrize(
        ("required", "capacity", "expected"),
        [
            (5_000_000, 20_000_000, "pass"),
            (20_000_000, 20_000_000, "pass"),
            (50_000_000, 20_000_000, "fail"),
        ],
    )
    def test_turnover_within_capacity(
        self, required: float, capacity: float, expected: str
    ) -> None:
        assert (
            run(
                rule(),
                tender={"min_annual_turnover": {"amount": required, "currency": "USD"}},
                profile={"annual_turnover": {"amount": capacity, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.9},
            )
            == expected
        )

    def test_currencies_are_converted_before_comparing(self) -> None:
        """BDT against USD uncompared is a hundredfold error, not a near miss."""
        status = run(
            rule(),
            tender={"min_annual_turnover": {"amount": 10_000_000, "currency": "BDT"}},
            profile={"annual_turnover": {"amount": 200_000, "currency": "USD"}},
            confidence={"min_annual_turnover": 0.9},
            fx={"BDT": 110.0},  # 10m BDT ≈ 91k USD, within a 200k capacity
        )

        assert status == "pass"

    def test_an_unconvertible_currency_is_unknown_not_compared_raw(self) -> None:
        status = run(
            rule(),
            tender={"min_annual_turnover": {"amount": 10_000_000, "currency": "BDT"}},
            profile={"annual_turnover": {"amount": 200_000, "currency": "USD"}},
            confidence={"min_annual_turnover": 0.9},
            fx={},  # no rate for BDT
        )

        assert status == "unknown"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(50_000, "fail"), (150_000, "pass"), (5_000_000, "pass"), (9_000_000, "fail")],
    )
    def test_between(self, value: float, expected: str) -> None:
        status = run(
            rule(
                id="r_value",
                attribute="estimated_value",
                operator=Operator.BETWEEN,
                value={
                    "source": "literal",
                    "data": {
                        "min": {"amount": 100_000, "currency": "USD"},
                        "max": {"amount": 5_000_000, "currency": "USD"},
                    },
                },
            ),
            tender={"estimated_value": {"amount": value, "currency": "USD"}},
        )
        assert status == expected

    def test_between_with_no_bounds_is_unknown(self) -> None:
        status = run(
            rule(
                id="r_value",
                attribute="estimated_value",
                operator=Operator.BETWEEN,
                value={"source": "literal", "data": {"min": None, "max": None}},
            ),
            tender={"estimated_value": {"amount": 1000, "currency": "USD"}},
        )
        assert status == "unknown"


class TestLists:
    @pytest.mark.parametrize(
        ("required", "held", "expected"),
        [
            ([], ["ISO9001"], "pass"),
            (["ISO 9001"], ["ISO9001", "ISO27001"], "pass"),
            (["ISO 9001", "ISO 27001"], ["ISO9001"], "fail"),
        ],
    )
    def test_certifications_subset_of_what_we_hold(
        self, required: list[str], held: list[str], expected: str
    ) -> None:
        assert (
            run(
                rule(
                    id="r_certs",
                    attribute="required_certifications",
                    operator=Operator.SUBSET_OF,
                    value={"source": "profile", "field": "certification_codes"},
                ),
                tender={"required_certifications": required},
                profile={"certification_codes": held},
                confidence={"required_certifications": 0.8},
            )
            == expected
        )

    def test_spelling_and_punctuation_do_not_decide_eligibility(self) -> None:
        """ "ISO 9001" in a notice must match "iso-9001" in a profile."""
        assert (
            run(
                rule(
                    id="r_certs",
                    attribute="required_certifications",
                    operator=Operator.SUBSET_OF,
                    value={"source": "profile", "field": "certification_codes"},
                ),
                tender={"required_certifications": ["ISO 9001:2015"]},
                profile={"certification_codes": ["iso-9001"]},
                confidence={"required_certifications": 0.8},
            )
            == "pass"
        )

    def test_an_unrestricted_notice_excludes_nobody(self) -> None:
        """A notice naming no eligible countries is open to everyone; treating
        the empty list as "no overlap" would hide every unrestricted tender."""
        assert (
            run(
                rule(
                    id="r_countries",
                    attribute="eligible_countries",
                    operator=Operator.INTERSECTS,
                    value={"source": "profile", "field": "geographies"},
                ),
                tender={"eligible_countries": []},
                profile={"geographies": ["BD"]},
                confidence={"eligible_countries": 0.7},
            )
            == "pass"
        )

    @pytest.mark.parametrize(
        ("eligible", "ours", "expected"),
        [(["BD", "NP"], ["BD"], "pass"), (["IN", "LK"], ["BD"], "fail")],
    )
    def test_intersects(self, eligible: list[str], ours: list[str], expected: str) -> None:
        assert (
            run(
                rule(
                    id="r_countries",
                    attribute="eligible_countries",
                    operator=Operator.INTERSECTS,
                    value={"source": "profile", "field": "geographies"},
                ),
                tender={"eligible_countries": eligible},
                profile={"geographies": ours},
                confidence={"eligible_countries": 0.7},
            )
            == expected
        )

    @pytest.mark.parametrize(
        ("method", "allowed", "expected"),
        [("Open Tendering", ["Open Tendering"], "pass"), ("RFQ", ["Open Tendering"], "fail")],
    )
    def test_enum_in(self, method: str, allowed: list[str], expected: str) -> None:
        assert (
            run(
                rule(
                    id="r_method",
                    attribute="procurement_method",
                    operator=Operator.IN,
                    value={"source": "literal", "data": allowed},
                    severity=Severity.SOFT,
                ),
                tender={"procurement_method": method},
            )
            == expected
        )

    def test_not_in(self) -> None:
        assert (
            run(
                rule(
                    id="r_method",
                    attribute="procurement_method",
                    operator=Operator.NOT_IN,
                    value={"source": "literal", "data": ["Direct Procurement"]},
                    severity=Severity.SOFT,
                ),
                tender={"procurement_method": "Direct Procurement"},
            )
            == "fail"
        )


class TestIntegers:
    @pytest.mark.parametrize(
        ("required", "have", "expected"), [(3, 10, "pass"), (10, 10, "pass"), (15, 10, "fail")]
    )
    def test_years_of_experience(self, required: int, have: int, expected: str) -> None:
        assert (
            run(
                rule(
                    id="r_years",
                    attribute="min_years_experience",
                    operator=Operator.LTE,
                    value={"source": "profile", "field": "years_in_business"},
                ),
                tender={"min_years_experience": required},
                profile={"years_in_business": have},
                confidence={"min_years_experience": 0.8},
            )
            == expected
        )


class TestBooleans:
    @pytest.mark.parametrize(
        ("allowed", "want", "expected"),
        [(True, True, "pass"), (False, True, "fail"), (False, False, "pass")],
    )
    def test_jv_allowed(self, allowed: bool, want: bool, expected: str) -> None:
        assert (
            run(
                rule(
                    id="r_jv",
                    attribute="jv_allowed",
                    operator=Operator.EQ,
                    value={"source": "literal", "data": want},
                ),
                tender={"jv_allowed": allowed},
                confidence={"jv_allowed": 0.8},
            )
            == expected
        )


class TestText:
    @pytest.mark.parametrize(
        ("text", "terms", "expected"),
        [
            ("Demolition of an old bridge", ["demolition"], "fail"),
            ("Supply of network switches", ["demolition"], "pass"),
            ("DEMOLITION works", ["demolition"], "fail"),
        ],
    )
    def test_exclude_keywords(self, text: str, terms: list[str], expected: str) -> None:
        assert (
            run(
                rule(
                    id="r_exclude",
                    attribute="full_text",
                    operator=Operator.NOT_CONTAINS_ANY,
                    value={"source": "literal", "data": terms},
                    on_missing=OnMissing.PASS,
                ),
                tender={"full_text": text},
            )
            == expected
        )

    def test_an_empty_term_list_is_unknown_rather_than_matching_everything(self) -> None:
        assert (
            run(
                rule(
                    id="r_exclude",
                    attribute="full_text",
                    operator=Operator.NOT_CONTAINS_ANY,
                    value={"source": "literal", "data": []},
                ),
                tender={"full_text": "anything"},
            )
            == "unknown"
        )


class TestDatetime:
    def test_after_a_relative_horizon(self) -> None:
        assert (
            run(
                rule(
                    id="r_time",
                    attribute="deadline_at",
                    operator=Operator.AFTER,
                    value={"source": "literal", "data": {"days_from_now": 7}},
                    severity=Severity.SOFT,
                ),
                tender={"deadline_at": NOW + timedelta(days=10)},
            )
            == "pass"
        )

    def test_a_deadline_inside_the_horizon_fails(self) -> None:
        assert (
            run(
                rule(
                    id="r_time",
                    attribute="deadline_at",
                    operator=Operator.AFTER,
                    value={"source": "literal", "data": {"days_from_now": 7}},
                    severity=Severity.SOFT,
                ),
                tender={"deadline_at": NOW + timedelta(days=2)},
            )
            == "fail"
        )

    def test_within_days(self) -> None:
        assert (
            run(
                rule(
                    id="r_soon",
                    attribute="deadline_at",
                    operator=Operator.WITHIN_DAYS,
                    value={"source": "literal", "data": {"days": 14}},
                    severity=Severity.SOFT,
                ),
                tender={"deadline_at": NOW + timedelta(days=3)},
            )
            == "pass"
        )


class TestUnknowns:
    """The behaviour that keeps the product honest."""

    def test_a_missing_attribute_asks_for_verification_by_default(self) -> None:
        assert run(rule(), tender={}, profile={"annual_turnover": 100}) == "unknown"

    def test_on_missing_pass_lets_it_through(self) -> None:
        assert (
            run(rule(on_missing=OnMissing.PASS), tender={}, profile={"annual_turnover": 100})
            == "pass"
        )

    def test_on_missing_fail_rejects(self) -> None:
        assert (
            run(rule(on_missing=OnMissing.FAIL), tender={}, profile={"annual_turnover": 100})
            == "fail"
        )

    def test_a_low_confidence_extraction_is_not_evidence(self) -> None:
        """Rejecting a tender on a guess is the failure mode that costs money."""
        assert (
            run(
                rule(),
                tender={"min_annual_turnover": {"amount": 999_000_000, "currency": "USD"}},
                profile={"annual_turnover": {"amount": 1000, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.3},
            )
            == "unknown"
        )

    def test_a_confident_extraction_is_acted_on(self) -> None:
        assert (
            run(
                rule(),
                tender={"min_annual_turnover": {"amount": 999_000_000, "currency": "USD"}},
                profile={"annual_turnover": {"amount": 1000, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.9},
            )
            == "fail"
        )

    def test_a_scraped_attribute_needs_no_confidence(self) -> None:
        """Portal metadata is a fact; demanding a confidence score for it would
        make every rule over scraped data permanently unknown."""
        assert get_attribute("procurement_method") is not None
        assert (
            run(
                rule(
                    id="r_method",
                    attribute="procurement_method",
                    operator=Operator.IN,
                    value={"source": "literal", "data": ["RFQ"]},
                ),
                tender={"procurement_method": "RFQ"},
            )
            == "pass"
        )

    def test_an_unset_profile_field_is_unknown_not_a_failure(self) -> None:
        """A customer who has not filled in their turnover has not failed a
        requirement; they have not answered one."""
        result = evaluate_rule(
            rule(),
            tender=TenderFacts(
                values={"min_annual_turnover": {"amount": 100, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.9},
            ),
            profile=ProfileFacts(values={}),
            now=NOW,
        )

        assert result.status == "unknown"
        assert "annual turnover" in result.reason

    def test_an_undecidable_soft_rule_is_a_warning_not_a_question(self) -> None:
        """A soft rule can never make a tender ineligible, so leaving it
        "unknown" would put a question mark on something nobody needs to answer."""
        assert run(rule(severity=Severity.SOFT), tender={}) == "warn"

    def test_unknown_is_not_none(self) -> None:
        """`None` is a real answer — "no restriction" — and must not collapse
        into "we could not find out"."""
        assert UNKNOWN is not None
        assert not UNKNOWN
        assert TenderFacts(values={"x": None}).get("x") is None
        assert TenderFacts(values={}).get("x") is UNKNOWN


class TestRuleSet:
    def _set(self, *rules: RuleDefinition) -> RuleSetDefinition:
        return RuleSetDefinition(rules=list(rules))

    def _status(
        self, definition: RuleSetDefinition, tender: dict[str, Any], profile: dict[str, Any]
    ) -> EligibilityStatus:
        return evaluate(
            definition,
            tender=TenderFacts(values=tender, confidence=dict.fromkeys(tender, 0.9)),
            profile=ProfileFacts(values=profile),
            now=NOW,
        ).status

    def test_no_rules_means_eligible(self) -> None:
        """A customer who has written no criteria has not failed to answer."""
        assert self._status(self._set(), {}, {}) is EligibilityStatus.ELIGIBLE

    def test_one_hard_failure_disqualifies(self) -> None:
        assert (
            self._status(
                self._set(rule()),
                {"min_annual_turnover": {"amount": 100, "currency": "USD"}},
                {"annual_turnover": {"amount": 10, "currency": "USD"}},
            )
            is EligibilityStatus.INELIGIBLE
        )

    def test_a_hard_unknown_asks_for_verification(self) -> None:
        assert (
            self._status(self._set(rule()), {}, {"annual_turnover": 100})
            is EligibilityStatus.NEEDS_VERIFICATION
        )

    def test_a_definite_failure_outranks_an_open_question(self) -> None:
        """There is nothing left to verify once a hard rule has said no."""
        failing = rule(id="r_fail")
        unknown = rule(id="r_unknown", attribute="bid_security", operator=Operator.LTE)
        status = self._status(
            self._set(failing, unknown),
            {"min_annual_turnover": {"amount": 100, "currency": "USD"}},
            {"annual_turnover": {"amount": 10, "currency": "USD"}},
        )

        assert status is EligibilityStatus.INELIGIBLE

    def test_a_soft_rule_never_makes_a_tender_ineligible(self) -> None:
        soft = rule(id="r_soft", severity=Severity.SOFT)
        assert (
            self._status(
                self._set(soft),
                {"min_annual_turnover": {"amount": 100, "currency": "USD"}},
                {"annual_turnover": {"amount": 10, "currency": "USD"}},
            )
            is EligibilityStatus.ELIGIBLE
        )

    def test_a_disabled_rule_is_not_evaluated(self) -> None:
        assert (
            self._status(
                self._set(rule(enabled=False)),
                {"min_annual_turnover": {"amount": 100, "currency": "USD"}},
                {"annual_turnover": {"amount": 10, "currency": "USD"}},
            )
            is EligibilityStatus.ELIGIBLE
        )

    def test_duplicate_rule_ids_are_rejected(self) -> None:
        """Two rules with one id makes a per-rule override ambiguous."""
        with pytest.raises(ValueError, match="Duplicate rule ids"):
            RuleSetDefinition(rules=[rule(id="same"), rule(id="same")])

    def test_results_carry_evidence_for_the_ui(self) -> None:
        evaluation = evaluate(
            self._set(rule()),
            tender=TenderFacts(
                values={"min_annual_turnover": {"amount": 100, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.91},
                evidence={"min_annual_turnover": "average annual turnover of USD 100"},
            ),
            profile=ProfileFacts(values={"annual_turnover": {"amount": 500, "currency": "USD"}}),
            now=NOW,
        )

        result = evaluation.results[0]
        assert result.status == "pass"
        assert result.confidence == pytest.approx(0.91)
        assert result.evidence == "average annual turnover of USD 100"
        assert "USD 100" in (result.tender_value or "")
        assert evaluation.as_json()[0]["rule_id"] == "r1"


class TestSameCurrency:
    """A rule between two amounts in one currency must not need an FX rate.

    Caught by the rule preview showing every tender as "needs checking" for a
    Bangladeshi customer whose notices and profile were both in BDT: each side
    was converted to USD independently, and with no stored rate both became
    unknown — so a money rule could never decide anything.
    """

    def _turnover(self, currency: str, fx: dict[str, float] | None = None) -> str:
        return run(
            rule(),
            tender={"min_annual_turnover": {"amount": 5_000_000, "currency": currency}},
            profile={"annual_turnover": {"amount": 20_000_000, "currency": currency}},
            confidence={"min_annual_turnover": 0.9},
            fx=fx,
        )

    @pytest.mark.parametrize("currency", ["BDT", "USD", "NPR"])
    def test_matching_currencies_compare_without_any_rate(self, currency: str) -> None:
        assert self._turnover(currency) == "pass"

    def test_a_failure_is_still_detected_without_a_rate(self) -> None:
        assert (
            run(
                rule(),
                tender={"min_annual_turnover": {"amount": 50_000_000, "currency": "BDT"}},
                profile={"annual_turnover": {"amount": 20_000_000, "currency": "BDT"}},
                confidence={"min_annual_turnover": 0.9},
            )
            == "fail"
        )

    def test_a_cross_currency_pair_still_needs_a_rate(self) -> None:
        """The protection that made this bug worth having in the first place."""
        assert (
            run(
                rule(),
                tender={"min_annual_turnover": {"amount": 5_000_000, "currency": "BDT"}},
                profile={"annual_turnover": {"amount": 20_000_000, "currency": "USD"}},
                confidence={"min_annual_turnover": 0.9},
            )
            == "unknown"
        )

    def test_between_bounds_in_the_tenders_own_currency(self) -> None:
        assert (
            run(
                rule(
                    id="r_value",
                    attribute="estimated_value",
                    operator=Operator.BETWEEN,
                    value={
                        "source": "literal",
                        "data": {
                            "min": {"amount": 1_000_000, "currency": "BDT"},
                            "max": {"amount": 100_000_000, "currency": "BDT"},
                        },
                    },
                ),
                tender={"estimated_value": {"amount": 50_000_000, "currency": "BDT"}},
            )
            == "pass"
        )
