import { Badge } from "@/components/ui/badge"
import { GradeBadge } from "@/features/tenders/GradeBadge"
import type {
  EligibilityStatus,
  Match,
  Recommendation,
} from "@/features/matches/api"

type BadgeVariant = React.ComponentProps<typeof Badge>["variant"]

const ELIGIBILITY: Record<
  EligibilityStatus,
  { label: string; variant: BadgeVariant }
> = {
  eligible: { label: "Eligible", variant: "success" },
  // Never "ineligible": an unverifiable requirement is a question for a human,
  // not a rejection, and the wording has to say so.
  needs_verification: { label: "Needs checking", variant: "warning" },
  ineligible: { label: "Not eligible", variant: "destructive" },
}

const RECOMMENDATION: Record<
  Recommendation,
  { label: string; variant: BadgeVariant }
> = {
  bid: { label: "Bid", variant: "success" },
  hold: { label: "Hold", variant: "warning" },
  skip: { label: "Skip", variant: "outline" },
}

export function EligibilityBadge({ status }: { status: EligibilityStatus }) {
  const entry = ELIGIBILITY[status]
  return <Badge variant={entry.variant}>{entry.label}</Badge>
}

export function RecommendationBadge({ value }: { value: Recommendation }) {
  const entry = RECOMMENDATION[value]
  return <Badge variant={entry.variant}>{entry.label}</Badge>
}

/** Grade, eligibility and recommendation as one line — the whole verdict. */
export function VerdictStrip({
  match,
  showScore = false,
}: {
  match: Pick<
    Match,
    "grade" | "eligibility_status" | "recommendation" | "similarity"
  >
  showScore?: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <GradeBadge grade={match.grade} />
      <EligibilityBadge status={match.eligibility_status} />
      <RecommendationBadge value={match.recommendation} />
      {showScore ? (
        <span className="text-xs text-muted-foreground">
          {Math.round(match.similarity * 100)}% match
        </span>
      ) : null}
    </div>
  )
}
