"""Saying why a tender matched.

Every match gets a templated explanation built from structured data — no model
call, no tokens, never absent. The language model is only asked for a narrative
where it earns its cost, and even then the templated version stays as the
fallback when the budget is spent or the call fails.

Writing this from the score breakdown rather than from the notice text is
deliberate: the explanation then cannot claim anything the scoring did not
actually use, which is what makes it safe to show beside a grade.
"""

from __future__ import annotations

from app.modules.matching.models import (
    EligibilityStatus,
    MatchGrade,
    Recommendation,
    Urgency,
)
from app.modules.matching.scoring import ScoreResult

#: Only these grades are worth a model call; everything else stays templated.
LLM_WORTHY_GRADES = frozenset({MatchGrade.S, MatchGrade.A, MatchGrade.B})

_GRADE_PHRASES = {
    MatchGrade.S: "a very strong fit",
    MatchGrade.A: "a strong fit",
    MatchGrade.B: "a partial fit",
    MatchGrade.C: "a weak fit",
}

_ELIGIBILITY_PHRASES = {
    EligibilityStatus.ELIGIBLE: "You meet every eligibility rule that could be checked.",
    EligibilityStatus.NEEDS_VERIFICATION: (
        "Some requirements could not be confirmed from the notice and need a human check."
    ),
    EligibilityStatus.INELIGIBLE: "At least one hard requirement is not met.",
}

_URGENCY_PHRASES = {
    Urgency.EXPIRED: "The deadline has passed.",
    Urgency.CRITICAL: "The deadline is within three days.",
    Urgency.HIGH: "The deadline is within a week.",
    Urgency.NORMAL: "There is still time to prepare.",
    Urgency.LOW: "The deadline is comfortably far off.",
    Urgency.UNKNOWN: "The notice gives no closing date.",
}

_NEXT_STEPS = {
    Recommendation.BID: "Open the notice and start a bid.",
    Recommendation.HOLD: "Check the flagged requirements before committing.",
    Recommendation.SKIP: "No action needed.",
}


def should_use_llm(grade: MatchGrade, eligibility: EligibilityStatus, urgency: Urgency) -> bool:
    """Whether a match is worth spending tokens explaining.

    A C-grade or expired tender is never worth it; a B only when the company is
    actually eligible, because an ineligible partial fit is not a decision
    anyone needs prose about.
    """
    if urgency is Urgency.EXPIRED:
        return False
    if grade is MatchGrade.C:
        return False
    if grade is MatchGrade.B:
        return eligibility is EligibilityStatus.ELIGIBLE
    return True


def templated_explanation(
    *,
    grade: MatchGrade,
    eligibility: EligibilityStatus,
    urgency: Urgency,
    recommendation: Recommendation,
    score: ScoreResult,
    rule_results: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Build the structured explanation shown on every match.

    Shares its shape with the model-written version, so the UI renders both
    identically and a fallback is invisible to the reader.
    """
    results = rule_results or []

    why_matched = [
        f"{facet.label} closely matches this notice."
        for facet in sorted(score.facets, key=lambda f: f.score, reverse=True)[:3]
        if facet.score > 0
    ]

    gaps = [
        str(result.get("reason") or result.get("label") or "")
        for result in results
        if result.get("status") == "fail"
    ]
    risks = [
        str(result.get("reason") or result.get("label") or "")
        for result in results
        if result.get("status") in {"unknown", "warn"}
    ]

    summary = (
        f"Graded {grade.value} — {_GRADE_PHRASES[grade]}. " + _ELIGIBILITY_PHRASES[eligibility]
    )

    return {
        "summary": summary,
        "why_matched": why_matched,
        "gaps": [gap for gap in gaps if gap],
        "risks": [risk for risk in risks if risk] + [_URGENCY_PHRASES[urgency]],
        "next_step": _NEXT_STEPS[recommendation],
    }


def explanation_to_text(explanation: dict[str, object]) -> str:
    """Flatten the structured form into plain text for email and search."""
    lines: list[str] = [str(explanation.get("summary", ""))]

    for key, heading in (
        ("why_matched", "Why it matches"),
        ("gaps", "Gaps"),
        ("risks", "Worth checking"),
    ):
        items = explanation.get(key) or []
        if isinstance(items, list) and items:
            lines.append(f"\n{heading}:")
            lines.extend(f"- {item}" for item in items)

    next_step = explanation.get("next_step")
    if next_step:
        lines.append(f"\nNext: {next_step}")

    return "\n".join(line for line in lines if line).strip()
