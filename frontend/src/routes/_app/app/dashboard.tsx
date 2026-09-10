import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRightIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import {
  useMatches,
  useMatchStats,
  useTodayShortlist,
} from "@/features/matches/api"
import { useRecipients } from "@/features/notifications/api"
import { useCompleteness } from "@/features/profile/api"

export const Route = createFileRoute("/_app/app/dashboard")({
  component: DashboardPage,
})

/**
 * Counts belong on one line, not in four boxes.
 *
 * Four outlined tiles across the top is the arrangement every dashboard
 * reaches for, and it spends the best space on the screen — the part read
 * first — on aggregate totals, pushing the day's actual decisions below the
 * fold. These are context for the shortlist, so they read as one strip of
 * figures above it.
 */
function StatStrip({
  stats,
  isLoading,
}: {
  stats: {
    total?: number
    strong?: number
    closing?: number
    newToday?: number
  }
  isLoading?: boolean
}) {
  const items = [
    { label: "Open matches", value: stats.total, to: "/app/matches" as const },
    { label: "Strong fits", value: stats.strong, to: "/app/matches" as const },
    {
      label: "Closing in 7 days",
      value: stats.closing,
      to: "/app/matches" as const,
    },
    { label: "New today", value: stats.newToday, to: "/app/today" as const },
  ]

  // Each figure is the door into the list it counts; a number you cannot act on
  // is decoration. That makes this a set of links rather than a description
  // list, which is also the only markup where an anchor is legal here.
  return (
    <nav
      aria-label="Match totals"
      className="grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-border sm:grid-cols-4"
    >
      {items.map((item) => (
        <Link
          key={item.label}
          to={item.to}
          className="flex flex-col gap-1 bg-card px-4 py-3 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring"
        >
          <span className="text-xs text-muted-foreground">{item.label}</span>
          <span className="text-xl leading-none font-semibold tabular-nums">
            {isLoading ? <Skeleton className="h-5 w-10" /> : (item.value ?? 0)}
          </span>
        </Link>
      ))}
    </nav>
  )
}

/**
 * A company that never adds a recipient silently receives no email at all —
 * matches pile up in an app nobody has open. Said once, where it will be read.
 */
function EmailDeliveryNudge() {
  const recipients = useRecipients()
  if (recipients.isPending || recipients.error) return null
  if (
    (recipients.data ?? []).some((r) => r.verified_at && !r.unsubscribed_at)
  ) {
    return null
  }

  const awaiting = (recipients.data ?? []).some((r) => !r.verified_at)

  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <h3 className="text-sm font-medium">Nothing is being emailed yet</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">
        {awaiting
          ? "An address is waiting to be confirmed. Until someone clicks the link in it, matches only appear here in the app."
          : "Matches appear here, but nobody receives them by email. Add an address so a strong match reaches you when nobody has the app open."}
      </p>
      <Link
        to="/app/settings/notifications"
        className="mt-2 inline-block text-sm text-primary underline underline-offset-4"
      >
        Set up notifications
      </Link>
    </div>
  )
}

function ProfileNudge() {
  const completeness = useCompleteness()
  if ((completeness.data?.score ?? 100) >= 100) return null

  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <h3 className="text-sm font-medium">Finish your profile</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-pretty text-muted-foreground">
        {completeness.data?.next_step ??
          "A fuller profile means sharper matches."}
      </p>
      <Progress value={completeness.data?.score ?? 0} className="mt-3" />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(completeness.data?.sections ?? []).map((section) => (
          <Badge
            key={section.key}
            variant={section.complete ? "success" : "outline"}
          >
            {section.label}
          </Badge>
        ))}
      </div>
      <Link
        to="/app/settings/profile"
        className="mt-3 inline-block text-sm text-primary underline underline-offset-4"
      >
        Open the profile
      </Link>
    </div>
  )
}

function DashboardPage() {
  const stats = useMatchStats()
  const shortlist = useTodayShortlist({ page_size: 6 })
  const strong = (stats.data?.by_grade?.S ?? 0) + (stats.data?.by_grade?.A ?? 0)
  // "Nothing new today" is true and useless on its own while two dozen graded
  // matches sit unread. The nearest deadlines are what to do instead.
  const closing = useMatches({
    sort: "deadline_at",
    descending: false,
    open_only: true,
    page_size: 5,
  })
  const nothingNew =
    !shortlist.isPending && (shortlist.data?.items?.length ?? 0) === 0

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="What is worth your attention this morning."
      />

      <StatStrip
        isLoading={stats.isPending}
        stats={{
          total: stats.data?.total,
          strong,
          closing: stats.data?.closing_within_7_days,
          newToday: stats.data?.new_today,
        }}
      />

      {/* The shortlist is the point of the page, so it gets the width; the
          things that need setting up sit beside it, not above it. */}
      <div className="grid gap-x-10 gap-y-8 lg:grid-cols-12">
        <section className="lg:col-span-8">
          <div className="mb-3 flex items-baseline justify-between gap-3">
            <h2 className="font-heading text-base font-medium">
              Today&rsquo;s shortlist
            </h2>
            <Button
              variant="ghost"
              size="sm"
              render={<Link to="/app/today" />}
              nativeButton={false}
            >
              See everything new
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          </div>
          <ApiErrorAlert error={shortlist.error} />
          <MatchList
            matches={shortlist.data?.items ?? []}
            isLoading={shortlist.isPending}
            emptyTitle="Nothing new today"
            emptyDescription="Strong matches will appear here as tenders arrive."
          />
          {nothingNew && (closing.data?.items?.length ?? 0) > 0 ? (
            <div className="mt-8">
              <div className="mb-3 flex items-baseline justify-between gap-3">
                <h2 className="font-heading text-base font-medium">
                  Closing soonest
                </h2>
                <Button
                  variant="ghost"
                  size="sm"
                  render={<Link to="/app/matches" />}
                  nativeButton={false}
                >
                  All matches
                  <ArrowRightIcon data-icon="inline-end" />
                </Button>
              </div>
              <MatchList
                matches={closing.data?.items ?? []}
                isLoading={closing.isPending}
              />
            </div>
          ) : null}
        </section>

        <aside className="flex flex-col gap-4 lg:col-span-4">
          <ProfileNudge />
          <EmailDeliveryNudge />
        </aside>
      </div>
    </>
  )
}
