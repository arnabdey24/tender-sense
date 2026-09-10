"""The explanation prompt.

The model is given the *conclusions* — the grade, the eligibility verdict, which
facets matched, which rules failed — and asked to phrase them. It is not given
the raw notice and asked to judge, because then the prose could disagree with
the grade sitting next to it, and a customer reading a confident paragraph that
contradicts the badge above it will trust neither again.
"""

from __future__ import annotations

from typing import Any

SYSTEM_INSTRUCTION = """\
You explain, in plain English, why a procurement tender does or does not suit a
company. You are given the conclusions of an automated assessment. Your job is
to phrase them, not to reach your own.

Rules you must follow:
- Never contradict the grade or the eligibility verdict you are given.
- Never invent a requirement, a certification or a number that is not in the
  input. If a fact is not given, do not mention it.
- "Needs verification" means the system could not determine something, not that
  the company failed it. Say what needs checking, not that they fall short.
- Be specific about what matched. "Strong alignment" is worthless; "your
  network integration service matches the switching and cabling scope" is not.
- Two or three sentences of summary. Keep every list to at most three items.
- Write to the bidder as "you".
"""


def build_prompt(
    *,
    title: str,
    procuring_entity: str | None,
    deadline: str | None,
    grade: str,
    similarity: float,
    eligibility: str,
    recommendation: str,
    matched_facets: list[dict[str, Any]],
    rule_results: list[dict[str, Any]],
    profile_overview: str | None,
) -> str:
    """Assemble the user-side prompt for one match."""
    lines = [
        "Explain this assessment to the bidder.",
        "",
        f"Tender: {title}",
    ]
    if procuring_entity:
        lines.append(f"Buyer: {procuring_entity}")
    if deadline:
        lines.append(f"Deadline: {deadline}")

    lines += [
        "",
        f"Assessment: grade {grade} ({similarity:.0%} similarity), "
        f"eligibility {eligibility}, recommendation {recommendation}.",
    ]

    if profile_overview:
        lines += ["", f"The company describes itself as: {profile_overview}"]

    if matched_facets:
        lines += ["", "What matched, strongest first:"]
        lines += [
            f"- {facet.get('label')} ({float(facet.get('score', 0)):.0%})"
            for facet in matched_facets[:5]
        ]

    failing = [r for r in rule_results if r.get("status") == "fail"]
    unresolved = [r for r in rule_results if r.get("status") in {"unknown", "warn"}]
    passing = [r for r in rule_results if r.get("status") == "pass"]

    if failing:
        lines += ["", "Requirements NOT met:"]
        lines += [f"- {r.get('label')}: {r.get('reason')}" for r in failing]
    if unresolved:
        lines += ["", "Could not be determined (needs a human to check):"]
        lines += [f"- {r.get('label')}: {r.get('reason')}" for r in unresolved]
    if passing:
        lines += ["", "Requirements met:"]
        lines += [f"- {r.get('label')}" for r in passing[:5]]

    return "\n".join(lines)
