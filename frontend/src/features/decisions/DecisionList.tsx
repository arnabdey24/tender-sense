import { Link } from "@tanstack/react-router"

import { EmptySignal } from "@/components/brand/EmptySignal"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Meter } from "@/components/ui/meter"
import { Skeleton } from "@/components/ui/skeleton"
import type { DecisionWithTender } from "@/features/decisions/api"
import { EligibilityBadge } from "@/features/matches/verdict"
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
 * A row on the pipeline: one notice this company has committed to.
 *
 * Close to a match row and deliberately not the same component. A match row
 * exists to *produce* a decision, so it carries Bid and Skip buttons and
 * leads with the score. These rows are the decisions already taken: the
 * buttons would be asking a question that has been answered, and the thing
 * worth reading is the note somebody left explaining why.
 *
 * The grade is optional here in a way it never is on a match row. A decision
 * hangs off a tender, and a tender can be decided on before this organization
 * has scored anything at all.
 */
function DecisionRow({ entry }: { entry: DecisionWithTender }) {
  const value = formatValue(entry.tender.estimated_value, entry.tender.currency)
  const meta = [
    entry.tender.procuring_entity,
    categoryLabel(entry.tender.procurement_category),
    value !== "—" ? value : null,
  ]
    .filter(Boolean)
    .join(" · ")

  return (
    <li className="group/row relative border-t transition-colors first:border-t-0 hover:bg-row-hover has-focus-visible:bg-row-hover">
      {entry.verdict ? (
        <span
          aria-hidden
          className={cn(
            "absolute inset-y-1 left-0 w-[3px] rounded-full",
            RAIL_BY_GRADE[entry.verdict.grade]
          )}
        />
      ) : null}

      <div className="grid grid-cols-[1.75rem_minmax(0,1fr)] gap-x-3 gap-y-2 py-3 pl-3 pr-2 sm:grid-cols-[1.75rem_minmax(0,1fr)_auto] sm:gap-y-1">
        {entry.verdict ? (
          <GradeBadge
            grade={entry.verdict.grade}
            className="mt-0.5 w-7 justify-center"
          />
        ) : (
          /* Not a grade of "none" — an em dash, because the tender has not
             been scored rather than scored badly, and a C badge here would
             be a claim the system has not made. */
          <span
            className="mt-0.5 w-7 text-center text-sm text-muted-foreground"
            title="Not scored yet"
            aria-label="Not scored yet"
          >
            &mdash;
          </span>
        )}

        <div className="min-w-0">
          <Link
            to="/app/tenders/$tenderId"
            params={{ tenderId: entry.tender_id }}
            className="text-sm font-medium underline-offset-4 outline-none after:absolute after:inset-0 hover:underline focus-visible:underline sm:truncate sm:block"
          >
            {entry.tender.title}
          </Link>
          <p className="mt-1 text-xs text-muted-foreground sm:truncate">
            {meta || "Buyer not stated"}
          </p>
          {entry.note ? (
            /* The reason somebody gave is the most valuable text on this
               page, and it lived only behind a click into the notice. */
            <p className="mt-1 text-xs text-pretty text-foreground/80">
              &ldquo;{entry.note}&rdquo;
            </p>
          ) : null}
        </div>

        <div className="col-start-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 sm:col-start-3 sm:flex-col sm:items-end sm:gap-1.5">
          <Deadline
            days={entry.tender.days_to_deadline}
            deadlineAt={entry.tender.deadline_at}
            muteNormal
            className="text-xs"
          />

          <div className="flex items-center gap-2">
            {entry.verdict &&
            entry.verdict.eligibility_status !== "eligible" ? (
              <EligibilityBadge status={entry.verdict.eligibility_status} />
            ) : null}

            {entry.verdict ? (
              <span className="flex items-center gap-1.5">
                <span className="text-sm font-semibold tabular-nums">
                  {Math.round(entry.verdict.similarity * 100)}%
                </span>
                <Meter value={entry.verdict.similarity} grade={entry.verdict.grade} />
              </span>
            ) : (
              <span className="relative z-10 text-xs text-muted-foreground">
                Not scored —{" "}
                <Link
                  to="/app/settings/profile"
                  className="underline underline-offset-4 hover:text-foreground"
                >
                  finish your profile
                </Link>
              </span>
            )}
          </div>
        </div>
      </div>
    </li>
  )
}

export function DecisionList({
  entries,
  isLoading,
  emptyTitle = "Nothing decided yet",
  emptyDescription = "Mark a tender as a bid or a hold and it collects here.",
  groups,
}: {
  entries: DecisionWithTender[]
  isLoading?: boolean
  emptyTitle?: string
  emptyDescription?: string
  groups?: {
    key: string
    label: string
    match: (entry: DecisionWithTender) => boolean
  }[]
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col" aria-busy>
        {Array.from({ length: 4 }).map((_, i) => (
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

  if (entries.length === 0) {
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

  if (groups?.length) {
    const runs = groups
      .map((group) => ({ ...group, rows: entries.filter(group.match) }))
      .filter((group) => group.rows.length > 0)

    return (
      <div className="flex flex-col gap-6">
        {runs.map((group) => (
          <section key={group.key}>
            <h3 className="flex items-baseline gap-2 pb-1 text-sm font-medium">
              {group.label}
              <span className="text-xs text-muted-foreground tabular-nums">
                {group.rows.length}
              </span>
            </h3>
            <ul className="flex flex-col">
              {group.rows.map((entry) => (
                <DecisionRow key={entry.id} entry={entry} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    )
  }

  return (
    <ul className="flex flex-col">
      {entries.map((entry) => (
        <DecisionRow key={entry.id} entry={entry} />
      ))}
    </ul>
  )
}
