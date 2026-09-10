import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  HelpCircleIcon,
  XCircleIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { RuleStatus } from "@/features/rules/api"

type Status = "pass" | "fail" | "unknown" | "warn"

const PRESENTATION: Record<
  Status,
  { icon: typeof CheckCircle2Icon; className: string; label: string }
> = {
  pass: { icon: CheckCircle2Icon, className: "text-success", label: "Met" },
  fail: { icon: XCircleIcon, className: "text-destructive", label: "Not met" },
  // Never "failed": the engine could not determine this, which is a question
  // for a person rather than a rejection.
  unknown: {
    icon: HelpCircleIcon,
    className: "text-warning-foreground",
    label: "Needs checking",
  },
  warn: {
    icon: AlertTriangleIcon,
    className: "text-warning-foreground",
    label: "Worth a look",
  },
}

/** The order a reader cares about: blockers, then questions, then what passed. */
const ORDER: Record<Status, number> = { fail: 0, unknown: 1, warn: 2, pass: 3 }

export function EligibilityList({ results }: { results: RuleStatus[] }) {
  if (results.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No bidding criteria set, so nothing was checked.
      </p>
    )
  }

  const sorted = [...results].sort(
    (a, b) => ORDER[a.status as Status] - ORDER[b.status as Status]
  )

  return (
    <ul className="flex flex-col gap-3">
      {sorted.map((result) => {
        const presentation = PRESENTATION[result.status as Status]
        const Icon = presentation.icon
        return (
          <li key={result.rule_id} className="flex gap-3">
            <Icon className={`mt-0.5 size-4 shrink-0 ${presentation.className}`} />
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium">{result.label}</span>
                <Badge variant="outline">{presentation.label}</Badge>
                {result.severity === "soft" ? (
                  <Badge variant="secondary">Advisory</Badge>
                ) : null}
                {typeof result.confidence === "number" ? (
                  <span className="text-xs text-muted-foreground">
                    {Math.round(result.confidence * 100)}% confident
                  </span>
                ) : null}
              </div>
              <p className="text-sm text-muted-foreground">{result.reason}</p>
              {result.evidence ? (
                // The quote is what lets someone check the claim against the
                // notice rather than taking the model's word for it.
                <blockquote className="border-l-2 pl-3 text-xs text-muted-foreground italic">
                  “{result.evidence}”
                </blockquote>
              ) : null}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
