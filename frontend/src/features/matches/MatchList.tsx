import { Link } from "@tanstack/react-router"
import { InboxIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Item, ItemContent, ItemGroup } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { DeadlineBadge } from "@/features/tenders/DeadlineBadge"
import type { Match } from "@/features/matches/api"
import { explanationOf } from "@/features/matches/explanation"
import { VerdictStrip } from "@/features/matches/verdict"
import { categoryLabel, formatValue } from "@/features/tenders/format"

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
      <div className="flex flex-col gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
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
    <ItemGroup className="gap-2">
      {matches.map((match) => {
        const explanation = explanationOf(match)
        return (
          <Item
            key={match.id}
            variant="outline"
            render={
              <Link
                to="/app/tenders/$tenderId"
                params={{ tenderId: match.tender_id }}
              />
            }
          >
            <ItemContent className="gap-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <span className="font-medium">{match.tender.title}</span>
                <DeadlineBadge
                  days={match.tender.days_to_deadline}
                  deadlineAt={match.tender.deadline_at}
                />
              </div>

              <VerdictStrip match={match} showScore />

              {explanation.summary ? (
                <p className="text-sm text-muted-foreground">
                  {explanation.summary}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline">{match.tender.source_code}</Badge>
                <span>{match.tender.procuring_entity ?? "—"}</span>
                <span>{categoryLabel(match.tender.procurement_category)}</span>
                <span>
                  {formatValue(
                    match.tender.estimated_value,
                    match.tender.currency
                  )}
                </span>
              </div>
            </ItemContent>
          </Item>
        )
      })}
    </ItemGroup>
  )
}
