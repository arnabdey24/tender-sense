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
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-16" />
        ) : (
          <span className="text-3xl font-semibold tabular-nums">
            {value ?? 0}
          </span>
        )}
      </CardContent>
    </Card>
  )
}

function DashboardPage() {
  const stats = useMatchStats()
  const shortlist = useTodayShortlist({ page_size: 5 })
  const completeness = useCompleteness()

  const strong =
    (stats.data?.by_grade?.S ?? 0) + (stats.data?.by_grade?.A ?? 0)

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Your tender activity at a glance."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Open matches"
          value={stats.data?.total}
          isLoading={stats.isPending}
        />
        <Stat label="Strong fits (S/A)" value={strong} isLoading={stats.isPending} />
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
