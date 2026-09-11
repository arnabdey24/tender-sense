import { createFileRoute } from "@tanstack/react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
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

function when(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function JobRunsCard() {
  const runs = useJobRuns()
  const trigger = useTriggerJob()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Background jobs</CardTitle>
        <CardDescription>
          A job that quietly stops running looks exactly like a job with nothing
          to do. These records are the difference.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2">
          {TRIGGERABLE_JOBS.map((item) => (
            <Button
              key={item.job}
              size="sm"
              variant="outline"
              onClick={() => trigger.mutate(item.job)}
              disabled={trigger.isPending}
            >
              {item.label}
            </Button>
          ))}
        </div>

        <ApiErrorAlert error={runs.error} />
        {runs.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead className="text-right">Took</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runs.data ?? []).map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="font-medium">{run.name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {when(run.started_at)}
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
                    <TableCell className="text-right tabular-nums">
                      {(run.duration_ms / 1000).toFixed(1)}s
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function MailCard() {
  const outbox = useEmailOutbox()
  const retry = useRetryEmail()
  const rows = outbox.data ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>Mail queue</CardTitle>
        <CardDescription>
          Anything not yet delivered. A row that gave up names its own cause in
          the last error — usually an SPF record rather than a bug.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ApiErrorAlert error={outbox.error} />
        {outbox.isPending ? (
          <Skeleton className="h-16 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing waiting. Every message has been delivered.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
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
                    <TableCell className="text-right tabular-nums">
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
      </CardContent>
    </Card>
  )
}

function SpendCard() {
  const usage = useAiUsage()
  const budget = usage.data?.daily_token_budget ?? 0
  const spent = usage.data?.spent_today ?? 0
  const percent = budget > 0 ? Math.min((spent / budget) * 100, 100) : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle>Model spend</CardTitle>
        <CardDescription>
          An exhausted budget explains missing explanations. Nothing else does —
          matches still score, the prose just degrades to the templated one.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
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
              {budget > 0 && <Progress value={percent} />}
            </div>

            {(usage.data?.rows ?? []).length > 0 && (
              <div className="overflow-x-auto">
                <Table>
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
                        <TableCell className="text-right tabular-nums">
                          {row.calls}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
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
      </CardContent>
    </Card>
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
