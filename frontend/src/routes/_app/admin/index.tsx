import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ActivityIcon,
  CoinsIcon,
  ListChecksIcon,
  MailIcon,
  SatelliteDishIcon,
} from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
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
type Health = "ok" | "warn" | "bad"

/**
 * One subsystem, as the console needs to report it.
 *
 * A tile carries a state, the number that decides that state, and a way into
 * the section that can do something about it. The colour is never alone: the
 * label says the same thing, which is the rule for every status in this
 * product and the reason it survives a colour-blind reader and a bad monitor.
 */
function StatusTile({
  icon: Icon,
  label,
  health,
  value,
  detail,
  to,
}: {
  icon: typeof ActivityIcon
  label: string
  health: Health
  value: string
  detail: string
  to: "/admin/sources" | "/admin/jobs" | "/admin/limits"
}) {
  const tone =
    health === "ok"
      ? "text-success"
      : health === "warn"
        ? "text-warning"
        : "text-destructive"
  const word = health === "ok" ? "Healthy" : health === "warn" ? "Degraded" : "Failing"

  return (
    <Link
      to={to}
      className="group flex flex-col gap-2 rounded-xl border p-4 transition-colors hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
    >
      <div className="flex items-center gap-2">
        <Icon className={cn("size-4 shrink-0", tone)} aria-hidden />
        <span className="text-sm font-medium">{label}</span>
        <span className={cn("ml-auto text-xs font-medium", tone)}>{word}</span>
      </div>
      <div className="font-heading text-2xl leading-none tabular-nums">
        {value}
      </div>
      <div className="text-xs text-muted-foreground">{detail}</div>
    </Link>
  )
}

/**
 * Is anything wrong, answered before anything else is said.
 *
 * The page used to open on an alert and then four stacked sections of counts,
 * which is a report rather than a board: an operator arriving because
 * something broke had to read all of it to find out what. Four tiles, one per
 * subsystem, each a link into the section that can fix it.
 */
function StatusBoard({ data }: { data: Overview }) {
  const sources = (data.sources ?? []).filter((s) => s.enabled)
  const budget = data.ai_daily_token_budget
  const unhealthy = sources.filter((s) => s.health !== "ok")
  const spend = budget > 0 ? data.ai_tokens_today / budget : 0

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <StatusTile
        icon={SatelliteDishIcon}
        label="Portals"
        to="/admin/sources"
        health={
          unhealthy.length === 0 ? "ok" : unhealthy.length < sources.length ? "warn" : "bad"
        }
        value={`${sources.length - unhealthy.length}/${sources.length}`}
        detail={
          unhealthy.length
            ? `${unhealthy.map((s) => s.code).join(", ")} not answering`
            : "All answering"
        }
      />
      <StatusTile
        icon={ListChecksIcon}
        label="Jobs"
        to="/admin/jobs"
        health={data.jobs_failed_24h === 0 ? "ok" : data.jobs_failed_24h < 10 ? "warn" : "bad"}
        value={String(data.jobs_failed_24h)}
        detail={`failed in 24h · ${data.scrapes_failed_24h} scrapes`}
      />
      <StatusTile
        icon={MailIcon}
        label="Mail"
        to="/admin/jobs"
        health={data.email_failed === 0 ? "ok" : "bad"}
        value={String(data.email_failed)}
        detail={`gave up · ${data.email_queued} waiting`}
      />
      <StatusTile
        icon={CoinsIcon}
        label="Model spend"
        to="/admin/limits"
        health={budget === 0 ? "ok" : spend >= 1 ? "bad" : spend > 0.8 ? "warn" : "ok"}
        value={
          budget > 0
            ? `${Math.round(spend * 100)}%`
            : data.ai_tokens_today.toLocaleString()
        }
        detail={
          budget > 0
            ? `${data.ai_tokens_today.toLocaleString()} of ${budget.toLocaleString()}`
            : "tokens today · no cap set"
        }
      />
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

  return (
    <div className="flex flex-col gap-8">
      <StatusBoard data={data} />

      <ConsoleSection
        title="The pool"
        caption="Shared across every tenant. A pool that stops growing is the first symptom of a portal that has stopped answering."
      >
        <div className="grid gap-3 sm:grid-cols-2">
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

        </div>
      </ConsoleSection>

      <ConsoleSection
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
      </ConsoleSection>

      <ConsoleSection
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
      </ConsoleSection>

    </div>
  )
}
