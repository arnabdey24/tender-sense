import { createFileRoute } from "@tanstack/react-router"
import {
  PlayIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SatelliteDishIcon,
} from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { PageBody, PageSection } from "@/components/layout/PageSection"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
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
import { SourceHealthBadge } from "@/features/sources/SourceHealthBadge"
import {
  useAdminSources,
  useCheckSource,
  useReparseSource,
  useRunSource,
  useScraperRuns,
  useSources,
} from "@/features/sources/api"
import { countryName } from "@/lib/data/locale"
import { useIsSuperuser } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/sources")({
  component: SourcesSettingsPage,
})

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "Never"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "Never"
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function SourceTable() {
  const sources = useSources()

  if (sources.isPending) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (!sources.data?.length) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <SatelliteDishIcon />
          </EmptyMedia>
          <EmptyTitle>No portals yet</EmptyTitle>
          <EmptyDescription>
            Notices arrive once a portal is registered. Ask your TenderSense
            operator to add one.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Portal</TableHead>
            <TableHead>Country</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last checked</TableHead>
            <TableHead>Last success</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.data.map((source) => (
            <TableRow key={source.id}>
              <TableCell>
                <div className="font-medium">{source.name}</div>
                <div className="text-xs text-muted-foreground">
                  {source.code}
                  {!source.enabled && " · paused"}
                </div>
              </TableCell>
              <TableCell>{countryName(source.country) || "—"}</TableCell>
              <TableCell>
                <SourceHealthBadge
                  health={source.health}
                  enabled={source.enabled}
                />
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatWhen(source.last_run_at)}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatWhen(source.last_success_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function OperatorControls() {
  const sources = useAdminSources(true)
  const runSource = useRunSource()
  const checkSource = useCheckSource()
  const reparseSource = useReparseSource()

  if (sources.isPending) return <Skeleton className="h-24 w-full" />

  return (
    <div className="flex flex-col gap-4">
      <ApiErrorAlert error={sources.error} />
      {sources.data?.map((source) => (
        <div
          key={source.id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3"
        >
          <div className="min-w-0">
            <div className="font-medium">{source.code}</div>
            <div className="truncate text-xs text-muted-foreground">
              {source.adapter_key} · {source.base_url || "no base URL"}
              {source.consecutive_failures > 0 &&
                ` · ${source.consecutive_failures} failures in a row`}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => checkSource.mutate(source.id)}
              disabled={checkSource.isPending}
            >
              <RefreshCwIcon /> Probe
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => runSource.mutate(source.id)}
              disabled={runSource.isPending}
            >
              <PlayIcon /> Scrape now
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => reparseSource.mutate(source.id)}
              disabled={reparseSource.isPending}
            >
              <RotateCcwIcon /> Replay stored pages
            </Button>
          </div>
        </div>
      ))}
    </div>
  )
}

function RunHistory() {
  const runs = useScraperRuns(true)

  if (runs.isPending) return <Skeleton className="h-24 w-full" />
  if (!runs.data?.length) {
    return (
      <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Started</TableHead>
            <TableHead>Result</TableHead>
            <TableHead className="text-right">Seen</TableHead>
            <TableHead className="text-right">New</TableHead>
            <TableHead className="text-right">Updated</TableHead>
            <TableHead className="text-right">Lost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.data.slice(0, 20).map((run) => (
            <TableRow key={run.id}>
              <TableCell className="text-sm">
                {formatWhen(run.started_at)}
              </TableCell>
              <TableCell>
                <span className="text-sm capitalize">{run.status}</span>
                {run.error && (
                  <div className="max-w-md truncate text-xs text-muted-foreground">
                    {run.error}
                  </div>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {run.notices_seen}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {run.created}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {run.updated}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {run.failed}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function SourcesSettingsPage() {
  const isSuperuser = useIsSuperuser()

  return (
    <>
      <PageHeader
        title="Sources"
        description="The procurement portals TenderSense watches on your behalf."
      />

      <PageBody>
        <PageSection
          title="Portals"
          caption="The tender pool is shared, so every portal here feeds every organization's matches. A portal marked degraded or down means notices may be missing from your feed."
        >
          <SourceTable />
        </PageSection>

        {isSuperuser && (
          <>
            <PageSection
              title="Operator controls"
              caption="Replaying re-parses pages already stored — it fetches nothing, which is what makes it safe to run against a portal that has started refusing us."
            >
              <OperatorControls />
            </PageSection>

            <PageSection
              title="Recent runs"
              caption="A scraper that quietly stops returning notices looks exactly like a quiet portal. These records are the difference."
            >
              <RunHistory />
            </PageSection>
          </>
        )}
      </PageBody>
    </>
  )
}
