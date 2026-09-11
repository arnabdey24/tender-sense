import { createFileRoute } from "@tanstack/react-router"
import { ChevronDownIcon, PlayIcon } from "lucide-react"

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
          <div className="overflow-x-auto">
            <Table density="compact">
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead numeric>Took</TableHead>
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
                        <div className="max-w-md truncate text-xs text-muted-foreground">
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
          </div>
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
          <div className="overflow-x-auto">
            <Table density="compact">
              <TableHeader>
                <TableRow>
                  <TableHead>To</TableHead>
                  <TableHead>Template</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Attempts</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="max-w-48 truncate">
                      {row.to_email}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
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
                        <div className="max-w-md truncate text-xs text-muted-foreground">
                          {row.last_error}
                        </div>
                      )}
                    </TableCell>
                    <TableCell numeric>
                      {row.attempts}
                    </TableCell>
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
          </div>
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
              <div className="overflow-x-auto">
                <Table density="compact">
                  <TableHeader>
                    <TableRow>
                      <TableHead>Day</TableHead>
                      <TableHead>Purpose</TableHead>
                      <TableHead className="text-right">Calls</TableHead>
                      <TableHead className="text-right">Tokens</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(usage.data?.rows ?? []).slice(0, 12).map((row, index) => (
                      <TableRow key={`${row.day}-${row.purpose}-${index}`}>
                        <TableCell>{row.day}</TableCell>
                        <TableCell>{row.purpose}</TableCell>
                        <TableCell numeric>
                          {row.calls}
                        </TableCell>
                        <TableCell numeric>
                          {(row.tokens_in + row.tokens_out).toLocaleString()}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
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
