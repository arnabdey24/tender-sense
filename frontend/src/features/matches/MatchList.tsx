import { Link } from "@tanstack/react-router"
import { ChevronDownIcon } from "lucide-react"
import * as React from "react"

import { EmptySignal } from "@/components/brand/EmptySignal"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Meter } from "@/components/ui/meter"
import { Skeleton } from "@/components/ui/skeleton"
import type { Match } from "@/features/matches/api"
import { explanationOf } from "@/features/matches/explanation"
import {
  EligibilityBadge,
  RecommendationBadge,
} from "@/features/matches/verdict"
import { useRecordDecision } from "@/features/decisions/api"
import { Deadline } from "@/features/tenders/Deadline"
import { GradeBadge } from "@/features/tenders/GradeBadge"
import { categoryLabel, formatValue } from "@/features/tenders/format"
import { cn } from "@/lib/utils"

const RAIL_BY_GRADE = {
  S: "bg-grade-s",
  A: "bg-grade-a",
  B: "bg-grade-b",
  C: "bg-grade-c",
} as const

/**
 * A triage row.
 *
 * The change that matters here is subtractive. Every row carried an
 * "Eligible" pill and a "Skip" pill, so on a feed where all 23 matches were
 * eligible the badges rendered 23 times and distinguished nothing — the design
 * was giving a constant column the same weight as a varying one. A verdict is
 * now shown only when it is *not* the common case: eligibility appears when
 * something needs checking or fails, and the recommendation appears only when
 * it says bid. Silence means "nothing to flag", which is the reading a
 * scanner wants.
 *
 * What is left is ranked: the score is the row's second-strongest element
 * after the title, because it is the one number the product exists to
 * produce, and the grade rail lets the eye group runs of the same grade
 * without reading a letter on every line.
 */
/**
 * Why a shortlist is empty, in one sentence, in one place.
 *
 * Today and the dashboard's "new today" segment describe the same morning, and
 * had drifted into two different explanations of it — one of which promised
 * that matches would arrive on their own, which on a pool nobody has pulled is
 * a promise nothing will keep.
 */
export const NOTHING_NEW_DESCRIPTION =
  "Strong matches appear here as new notices are read and graded. An empty morning means nothing cleared the bar since yesterday — or the portals have not been pulled yet."

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
      <div className="flex flex-col" aria-busy>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 border-t py-4">
            <Skeleton className="size-5 rounded-md" />
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
      <Empty size="compact">
        <EmptyHeader>
          <EmptySignal />
          <EmptyTitle>{emptyTitle}</EmptyTitle>
          <EmptyDescription>{emptyDescription}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <ul className="flex flex-col">
      {matches.map((match) => (
        <MatchRow key={match.id} match={match} />
      ))}
    </ul>
  )
}

function MatchRow({ match }: { match: Match }) {
  const [open, setOpen] = React.useState(false)
  const record = useRecordDecision(match.tender_id)
  const explanation = explanationOf(match)

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

  const reasons = (explanation.why_matched ?? []).slice(0, 3)
  const gaps = (explanation.gaps ?? []).slice(0, 3)
  const hasEvidence = Boolean(explanation.summary) || reasons.length > 0 || gaps.length > 0

  return (
    <li className="group/row relative border-t transition-colors first:border-t-0 hover:bg-row-hover has-focus-visible:bg-row-hover">
      {/* The rail lets the eye group runs of one grade without reading a
          letter on every line. The letter is still there — colour is never
          the only signal. */}
      <span
        aria-hidden
        className={cn(
          "absolute inset-y-1 left-0 w-[3px] rounded-full",
          RAIL_BY_GRADE[match.grade]
        )}
      />

      <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 gap-y-2 py-3 pl-3 pr-2 sm:grid-cols-[1.75rem_minmax(0,1fr)_auto] sm:gap-y-1">
        <GradeBadge grade={match.grade} className="mt-0.5 w-7 justify-center" />

        <div className="min-w-0">
          {/* Stretched so the whole row is the click target, while the
              controls below keep their own hit areas above it. */}
          <Link
            to="/app/tenders/$tenderId"
            params={{ tenderId: match.tender_id }}
            className="text-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:underline sm:truncate sm:block"
          >
            {match.tender.title}
          </Link>
          <p className="mt-1 text-xs text-muted-foreground sm:truncate">
            {meta || "Buyer not stated"}
          </p>
        </div>

        <div className="col-start-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:col-start-3 sm:flex-col sm:items-end sm:gap-1.5">
          <Deadline
            days={match.tender.days_to_deadline}
            deadlineAt={match.tender.deadline_at}
            muteNormal
            className="text-xs"
          />

          <div className="flex items-center gap-2">
            {/* Only when it is not the common case. */}
            {match.eligibility_status !== "eligible" ? (
              <EligibilityBadge status={match.eligibility_status} />
            ) : null}
            {match.recommendation === "bid" ? (
              <RecommendationBadge value={match.recommendation} />
            ) : null}

            <span className="flex items-center gap-1.5">
              <span className="text-sm font-semibold tabular-nums">
                {Math.round(match.similarity * 100)}%
              </span>
              <Meter value={match.similarity} grade={match.grade} />
            </span>
          </div>
        </div>

        {/*
          Row actions and the evidence disclosure sit above the stretched
          link. On a pointer device they are revealed by hover or keyboard
          focus — six identical "Why this grade" buttons down a column is the
          same noise the eligibility badge had, and the row should read as one
          notice, not as three controls. Touch devices have no hover to give,
          so there they simply stay visible.

          Opacity rather than `hidden`, so the row reserves the space either
          way and a list does not reflow under the cursor as it moves down it.
        */}
        <div className="relative z-10 col-start-2 flex items-center gap-1 transition-opacity duration-[var(--motion-fast)] group-focus-within/row:opacity-100 group-hover/row:opacity-100 sm:col-span-full sm:col-start-2 sm:-mt-1 [@media(hover:hover)]:opacity-0">
          {hasEvidence ? (
            <Button
              variant="ghost"
              size="xs"
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
              className="text-muted-foreground"
            >
              <ChevronDownIcon
                className={cn(
                  "transition-transform duration-[var(--motion-fast)]",
                  open && "rotate-180"
                )}
              />
              {open ? "Hide evidence" : "Why this grade"}
            </Button>
          ) : null}

          <span className="ml-auto flex items-center gap-1">
            <Button
              variant="ghost"
              size="xs"
              disabled={record.isPending}
              onClick={() => record.mutate({ decision: "bid" })}
            >
              Bid
            </Button>
            <Button
              variant="ghost"
              size="xs"
              disabled={record.isPending}
              onClick={() => record.mutate({ decision: "skip" })}
              className="text-muted-foreground"
            >
              Skip
            </Button>
          </span>
        </div>

        {/* The product's whole thesis is evidence beside verdict; it was one
            navigation away from every row that states a verdict. */}
        {open ? (
          <div className="relative z-10 col-start-2 mt-1 flex flex-col gap-2 rounded-lg bg-surface-sunken p-3 text-xs sm:col-span-full sm:col-start-2">
            {explanation.summary ? (
              <p className="text-pretty text-foreground">{explanation.summary}</p>
            ) : null}
            {reasons.length > 0 ? (
              <div>
                <p className="font-medium text-foreground">Why it matched</p>
                <ul className="mt-1 flex flex-col gap-0.5 text-muted-foreground">
                  {reasons.map((reason, i) => (
                    <li key={i} className="flex gap-1.5">
                      <span aria-hidden className="text-success">
                        &bull;
                      </span>
                      <span className="text-pretty">{reason}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {gaps.length > 0 ? (
              <div>
                <p className="font-medium text-foreground">Gaps</p>
                <ul className="mt-1 flex flex-col gap-0.5 text-muted-foreground">
                  {gaps.map((gap, i) => (
                    <li key={i} className="flex gap-1.5">
                      <span aria-hidden className="text-warning">
                        &bull;
                      </span>
                      <span className="text-pretty">{gap}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <Link
              to="/app/tenders/$tenderId"
              params={{ tenderId: match.tender_id }}
              className="text-primary underline underline-offset-4"
            >
              Open the full assessment
            </Link>
          </div>
        ) : null}
      </div>
    </li>
  )
}
