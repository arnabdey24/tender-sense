import { createFileRoute, Link } from "@tanstack/react-router"
import { CheckCircle2Icon, TriangleAlertIcon } from "lucide-react"

import { PageSection } from "@/components/layout/PageSection"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { useOverview, type Overview } from "@/features/admin/api"
import { timeAgo } from "@/lib/data/time"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_app/admin/")({
  component: OverviewPage,
})

function Stat({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail?: string
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border p-4">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="font-heading text-2xl leading-none tabular-nums">
        {value}
      </span>
      {detail ? (
        <span className="text-xs text-muted-foreground">{detail}</span>
      ) : null}
    </div>
  )
}

/**
 * What is wrong, said first.
 *
 * An operator opens this page with one question, and a wall of totals does not
 * answer it: the counts are context, and the failures are the news. So anything
 * currently broken is stated in a sentence at the top, and when nothing is, the
 * page says that too rather than leaving the reader to infer it from six zeroes.
 */
function Verdict({ data }: { data: Overview }) {
  const unanswering = (data.sources ?? []).filter(
    (source) => source.enabled && source.health !== "ok"
  ).length

  const problems = [
    unanswering &&
      `${unanswering} portal${unanswering === 1 ? "" : "s"} not answering`,
    data.jobs_failed_24h && `${data.jobs_failed_24h} failed job runs in 24h`,
    data.scrapes_failed_24h &&
      `${data.scrapes_failed_24h} failed scrapes in 24h`,
    data.email_failed && `${data.email_failed} messages gave up`,
    data.ai_daily_token_budget > 0 &&
      data.ai_tokens_today >= data.ai_daily_token_budget &&
      "the model budget for today is spent",
  ].filter(Boolean) as string[]

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-lg border p-4",
        problems.length ? "border-warning/40 bg-warning/5" : "bg-surface-sunken"
      )}
    >
      {problems.length ? (
        <TriangleAlertIcon className="mt-0.5 size-5 shrink-0 text-warning" />
      ) : (
        <CheckCircle2Icon className="mt-0.5 size-5 shrink-0 text-success" />
      )}
      <div className="min-w-0">
        <p className="text-sm font-medium">
          {problems.length
            ? "Wants attention"
            : "Nothing is failing right now"}
        </p>
        <p className="text-sm text-pretty text-muted-foreground">
          {problems.length
            ? problems.join(" · ")
            : "Portals answering, jobs completing, mail going out, budget intact."}
        </p>
      </div>
    </div>
  )
}

function OverviewPage() {
  const overview = useOverview()

  if (overview.isPending) {
    return <Skeleton className="h-64 w-full" />
  }
  if (!overview.data) {
    return <ApiErrorAlert error={overview.error} />
  }

  const data = overview.data
  const budget = data.ai_daily_token_budget

  return (
    <div className="flex flex-col gap-8">
      <Verdict data={data} />

      <PageSection
        title="The pool"
        caption="Shared across every tenant. A pool that stops growing is the first symptom of a portal that has stopped answering."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat
            label="Notices held"
            value={data.tenders.toLocaleString()}
            detail={`${data.tenders_open.toLocaleString()} still open`}
          />
          <Stat
            label="Added in 24h"
            value={data.tenders_added_today.toLocaleString()}
            detail={
              data.tenders_added_today === 0
                ? "Nothing new since yesterday"
                : undefined
            }
          />
          <Stat
            label="Model spend today"
            value={data.ai_tokens_today.toLocaleString()}
            detail={
              budget > 0
                ? `of ${budget.toLocaleString()} tokens`
                : "no daily cap set"
            }
          />
        </div>
      </PageSection>

      <PageSection
        title="Portals"
        caption="Where the notices come from, and when each last answered."
        action={
          <Link
            to="/app/settings/sources"
            className="text-sm font-medium text-primary hover:underline"
          >
            Sources
          </Link>
        }
      >
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Portal</TableHead>
                <TableHead>Health</TableHead>
                <TableHead>Last success</TableHead>
                <TableHead className="text-right">Notices</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data.sources ?? []).map((source) => (
                <TableRow key={source.code}>
                  <TableCell className="font-medium">{source.name}</TableCell>
                  <TableCell>
                    {/*
                      A disabled source is not an unhealthy one. `manual` holds
                      hand-entered notices and is never scraped, so reporting it
                      as "ok · never" put a permanent non-event beside the
                      portals that actually answer.
                    */}
                    {source.enabled ? (
                      <Badge
                        variant={
                          source.health === "ok"
                            ? "success"
                            : source.health === "degraded"
                              ? "warning"
                              : "destructive"
                        }
                      >
                        {source.health}
                      </Badge>
                    ) : (
                      <Badge variant="outline">not scraped</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {!source.enabled
                      ? "—"
                      : source.last_success_at
                        ? timeAgo(source.last_success_at)
                        : "Never"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {source.tenders.toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </PageSection>

      <PageSection
        title="Tenants and accounts"
        caption="Every organization on this deployment, and everyone who can sign in to one."
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Stat
            label="Organizations"
            value={data.organizations.toLocaleString()}
            detail={`${data.organizations_active.toLocaleString()} active`}
          />
          <Stat
            label="Accounts"
            value={data.users.toLocaleString()}
            detail={`${data.users_active.toLocaleString()} active`}
          />
        </div>
      </PageSection>

      <PageSection
        title="Queues"
        caption="A job that fails quietly and mail that never leaves look identical from inside the app. These are where they show."
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Failed jobs, 24h" value={String(data.jobs_failed_24h)} />
          <Stat
            label="Failed scrapes, 24h"
            value={String(data.scrapes_failed_24h)}
          />
          <Stat label="Mail waiting" value={String(data.email_queued)} />
          <Stat label="Mail gave up" value={String(data.email_failed)} />
        </div>
      </PageSection>
    </div>
  )
}
