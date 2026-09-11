import { createFileRoute } from "@tanstack/react-router"
import * as React from "react"
import { PlayIcon, PlusIcon, RefreshCwIcon, RotateCcwIcon } from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
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
  useAdapters,
  useAdminSources,
  useCheckSource,
  useCreateSource,
  useReparseSource,
  useRunSource,
  useScraperRuns,
  useUpdateSource,
} from "@/features/sources/api"
import { timeAgo } from "@/lib/data/time"

export const Route = createFileRoute("/_app/admin/sources")({
  component: SourcesPage,
})

/**
 * Registering a portal had no interface at all.
 *
 * `POST /admin/sources` has existed since ingestion did, and the only way to
 * reach it was curl — which means adding a portal, the single most consequential
 * thing an operator can do to what this product sees, lived outside the product.
 * The adapter list comes from the registry rather than a hardcoded menu, so a
 * build that ships a new adapter offers it here without an edit.
 */
function RegisterPortal() {
  const adapters = useAdapters()
  const create = useCreateSource()
  const [form, setForm] = React.useState({
    code: "",
    name: "",
    adapter_key: "",
    base_url: "",
    country: "",
  })

  const ready = form.code && form.name && form.adapter_key

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate(
          {
            code: form.code.trim(),
            name: form.name.trim(),
            adapter_key: form.adapter_key,
            base_url: form.base_url.trim(),
            country: form.country.trim().toUpperCase() || null,
            // A portal is registered to be scraped; anything else is a
            // deliberate later change on the row itself.
            enabled: true,
          },
          {
            onSuccess: () =>
              setForm({
                code: "",
                name: "",
                adapter_key: "",
                base_url: "",
                country: "",
              }),
          }
        )
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-code">Code</Label>
          <Input
            id="source-code"
            placeholder="adb"
            value={form.code}
            onChange={(event) =>
              setForm({ ...form, code: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            Short, permanent, and used in every notice that arrives from it.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-name">Name</Label>
          <Input
            id="source-name"
            placeholder="Asian Development Bank"
            value={form.name}
            onChange={(event) =>
              setForm({ ...form, name: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            What members see beside a notice.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-adapter">Adapter</Label>
          <Select
            value={form.adapter_key || undefined}
            onValueChange={(value) => {
              // Base UI reports a cleared selection as null; an adapter is
              // required, so clearing it is simply not a change.
              if (value) setForm({ ...form, adapter_key: value })
            }}
          >
            <SelectTrigger id="source-adapter">
              <SelectValue placeholder="Choose an adapter" />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {(adapters.data ?? []).map((key) => (
                  <SelectItem key={key} value={key}>
                    {key}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            The code that knows how to read this portal. A portal with no
            adapter needs one written first.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="source-url">Base URL</Label>
          <Input
            id="source-url"
            placeholder="https://www.adb.org"
            value={form.base_url}
            onChange={(event) =>
              setForm({ ...form, base_url: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            Blank keeps the adapter&rsquo;s own default.
          </p>
        </div>
      </div>

      <ApiErrorAlert error={create.error} />

      <div>
        <Button type="submit" disabled={!ready || create.isPending}>
          Register portal
        </Button>
      </div>
    </form>
  )
}

function Portals() {
  const sources = useAdminSources(true)
  const update = useUpdateSource()
  const run = useRunSource()
  const check = useCheckSource()
  const reparse = useReparseSource()

  if (sources.isPending) return <Skeleton className="h-40 w-full" />
  if (!sources.data) return <ApiErrorAlert error={sources.error} />

  return (
    <div className="overflow-x-auto">
      {/*
        Rows, not cards. Three portals in cards took 430px and said the same
        six things a table says in 120px — and a table is what an operator is
        actually doing here: comparing portals against each other on health and
        on when they last answered.
      */}
      <Table density="compact">
        <TableHeader>
          <TableRow>
            <TableHead>Portal</TableHead>
            <TableHead>Adapter</TableHead>
            <TableHead>Last success</TableHead>
            <TableHead className="text-center">Scraped</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.data.map((source) => (
            <TableRow key={source.id}>
              <TableCell className="max-w-xs">
                <div className="truncate font-medium">{source.name}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {source.code}
                  {source.consecutive_failures > 0 &&
                    ` · ${source.consecutive_failures} failures in a row`}
                </div>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {source.adapter_key}
              </TableCell>
              <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                {source.last_success_at
                  ? timeAgo(source.last_success_at)
                  : "Never"}
              </TableCell>
              <TableCell className="text-center">
                <Switch
                  aria-label={`Scrape ${source.name}`}
                  checked={source.enabled}
                  disabled={update.isPending}
                  onCheckedChange={(checked) =>
                    update.mutate({ id: source.id, enabled: checked })
                  }
                />
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={run.isPending || !source.enabled}
                    onClick={() => run.mutate(source.id)}
                  >
                    <PlayIcon /> Scrape
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={check.isPending}
                    onClick={() => check.mutate(source.id)}
                  >
                    <RefreshCwIcon /> Probe
                  </Button>
                  {/* Replays what is stored and fetches nothing, which is what
                      makes it safe against a portal refusing us. */}
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={reparse.isPending}
                    onClick={() => reparse.mutate(source.id)}
                  >
                    <RotateCcwIcon /> Replay
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function RunHistory() {
  const runs = useScraperRuns(true)
  const sources = useAdminSources(true)

  // A mixed list of runs with no portal on it says a scrape succeeded without
  // saying which portal succeeded at what — which is precisely the question
  // this table exists to answer. The names are already loaded; joining here
  // costs nothing and keeps the run record itself narrow.
  const portal = new Map(
    (sources.data ?? []).map((source) => [source.id, source.name])
  )

  if (runs.isPending) return <Skeleton className="h-32 w-full" />
  if (!runs.data?.length) {
    return <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
  }

  return (
    <div className="overflow-x-auto">
      <Table density="compact">
        <TableHeader sticky>
          <TableRow>
            <TableHead>Started</TableHead>
            <TableHead>Portal</TableHead>
            <TableHead>Result</TableHead>
            <TableHead numeric>Seen</TableHead>
            <TableHead numeric>New</TableHead>
            <TableHead numeric>Updated</TableHead>
            <TableHead numeric>Lost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.data.slice(0, 25).map((run) => (
            <TableRow key={run.id}>
              <TableCell className="text-sm">{timeAgo(run.started_at)}</TableCell>
              <TableCell className="text-sm">
                {portal.get(run.source_id) ?? "a portal since removed"}
              </TableCell>
              <TableCell>
                <span className="text-sm capitalize">{run.status}</span>
                {run.error && (
                  <div className="max-w-md truncate text-xs text-muted-foreground">
                    {run.error}
                  </div>
                )}
              </TableCell>
              <TableCell numeric>
                {run.notices_seen}
              </TableCell>
              <TableCell numeric>
                {run.created}
              </TableCell>
              <TableCell numeric>
                {run.updated}
              </TableCell>
              <TableCell numeric>
                {run.failed}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function SourcesPage() {
  return (
    <div className="flex flex-col gap-6">
      <ConsoleSection
        title="Portals"
        caption="Members see health and can start a sync under Settings. This is where a portal is registered, retuned or taken out of the schedule."
      >
        <Portals />
      </ConsoleSection>

      <ConsoleSection
        title="Recent runs"
        caption="A scraper that quietly stops returning notices looks exactly like a quiet portal. These records are the difference."
      >
        <RunHistory />
      </ConsoleSection>

      {/*
        Registering a portal is a twice-a-year action, and it was sitting above
        the run history an operator checks daily — 500px of form between them
        and the thing they came for. Collapsed, the page opens on what is
        watched rather than on what is occasionally added.
      */}
      <ConsoleSection title="Register a portal">
        <Collapsible>
          <CollapsibleTrigger
            render={
              <Button variant="outline" size="sm">
                <PlusIcon /> Add a portal
              </Button>
            }
          />
          <CollapsibleContent className="pt-4">
            <RegisterPortal />
          </CollapsibleContent>
        </Collapsible>
      </ConsoleSection>
    </div>
  )
}
