"""Deterministic analysis. Models choose a view, never invent its numeric data."""

from decimal import Decimal
from typing import Any

from app.core.time import utcnow
from app.modules.assistant.schemas import AnalysisRow, AnalyzeInput, Artifact, Source


def analyze(context: dict[str, Any], args: AnalyzeInput, *, version: int = 1) -> Artifact:
    match = context.get("match") or {}
    tender = context["tender"]
    profile = context["profile"]
    breakdown = match.get("score_breakdown", {})
    rules = match.get("rule_results", [])
    sources = [Source.model_validate(s) for s in context["sources"]]
    result = Artifact(
        id=args.kind,
        version=version,
        kind=args.kind,
        title="Tender analysis",
        description="Based on the available tender and company assessment.",
        context_version=context["version"],
        created_at=utcnow(),
        sources=sources,
    )
    if context.get("profile_changed"):
        result.assumptions.append(
            "Your profile has changed since this assessment. Recorded scores "
            "use the earlier profile."
        )
    if args.kind == "capabilities":
        result.title = "Where your capabilities align"
        result.description = (
            "Recorded semantic similarity by capability. Similarity is not a "
            "probability of winning."
        )
        result.unit = "similarity"
        result.rows = [
            AnalysisRow(
                label=f["label"],
                value=f["score"],
                detail=f.get("chunk_kind", ""),
                source_id="assessment",
            )
            for f in breakdown.get("top_facets", [])
        ]
        result.assumptions.append(
            "The assessment stores only its strongest capability scores; this "
            "is not an exhaustive capability audit."
        )
    elif args.kind == "eligibility":
        result.title = "The logic behind your recommendation"
        result.description = (
            f"Recorded recommendation: {match.get('recommendation', 'not assessed')}. "
            "Hard failures and unresolved requirements are evaluated separately from similarity."
        )
        result.rows = [
            AnalysisRow(
                label=r["label"],
                status=r["status"],
                detail=(
                    f"Tender: {r.get('tender_value') or 'unknown'} · "
                    f"Expected: {r.get('expected') or 'unknown'}. {r['reason']} "
                    f"(source: {r.get('source') or 'assessment'})"
                ),
                source_id=f"rule:{r['rule_id']}",
            )
            for r in rules
        ]
        result.formulas = [
            "Hard failure → Ineligible",
            "Otherwise, unresolved hard requirement → Needs verification",
            "Otherwise → Eligible under the configured rules",
            "Grade + eligibility + deadline → Recommendation",
        ]
    elif args.kind == "calculation":
        result.title = "How the match score was calculated"
        result.unit = "similarity"
        provenance = breakdown.get("calculation")
        if provenance:
            operands = provenance["top_scores"]
            best = provenance["best_score"]
            mean = sum(operands) / len(operands)
            result.rows = [
                AnalysisRow(label="Best capability", value=best),
                AnalysisRow(label="Mean of top capabilities", value=mean),
                AnalysisRow(label="Recorded similarity", value=match["similarity"]),
            ]
            result.formulas = [
                f"s = clamp({provenance['max_weight']} * best + "
                f"{provenance['mean_weight']} * mean(top {provenance['top_n']}), -1, 1)",
                f"s = clamp({provenance['max_weight']} * {best:.8f} + "
                f"{provenance['mean_weight']} * {mean:.8f}, -1, 1) "
                f"= {match['similarity']:.8f}",
            ]
            result.assumptions.append(f"Recorded grade thresholds: {provenance['thresholds']}")
        else:
            result.description = (
                "Exact historical formula inputs were not stored for this "
                "assessment. We can show the recorded result, but cannot reproduce"
                " its calculation exactly."
            )
            if match:
                result.rows = [
                    AnalysisRow(
                        label="Recorded similarity",
                        value=match["similarity"],
                        source_id="assessment",
                    )
                ]
        result.assumptions.append(
            "A similarity score is not a win probability. Eligibility is checked independently."
        )
    elif args.kind == "checklist":
        result.title = "Your bid preparation checklist"
        result.description = (
            "A working draft. Verify requirements against the official notice before relying on it."
        )
        result.rows = [
            AnalysisRow(
                label=r["label"],
                detail=r["reason"],
                status=r["status"],
                source_id=f"rule:{r['rule_id']}",
            )
            for r in rules
            if r["status"] != "pass"
        ]
        result.rows += [
            AnalysisRow(
                label="Review the official tender documents",
                detail="Suggested preparation task",
                source_id="tender",
            ),
            AnalysisRow(
                label="Confirm submission deadline and delivery method",
                detail=f"Recorded deadline: {tender.get('deadline_at') or 'not available'}",
                source_id="tender",
            ),
        ]
    elif args.kind == "timeline":
        result.title = "Tender timeline"
        result.description = (
            "Only dates present in the notice are shown. Preparation "
            "milestones have not been assumed."
        )
        result.rows = [
            AnalysisRow(label=label, detail=tender[key], source_id="tender")
            for key, label in (
                ("published_at", "Published"),
                ("deadline_at", "Submission deadline"),
            )
            if tender.get(key)
        ]
    elif args.kind == "scenario":
        result.title = "Turnover scenario"
        result.description = (
            "A hypothetical change to company turnover. This does not update "
            "your profile or official eligibility."
        )
        turnover = profile.get("annual_turnover")
        result.unit = profile.get("turnover_currency") or ""
        if turnover is not None:
            base = Decimal(str(turnover))
            pct = Decimal(str(args.adjustment_percent))
            adjusted = (base * (1 + pct / 100)).quantize(Decimal("0.01"))
            result.rows = [
                AnalysisRow(
                    label="Company turnover",
                    baseline=float(base),
                    value=float(adjusted),
                    source_id="profile",
                )
            ]
            result.formulas = [f"{base} * (1 + {pct} / 100) = {adjusted} {result.unit}"]
            result.assumptions = [
                f"User-supplied hypothetical turnover change: {pct}%",
                "No currency conversion or joint-venture eligibility is inferred.",
            ]
        else:
            result.assumptions.append(
                "Annual turnover is missing from your company profile. Add it in "
                "Settings to calculate a scenario."
            )
    if not result.rows:
        result.assumptions.append(
            "The available assessment does not contain enough data for this view."
        )
    return result
