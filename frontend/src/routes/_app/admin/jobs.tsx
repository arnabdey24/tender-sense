import { createFileRoute } from "@tanstack/react-router"
import {
  ChevronDownIcon,
  CoinsIcon,
  ListChecksIcon,
  MailIcon,
  PlayIcon,
} from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
import { timeAgo } from "@/lib/data/time"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
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
import {
  TRIGGERABLE_JOBS,
  useAiUsage,
  useEmailOutbox,
  useJobRuns,
  useRetryEmail,
  useTriggerJob,
} from "@/features/admin/api"

export const Route = createFileRoute("/_app/admin/jobs")({
  component: JobsPage,
})

const RUN_VARIANTS: Record<
  string,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  succeeded: "success",
  partial: "warning",
  failed: "destructive",
  running: "secondary",
}


function JobRunsCard() {
  const runs = useJobRuns()
  const trigger = useTriggerJob()

  return (
    <ConsoleSection
      title="Background jobs"
      icon={ListChecksIcon}
      caption="A job that quietly stops running looks exactly like a job with nothing to do. These records are the difference."
      action={
        /*
          Eight buttons wrapping across two rows gave every job equal weight
          and none of it hierarchy — a soup of verbs at the top of the page an
          operator came to read. They are occasional by nature, so they go
          behind one control that says what they are.
        */
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button size="sm" variant="outline" disabled={trigger.isPending}>
                <PlayIcon /> Run a job
                <ChevronDownIcon data-icon="inline-end" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-56">
            {TRIGGERABLE_JOBS.map((item) => (
              <DropdownMenuItem
                key={item.job}
                onClick={() => trigger.mutate(item.job)}
              >
                {item.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      }
    >
      <div className="flex flex-col gap-4">
        <ApiErrorAlert error={runs.error} />
        {runs.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <Table density="compact" fixed viewport="max-h-[26rem]" label="Background job runs">
            <TableHeader sticky>
              <TableRow>
                <TableHead className="w-64">Job</TableHead>
                <TableHead className="w-28">Started</TableHead>
                <TableHead>Result</TableHead>
                <TableHead numeric className="w-20">
                  Took
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(runs.data ?? []).map((run) => (
                <TableRow key={run.id}>
                  <TableCell className="font-medium">{run.name}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {timeAgo(run.started_at)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={RUN_VARIANTS[run.status] ?? "outline"}>
                      {run.status}
                    </Badge>
                    {run.error && (
                      <div className="truncate text-xs text-muted-foreground">
                        {run.error}
                      </div>
                    )}
                  </TableCell>
                  <TableCell numeric>
                    {(run.duration_ms / 1000).toFixed(1)}s
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </ConsoleSection>
  )
}

function MailCard() {
  const outbox = useEmailOutbox()
  const retry = useRetryEmail()
  const rows = outbox.data ?? []

  return (
    <ConsoleSection
      title="Mail queue"
      icon={MailIcon}
      caption="Anything not yet delivered. A row that gave up names its own cause in the last error — usually an SPF record rather than a bug."
    >
      <div>
        <ApiErrorAlert error={outbox.error} />
        {outbox.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing waiting. Every message has been delivered.
          </p>
        ) : (
          <Table density="compact" fixed viewport="max-h-[22rem]" label="Mail queue" className="min-w-[54rem]">
            <TableHeader sticky>
              <TableRow>
                <TableHead className="w-72">To</TableHead>
                <TableHead className="w-48">Template</TableHead>
                <TableHead>Status</TableHead>
                <TableHead numeric className="w-24">
                  Attempts
                </TableHead>
                <TableHead className="w-24">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.id}>
                  <TableCell className="truncate">{row.to_email}</TableCell>
                  <TableCell className="truncate text-sm text-muted-foreground">
                    {row.template_key}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={
                        row.status === "failed" ? "destructive" : "secondary"
                      }
                    >
                      {row.status}
                    </Badge>
                    {row.last_error && (
                      <div className="truncate text-xs text-muted-foreground">
                        {row.last_error}
                      </div>
                    )}
                  </TableCell>
                  <TableCell numeric>{row.attempts}</TableCell>
                  <TableCell className="text-right">
                    {row.status === "failed" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => retry.mutate(row.id)}
                        disabled={retry.isPending}
                      >
                        Retry
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </ConsoleSection>
  )
}

function SpendCard() {
  const usage = useAiUsage()
  const budget = usage.data?.daily_token_budget ?? 0
  const spent = usage.data?.spent_today ?? 0
  const percent = budget > 0 ? Math.min((spent / budget) * 100, 100) : 0

  return (
    <ConsoleSection
      title="Model spend"
      icon={CoinsIcon}
      caption="An exhausted budget explains missing explanations. Nothing else does — matches still score, the prose just degrades to the templated one."
    >
      <div className="flex flex-col gap-4">
        <ApiErrorAlert error={usage.error} />
        {usage.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <div className="flex justify-between text-sm">
                <span>Today</span>
                <span className="tabular-nums">
                  {spent.toLocaleString()}
                  {budget > 0 ? ` / ${budget.toLocaleString()}` : " (no cap)"}
                </span>
              </div>
              {/* A bare progressbar has no accessible name, so a screen
                  reader announces a percentage of nothing in particular. */}
              {budget > 0 && (
                <Progress
                  value={percent}
                  aria-label={`Model tokens used today: ${spent.toLocaleString()} of ${budget.toLocaleString()}`}
                />
              )}
            </div>

            {(usage.data?.rows ?? []).length > 0 && (
              <Table density="compact" fixed className="max-w-3xl min-w-[34rem]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-32">Day</TableHead>
                    <TableHead>Purpose</TableHead>
                    <TableHead numeric className="w-24">
                      Calls
                    </TableHead>
                    <TableHead numeric className="w-32">
                      Tokens
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(usage.data?.rows ?? []).slice(0, 12).map((row, index) => (
                    <TableRow key={`${row.day}-${row.purpose}-${index}`}>
                      <TableCell className="tabular-nums">{row.day}</TableCell>
                      <TableCell className="truncate">{row.purpose}</TableCell>
                      <TableCell numeric>{row.calls}</TableCell>
                      <TableCell numeric>
                        {(row.tokens_in + row.tokens_out).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </div>
    </ConsoleSection>
  )
}

function JobsPage() {
  return (
    <div className="flex flex-col gap-6">
      <JobRunsCard />
      <MailCard />
      <SpendCard />
    </div>
  )
}
