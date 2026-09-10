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
import { GradeBadge } from "@/features/tenders/GradeBadge"
import {
  categoryLabel,
  deadlineInfo,
  formatValue,
  type DeadlineTone,
} from "@/features/tenders/format"
import { cn } from "@/lib/utils"

/**
 * Time pressure is the thing a bid manager scans for, so it is text with its
 * own weight rather than another pill in a row of pills. Colour is never the
 * only signal — the label always says what it means.
 */
const DEADLINE_TONE: Record<DeadlineTone, string> = {
  expired: "text-muted-foreground",
  critical: "text-destructive",
  high: "text-warning",
  normal: "text-muted-foreground",
  none: "text-muted-foreground",
}

/**
 * A triage list, not a stack of cards.
 *
 * Twenty-three outlined cards, each repeating the same generated sentence, is
 * noise a reader has to work through rather than scan. One hairline-separated
 * row per match puts the grade, the title, the verdict and the deadline on
 * fixed reading lines, and leaves the explanation for the detail page where it
 * differs from row to row.
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
          <div key={i} className="flex items-center gap-3 border-t py-3.5">
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
        const deadline = deadlineInfo(
          match.tender.days_to_deadline,
          match.tender.deadline_at
        )
        const meta = [
          match.tender.procuring_entity,
          categoryLabel(match.tender.procurement_category),
          formatValue(match.tender.estimated_value, match.tender.currency),
        ]
          .filter((part) => part && part !== "—")
          .join(" · ")

        return (
          <li key={match.id} className="border-t first:border-t-0">
            <Link
              to="/app/tenders/$tenderId"
              params={{ tenderId: match.tender_id }}
              className="grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-start gap-x-3 rounded-lg px-2 py-3.5 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
            >
              <GradeBadge grade={match.grade} className="mt-0.5 w-7 justify-center" />

              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {match.tender.title}
                </p>
                <p className="mt-1 truncate text-xs text-muted-foreground">
                  {meta || "—"}
                </p>
              </div>

              <div className="flex flex-col items-end gap-1.5">
                <span
                  className={cn(
                    "text-xs font-medium tabular-nums",
                    DEADLINE_TONE[deadline.tone]
                  )}
                >
                  {deadline.label}
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground tabular-nums">
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
