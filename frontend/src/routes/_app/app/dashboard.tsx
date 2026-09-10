import { createFileRoute, Link } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import { useMatchStats, useTodayShortlist } from "@/features/matches/api"
import { useRecipients } from "@/features/notifications/api"
import { useCompleteness } from "@/features/profile/api"

export const Route = createFileRoute("/_app/app/dashboard")({
  component: DashboardPage,
})

function Stat({
  label,
  value,
  isLoading,
}: {
  label: string
  value: number | undefined
  isLoading?: boolean
}) {
  // Stacked one-per-row on a phone, four tiles at full desktop spacing pushed
  // the day's shortlist most of a screen down. Below `sm` the label and value
  // sit as one tight group instead.
  return (
    <Card className="gap-1 [--card-spacing:--spacing(3)] sm:gap-4 sm:[--card-spacing:--spacing(4)]">
      <CardHeader className="pb-0 sm:pb-2">
        <CardDescription className="text-xs sm:text-sm">
          {label}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-7 w-14 sm:h-8 sm:w-16" />
        ) : (
          <span className="text-2xl font-semibold tabular-nums sm:text-3xl">
            {value ?? 0}
          </span>
        )}
      </CardContent>
    </Card>
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
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Nothing is being emailed yet
        </CardTitle>
        <CardDescription>
          {awaiting
            ? "An address is waiting to be confirmed. Until someone clicks the link in it, matches only appear here in the app."
            : "Matches appear here, but nobody receives them by email. Add an address so a strong match reaches you when nobody has the app open."}{" "}
          <Link
            to="/app/settings/notifications"
            className="underline underline-offset-4"
          >
            Set up notifications
          </Link>
        </CardDescription>
      </CardHeader>
    </Card>
  )
}

function DashboardPage() {
  const stats = useMatchStats()
  const shortlist = useTodayShortlist({ page_size: 5 })
  const completeness = useCompleteness()

  const strong = (stats.data?.by_grade?.S ?? 0) + (stats.data?.by_grade?.A ?? 0)

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your tender activity at a glance."
      />

      {/* Two-up on a phone: stacked one-per-row, four tiles pushed the day's
          shortlist off the first screen entirely. */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Stat
          label="Open matches"
          value={stats.data?.total}
          isLoading={stats.isPending}
        />
        <Stat
          label="Strong fits (S/A)"
          value={strong}
          isLoading={stats.isPending}
        />
        <Stat
          label="Closing within 7 days"
          value={stats.data?.closing_within_7_days}
          isLoading={stats.isPending}
        />
        <Stat
          label="New today"
          value={stats.data?.new_today}
          isLoading={stats.isPending}
        />
      </div>

      {(completeness.data?.score ?? 100) < 100 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Finish your profile</CardTitle>
            <CardDescription>
              {completeness.data?.next_step ??
                "A fuller profile means sharper matches."}{" "}
              <Link
                to="/app/settings/profile"
                className="underline underline-offset-4"
              >
                Open the profile
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Progress value={completeness.data?.score ?? 0} />
            <div className="flex flex-wrap gap-2">
              {(completeness.data?.sections ?? []).map((section) => (
                <Badge
                  key={section.key}
                  variant={section.complete ? "success" : "outline"}
                >
                  {section.label}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <EmailDeliveryNudge />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Today's shortlist</CardTitle>
          <CardDescription>
            <Link to="/app/today" className="underline underline-offset-4">
              See everything new
            </Link>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ApiErrorAlert error={shortlist.error} />
          <MatchList
            matches={shortlist.data?.items ?? []}
            isLoading={shortlist.isPending}
            emptyTitle="Nothing new today"
            emptyDescription="Strong matches will appear here as tenders arrive."
          />
        </CardContent>
      </Card>
    </>
  )
}
