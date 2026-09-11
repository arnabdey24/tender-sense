import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"
import * as React from "react"

import { PageHeader } from "@/components/layout/PageHeader"
import { SectionHeader } from "@/components/layout/SectionHeader"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchCharts } from "@/features/matches/MatchCharts"
import {
  MatchList,
  NOTHING_NEW_DESCRIPTION,
} from "@/features/matches/MatchList"
import {
  useMatches,
  useMatchStats,
  useTodayShortlist,
  type MatchQuery,
  type MatchStats,
} from "@/features/matches/api"
import { SetupStrip } from "@/features/profile/SetupStrip"
import { PortalSyncButton } from "@/features/sources/PortalSync"
import { useAutoSyncEmptyPool } from "@/features/sources/use-portal-sync"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_app/app/dashboard")({
  component: DashboardPage,
})

/**
 * Four outlined tiles across the top is the arrangement every dashboard
 * reaches for. It spends the part of the screen that is read first on
 * aggregate totals and pushes the day's actual decisions below the fold, and
 * on this product it was rendering "Strong fits: 0" — a number nobody can act
 * on — in the best position available.
 *
 * The counts survive, because knowing there are 23 open matches is useful.
 * What changes is that each one now *filters the list beneath it* instead of
 * navigating away, so a figure earns its space twice: it reports a total, and
 * it is the control that shows you what the total is made of.
 *
 * "Strong fits" is gone as a segment. The API filters on a single grade, so
 * S-and-A could not be one query, and on this data it would have read zero
 * every morning — the dead tile again, in a new place. "Needs checking" takes
 * the slot: it is a real query, it has a real count, and unlike a grade band
 * it names a task somebody has to do.
 */
type SegmentId = "new" | "closing" | "checking" | "open"

const SEGMENTS: {
  id: SegmentId
  label: string
  count: (s?: MatchStats) => number
  empty: { title: string; description: string }
  query?: MatchQuery
}[] = [
  {
    id: "new",
    label: "New today",
    count: (s) => s?.new_today ?? 0,
    empty: {
      title: "Nothing new today",
      description: NOTHING_NEW_DESCRIPTION,
    },
  },
  {
    id: "closing",
    label: "Closing this week",
    count: (s) => s?.closing_within_7_days ?? 0,
    query: {
      deadline_within_days: 7,
      open_only: true,
      sort: "deadline_at",
      descending: false,
      page_size: 8,
    },
    empty: {
      title: "Nothing closes this week",
      description: "The nearest deadlines are further out than seven days.",
    },
  },
  {
    id: "checking",
    label: "Needs checking",
    count: (s) => s?.by_eligibility?.needs_verification ?? 0,
    query: { eligibility: "needs_verification", open_only: true, page_size: 8 },
    empty: {
      title: "Nothing is waiting on a check",
      description:
        "Every open match has enough information to decide eligibility.",
    },
  },
  {
    id: "open",
    label: "All open",
    count: (s) => s?.total ?? 0,
    query: {
      open_only: true,
      sort: "similarity",
      descending: true,
      page_size: 8,
    },
    empty: {
      title: "No open matches",
      description: "Once tenders are graded against your profile they land here.",
    },
  },
]

function TriageTabs({
  active,
  onChange,
  stats,
  isLoading,
}: {
  active: SegmentId
  onChange: (id: SegmentId) => void
  stats?: MatchStats
  isLoading?: boolean
}) {
  return (
    <div
      role="tablist"
      aria-label="Match queues"
      className="flex w-full gap-1 overflow-x-auto rounded-xl bg-surface-sunken p-1"
    >
      {SEGMENTS.map((segment) => {
        const selected = segment.id === active
        return (
          <button
            key={segment.id}
            role="tab"
            type="button"
            aria-selected={selected}
            onClick={() => onChange(segment.id)}
            className={cn(
              "flex min-w-0 flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm whitespace-nowrap transition-colors duration-[var(--motion-fast)] outline-none",
              "focus-visible:ring-3 focus-visible:ring-ring/50",
              selected
                ? "bg-card font-medium text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <span className="truncate">{segment.label}</span>
            {isLoading ? (
              <Skeleton className="h-4 w-5" />
            ) : (
              <span
                className={cn(
                  "text-sm tabular-nums",
                  // A count is a status, and status takes ink, not brand.
                  selected ? "font-semibold" : "text-muted-foreground"
                )}
              >
                {segment.count(stats)}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

function DashboardPage() {
  const [active, setActive] = React.useState<SegmentId>("new")
  const segment = SEGMENTS.find((s) => s.id === active) ?? SEGMENTS[0]

  // A deployment nobody has filled shows a new organization a dashboard with
  // nothing on it, and the one thing that would fix it is the thing they have
  // no reason to know about. So it starts itself — once per tab, only when the
  // shared pool is genuinely empty, and never while a pull is already running.
  useAutoSyncEmptyPool()

  const stats = useMatchStats()
  const shortlist = useTodayShortlist({ page_size: 8 })
  // The list endpoint serves every segment but "new today", which has its own
  // route. Both are cached, so switching tabs is instant after the first look.
  const listed = useMatches(segment.query ?? { page_size: 8 })

  const source = active === "new" ? shortlist : listed
  const items = source.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="What needs a decision this morning."
        actions={<PortalSyncButton size="default" variant="outline" />}
      />

      <SetupStrip />

      <section className="flex flex-col gap-3">
        <TriageTabs
          active={active}
          onChange={setActive}
          stats={stats.data}
          isLoading={stats.isPending}
        />

        <ApiErrorAlert error={source.error} />

        <MatchList
          matches={items}
          isLoading={source.isPending}
          emptyTitle={segment.empty.title}
          emptyDescription={segment.empty.description}
        />

        {items.length > 0 ? (
          <div className="flex justify-end border-t pt-3">
            <Button
              variant="ghost"
              size="sm"
              render={<Link to={active === "new" ? "/app/today" : "/app/matches"} />}
              nativeButton={false}
            >
              {active === "new" ? "See everything new" : "Open all matches"}
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          </div>
        ) : null}
      </section>

      {/* Below the queue on purpose: these describe the pool, they are not
          the day's decisions. */}
      <section>
        <SectionHeader title="How the pool looks" />
        <MatchCharts stats={stats.data} isLoading={stats.isPending} />
      </section>
    </>
  )
}
