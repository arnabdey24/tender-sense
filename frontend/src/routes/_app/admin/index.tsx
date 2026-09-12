import { createFileRoute, Link } from "@tanstack/react-router"
import {
  ActivityIcon,
  Building2Icon,
  CoinsIcon,
  DatabaseIcon,
  ListChecksIcon,
  MailIcon,
  SatelliteDishIcon,
} from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
import { PoolIntakeChart } from "@/features/admin/AdminCharts"
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
import { useOverview, useTrends, type Overview } from "@/features/admin/api"
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
  const mailProblems = data.email_config_problems ?? []
  const misconfigured = mailProblems.length > 0
  const stuck = data.email_stuck ?? 0

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
      {/*
        Three separate ways mail goes missing, and the tile has to distinguish
        them, because "0 failed" was reported while nothing was arriving.

        A failure gave up loudly and is visible. A *stuck* row was claimed by a
        worker that died before reporting an outcome — it used to be counted
        nowhere and listed nowhere, which is what let a verification email
        vanish in silence. And a configuration fault means every message is
        discarded or refused while the send path reports success, so the
        healthy-looking zero is the most misleading number on the page.
      */}
      <StatusTile
        icon={MailIcon}
        label="Mail"
        to="/admin/jobs"
        health={
          misconfigured
            ? "bad"
            : data.email_failed === 0 && stuck === 0
              ? "ok"
              : data.email_failed > 0
                ? "bad"
                : "warn"
        }
        value={misconfigured ? "!" : String(data.email_failed)}
        detail={
          misconfigured
            ? "not configured to send"
            : stuck > 0
              ? `${stuck} stuck · ${data.email_queued} waiting`
              : `gave up · ${data.email_queued} waiting`
        }
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

/**
 * Why mail is not arriving, in words, above everything else.
 *
 * A tile can say that outbound mail is broken; it cannot say that the sender
 * address is on a reserved domain no receiver will accept. That sentence is
 * the entire difference between an operator fixing it in a minute and a
 * tester filing "no email arrived, nothing in spam" for the third time.
 *
 * Nothing on the send path errors in any of these cases — the row is written,
 * claimed, handed to the transport and reported sent — so this is the only
 * place the fault becomes visible at all.
 */
function MailConfigAlert({ problems }: { problems: string[] }) {
  if (problems.length === 0) return null

  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-xl bg-destructive/5 p-4 ring-1 ring-destructive/25"
    >
      <div className="flex items-center gap-2">
        <MailIcon className="size-4 shrink-0 text-destructive" aria-hidden />
        <h2 className="text-sm font-medium">
          This deployment cannot deliver email
        </h2>
      </div>
      <ul className="flex flex-col gap-1.5">
        {problems.map((problem) => (
          <li key={problem} className="flex gap-2 text-sm text-pretty">
            <span aria-hidden className="text-destructive">
              &bull;
            </span>
            <span>{problem}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground text-pretty">
        Verification, password reset and invitation mail all go through this.
        Nothing on the send path reports an error when it is wrong, so the
        queue below will look healthy either way.
      </p>
    </div>
  )
}

function OverviewPage() {
  const overview = useOverview()
  const trends = useTrends()

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
      <MailConfigAlert problems={data.email_config_problems ?? []} />

      <ConsoleSection
        title="The pool"
        icon={DatabaseIcon}
        caption="Shared across every tenant. A pool that stops growing is the first symptom of a portal that has stopped answering."
      >
        {/*
          Two cards spanning 1,180px to hold one number each read as a page
          that has run out of things to say. Three of the deployment's pool
          facts are already here — the third was hiding as a footnote under the
          first — so they take a column each and the row closes.
        */}
        <div className="grid gap-3 sm:grid-cols-3">
          <Stat label="Notices held" value={data.tenders.toLocaleString()} />
          <Stat
            label="Still open"
            value={data.tenders_open.toLocaleString()}
            detail={`${(data.tenders - data.tenders_open).toLocaleString()} closed or withdrawn`}
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

        {/* The three numbers above are instants. This is the one thing on the
            page that can tell a portal which has stopped answering from one
            that simply had a quiet Tuesday. */}
        <div className="mt-6">
          <PoolIntakeChart trends={trends.data} isLoading={trends.isPending} />
        </div>
      </ConsoleSection>

      <ConsoleSection
        title="Portals"
        icon={SatelliteDishIcon}
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
        <Table density="compact" fixed>
          <TableHeader>
            <TableRow>
              <TableHead>Portal</TableHead>
              <TableHead className="w-32">Health</TableHead>
              <TableHead className="w-36">Last success</TableHead>
              <TableHead numeric className="w-24">Notices</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data.sources ?? []).map((source) => (
              <TableRow key={source.code}>
                <TableCell>
                  <div className="truncate font-medium">{source.name}</div>
                  <div className="truncate font-mono text-xs text-muted-foreground">
                    {source.code}
                  </div>
                </TableCell>
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
                <TableCell numeric>
                  {source.tenders.toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </ConsoleSection>

      <ConsoleSection
        title="Tenants and accounts"
        icon={Building2Icon}
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
