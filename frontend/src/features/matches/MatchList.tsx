import { Link } from "@tanstack/react-router"
import { InboxIcon } from "lucide-react"

import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import type { Match } from "@/features/matches/api"
import { EligibilityBadge, RecommendationBadge } from "@/features/matches/verdict"
import { Deadline } from "@/features/tenders/Deadline"
import { GradeBadge } from "@/features/tenders/GradeBadge"
import { categoryLabel, formatValue } from "@/features/tenders/format"

/**
 * A triage row.
 *
 * Two things it gets wrong if you are not careful. The match score is the one
 * number the whole product exists to produce, so it is the row's second-
 * strongest element — not, as it was, the smallest type on the line. And on a
 * phone a single-line row truncates the title to about twenty characters, which
 * makes consecutive notices indistinguishable; below `sm` the row stacks
 * instead, title wrapping to two lines with the verdict cluster beneath it.
 */
export function MatchList({
  matches,
  isLoading,
  emptyTitle = "No matches yet",
  emptyDescription = "Once your profile is set up, graded tenders appear here.",
}: {
  matches: Match[]
  isLoading?: boolean
  emptyTitle?: string
  emptyDescription?: string
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 border-t py-4">
            <Skeleton className="size-5 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    )
  }

  if (matches.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <InboxIcon />
          </EmptyMedia>
          <EmptyTitle>{emptyTitle}</EmptyTitle>
          <EmptyDescription>{emptyDescription}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <ul className="flex flex-col">
      {matches.map((match) => {
        const value = formatValue(
          match.tender.estimated_value,
          match.tender.currency
        )
        const meta = [
          match.tender.procuring_entity,
          categoryLabel(match.tender.procurement_category),
          value !== "—" ? value : null,
        ]
          .filter(Boolean)
          .join(" · ")

        return (
          <li key={match.id} className="border-t first:border-t-0">
            <Link
              to="/app/tenders/$tenderId"
              params={{ tenderId: match.tender_id }}
              className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 gap-y-2 rounded-lg px-2 py-3.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring sm:grid-cols-[1.75rem_minmax(0,1fr)_auto] sm:gap-y-1"
            >
              <GradeBadge
                grade={match.grade}
                className="mt-0.5 w-7 justify-center"
              />

              <div className="min-w-0">
                <p className="text-sm font-medium sm:truncate">
                  {match.tender.title}
                </p>
                <p className="mt-1 text-xs text-muted-foreground sm:truncate">
                  {meta || "—"}
                </p>
              </div>

              {/* Full width under the title on a phone, right-aligned column on
                  a desktop — the same four facts either way. */}
              <div className="col-start-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:col-start-3 sm:flex-col sm:items-end sm:gap-1.5">
                <Deadline
                  days={match.tender.days_to_deadline}
                  deadlineAt={match.tender.deadline_at}
                  muteNormal
                  className="text-xs sm:order-none"
                />
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-semibold tabular-nums">
                    {Math.round(match.similarity * 100)}%
                  </span>
                  <EligibilityBadge status={match.eligibility_status} />
                  <RecommendationBadge value={match.recommendation} />
                </div>
              </div>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
