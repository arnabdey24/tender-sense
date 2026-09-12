"""Numbers and unknowns must survive translation into a conversational view."""

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.assistant.schemas import AnalyzeInput
from app.modules.assistant.tools import analyze


@pytest.fixture
def context() -> dict[str, Any]:
    return {
        "version": "test-v1",
        "tender": {"title": "Network switches"},
        "profile": {"annual_turnover": 12345.67, "turnover_currency": "BDT"},
        "sources": [],
        "match": {
            "similarity": 0.796,
            "recommendation": "hold",
            "score_breakdown": {
                "top_facets": [{"label": "Networks", "score": 0.82}],
                "calculation": {
                    "top_scores": [0.82, 0.76, 0.70],
                    "best_score": 0.82,
                    "max_weight": 0.6,
                    "mean_weight": 0.4,
                    "top_n": 3,
                    "thresholds": {"S": 0.78, "A": 0.7, "B": 0.62},
                },
            },
            "rule_results": [
                {
                    "rule_id": "turnover",
                    "label": "Turnover",
                    "status": "unknown",
                    "reason": "Requirement not stated",
                    "tender_value": None,
                    "expected": "BDT 100000",
                    "source": "extraction",
                }
            ],
        },
    }


def test_exact_calculation_uses_stored_operands(context: dict[str, Any]) -> None:
    result = analyze(context, AnalyzeInput(kind="calculation"))
    assert "0.79600000" in result.formulas[-1]
    assert result.rows[1].value == pytest.approx(0.76)
    assert result.rows[-1].value == 0.796
    assert "not a win probability" in result.assumptions[-1]


def test_old_assessment_does_not_invent_formula(context: dict[str, Any]) -> None:
    del context["match"]["score_breakdown"]["calculation"]
    result = analyze(context, AnalyzeInput(kind="calculation"))
    assert not result.formulas
    assert "cannot reproduce" in result.description


def test_unknown_requirement_remains_unknown(context: dict[str, Any]) -> None:
    result = analyze(context, AnalyzeInput(kind="eligibility"))
    assert result.rows[0].status == "unknown"
    assert "unknown" in result.rows[0].detail
    assert "hold" in result.description


def test_scenario_uses_decimal_arithmetic_without_mutation(context: dict[str, Any]) -> None:
    result = analyze(context, AnalyzeInput(kind="scenario", adjustment_percent=15))
    assert result.rows[0].value == 14197.52
    assert result.rows[0].baseline == 12345.67
    assert context["profile"]["annual_turnover"] == 12345.67
    assert result.unit == "BDT"


def test_missing_turnover_is_not_zero(context: dict[str, Any]) -> None:
    context["profile"]["annual_turnover"] = None
    assert not analyze(context, AnalyzeInput(kind="scenario")).rows


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -101, 501])
def test_invalid_scenarios_are_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        AnalyzeInput(kind="scenario", adjustment_percent=value)


@pytest.mark.asyncio
async def test_reserve_is_disabled_by_a_zero_limit(monkeypatch) -> None:
    """A zero limit must not touch Redis at all, let alone raise.

    The daily budgets are this application's own guard rails, not the provider's
    quota, so a deployment on a paid key with its own billing controls has to be
    able to turn them off.
    """
    from app.modules.assistant import service

    async def explode() -> None:  # pragma: no cover - must never run
        raise AssertionError("reserve consulted Redis despite a disabled limit")

    monkeypatch.setattr(service, "get_queue", explode)
    await service.reserve(uuid4(), "voice seconds", 600, 0)


def test_the_assistant_is_told_to_refuse_form_filling_out_loud() -> None:
    """Read-only is a deliberate design, silence about it is not.

    Asked to put values into the capability profile, the assistant has no tool
    that could and never had one — but the prompt only stated that as a fact
    about the world, not as an instruction about what to say. The observed
    result was a field that stayed empty with nothing on screen admitting why.
    """
    from app.modules.assistant.provider import SYSTEM, instruction

    assert "cannot fill in, save, or edit any form field" in SYSTEM
    # Not merely a refusal: the reply has to leave the person something to use.
    assert "write out" in SYSTEM
    assert "open_in_app" in SYSTEM

    built = instruction({"version": "v1"}, "en", page="/app/settings/profile")
    assert "cannot fill in, save, or edit any form field" in built
