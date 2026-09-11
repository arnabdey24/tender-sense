import { createFileRoute } from "@tanstack/react-router"
import * as React from "react"
import { RefreshCwIcon, RotateCcwIcon, SearchIcon } from "lucide-react"

import { PageSection } from "@/components/layout/PageSection"
import { Badge } from "@/components/ui/badge"
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
import { Textarea } from "@/components/ui/textarea"
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
  useCreateTender,
  useImportTenders,
  useReprocessTender,
} from "@/features/admin/api"
import { useAdminSources } from "@/features/sources/api"
import { useTenders } from "@/features/tenders/api"
import { formatDate, sourceShort } from "@/features/tenders/format"

export const Route = createFileRoute("/_app/admin/pool")({
  component: PoolPage,
})

/** Ask the server once the typing settles, not on every keystroke. */
function useDebounced(value: string, delay = 300): string {
  const [settled, setSettled] = React.useState(value)

  React.useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return settled
}

/**
 * The pool itself, with the repair actions beside each notice.
 *
 * Reprocess re-runs extraction, embedding and every tenant's match against
 * whatever is already stored. Re-parse goes back further, to the raw payload
 * held at ingestion — the fix for a portal that changed its markup, and the one
 * that asks the portal for nothing, which is what makes it safe to run against
 * one that has started refusing us.
 */
function Pool() {
  const [draft, setDraft] = React.useState("")
  const q = useDebounced(draft)
  const tenders = useTenders({ q: q || undefined, page_size: 25 })
  const reprocess = useReprocessTender()
  const items = tenders.data?.items ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="relative max-w-sm">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search the pool by title, summary or buyer"
          aria-label="Search the pool"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </div>

      {tenders.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : !tenders.data ? (
        <ApiErrorAlert error={tenders.error} />
      ) : !items.length ? (
        <p className="text-sm text-muted-foreground">
          {q ? "No notice matches that." : "The pool is empty."}
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground tabular-nums">
            {tenders.data.total.toLocaleString()} notices
            {q ? " matching" : " held"}
            {tenders.data.total > items.length &&
              ` · showing the first ${items.length}`}
          </p>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Notice</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Closes</TableHead>
                  <TableHead className="text-right">Repair</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((tender) => (
                  <TableRow key={tender.id}>
                    <TableCell className="max-w-md">
                      <div className="truncate font-medium">{tender.title}</div>
                      <div className="truncate text-xs text-muted-foreground">
                        {tender.procuring_entity ?? "No buyer recorded"} ·{" "}
                        <span className="tabular-nums">
                          {tender.external_id}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {sourceShort(tender.source_code)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground tabular-nums">
                      {formatDate(tender.deadline_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={reprocess.isPending}
                          onClick={() =>
                            reprocess.mutate({ tenderId: tender.id })
                          }
                        >
                          <RefreshCwIcon /> Reprocess
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={reprocess.isPending}
                          title="Re-parse the stored payload first. Fetches nothing."
                          onClick={() =>
                            reprocess.mutate({
                              tenderId: tender.id,
                              reparse: true,
                            })
                          }
                        >
                          <RotateCcwIcon /> Re-parse
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
    </div>
  )
}

const EMPTY_NOTICE = {
  external_id: "",
  canonical_url: "",
  title: "",
  procuring_entity: "",
  deadline_at: "",
}

/**
 * One notice by hand, through the same upsert the scrapers use — so it is
 * indistinguishable downstream and goes through extraction and matching like
 * anything else. For the notice somebody was sent as a PDF, or one a portal
 * published and then withdrew before the scraper saw it.
 */
function AddNotice({ sources }: { sources: { code: string; name: string }[] }) {
  const create = useCreateTender()
  const [form, setForm] = React.useState(EMPTY_NOTICE)
  const [sourceCode, setSourceCode] = React.useState("manual")

  const ready = form.external_id && form.canonical_url && form.title

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        create.mutate(
          {
            source_code: sourceCode,
            // Both carry a server-side default, but the generated type requires
            // them; a hand-entered notice is open, and its category is whatever
            // extraction decides rather than whatever the operator guessed.
            procurement_category: "unknown",
            status: "open",
            external_id: form.external_id.trim(),
            canonical_url: form.canonical_url.trim(),
            title: form.title.trim(),
            procuring_entity: form.procuring_entity.trim() || null,
            // A date input gives a local calendar day; the pool stores instants.
            deadline_at: form.deadline_at
              ? new Date(`${form.deadline_at}T23:59:59`).toISOString()
              : null,
          },
          { onSuccess: () => setForm(EMPTY_NOTICE) }
        )
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="notice-title">Title</Label>
          <Input
            id="notice-title"
            value={form.title}
            onChange={(event) =>
              setForm({ ...form, title: event.target.value })
            }
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notice-id">Reference</Label>
          <Input
            id="notice-id"
            placeholder="1047821"
            value={form.external_id}
            onChange={(event) =>
              setForm({ ...form, external_id: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            The portal&rsquo;s own identifier. With the source it is what makes
            adding the same notice twice a no-op rather than a duplicate.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notice-url">Link</Label>
          <Input
            id="notice-url"
            placeholder="https://…"
            value={form.canonical_url}
            onChange={(event) =>
              setForm({ ...form, canonical_url: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            Where a bidder goes to read the original.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notice-buyer">Procuring entity</Label>
          <Input
            id="notice-buyer"
            value={form.procuring_entity}
            onChange={(event) =>
              setForm({ ...form, procuring_entity: event.target.value })
            }
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notice-deadline">Closing date</Label>
          <Input
            id="notice-deadline"
            type="date"
            value={form.deadline_at}
            onChange={(event) =>
              setForm({ ...form, deadline_at: event.target.value })
            }
          />
          <p className="text-xs text-muted-foreground">
            Left blank the notice has no clock, and every tender surface will
            say so rather than guess one.
          </p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="notice-source">Source</Label>
          <Select
            value={sourceCode}
            onValueChange={(value) => {
              if (value) setSourceCode(value)
            }}
          >
            <SelectTrigger id="notice-source">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {sources.map((source) => (
                  <SelectItem key={source.code} value={source.code}>
                    {source.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>

      <ApiErrorAlert error={create.error} />

      <div>
        <Button type="submit" disabled={!ready || create.isPending}>
          Add notice
        </Button>
      </div>
    </form>
  )
}

/** Many at once, from a JSON array or a CSV document. */
function Import({ sources }: { sources: { code: string; name: string }[] }) {
  const load = useImportTenders()
  const [payload, setPayload] = React.useState("")
  const [format, setFormat] = React.useState<"json" | "csv">("json")
  const [sourceCode, setSourceCode] = React.useState("manual")
  const report = load.data

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault()
        load.mutate({ payload, format, sourceCode })
      }}
    >
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="import-format">Format</Label>
          <Select
            value={format}
            onValueChange={(value) => {
              if (value) setFormat(value as "json" | "csv")
            }}
          >
            <SelectTrigger id="import-format" className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="json">JSON array</SelectItem>
                <SelectItem value="csv">CSV</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="import-source">Source for rows that omit one</Label>
          <Select
            value={sourceCode}
            onValueChange={(value) => {
              if (value) setSourceCode(value)
            }}
          >
            <SelectTrigger id="import-source" className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {sources.map((source) => (
                  <SelectItem key={source.code} value={source.code}>
                    {source.name}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="import-body">Document</Label>
        <Textarea
          id="import-body"
          className="min-h-48 font-mono text-xs"
          spellCheck={false}
          placeholder={
            format === "json"
              ? '[{"external_id": "1047821", "canonical_url": "https://…", "title": "…"}]'
              : "external_id,canonical_url,title\n1047821,https://…,…"
          }
          value={payload}
          onChange={(event) => setPayload(event.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          <span className="font-medium">external_id</span>,{" "}
          <span className="font-medium">canonical_url</span> and{" "}
          <span className="font-medium">title</span> are required; summary,
          description, procuring_entity, country, deadline_at, currency and
          estimated_value are read when present. A malformed row is reported and
          skipped rather than failing the batch.
        </p>
      </div>

      <ApiErrorAlert error={load.error} />

      <div>
        <Button type="submit" disabled={!payload.trim() || load.isPending}>
          Import
        </Button>
      </div>

      {report ? (
        <div className="flex flex-col gap-3 rounded-lg bg-surface-sunken p-4 ring-1 ring-foreground/10">
          <p className="text-sm tabular-nums">
            <span className="font-medium">{report.total}</span> rows read ·{" "}
            {report.created} added · {report.updated} updated ·{" "}
            {report.unchanged} already held ·{" "}
            <span className={report.failed ? "font-medium text-warning" : ""}>
              {report.failed} skipped
            </span>
          </p>
          {/* The rows that did not make it, and why — a count alone leaves the
              operator to guess which of two hundred lines was wrong. */}
          {report.errors?.length ? (
            <ul className="flex flex-col gap-1">
              {report.errors.map((entry, index) => (
                <li
                  key={index}
                  className="text-xs text-muted-foreground tabular-nums"
                >
                  Row {String(entry.row)}: {String(entry.error)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  )
}

function PoolPage() {
  const sources = useAdminSources(true)
  const options = (sources.data ?? []).map((source) => ({
    code: source.code,
    name: source.name,
  }))

  return (
    <div className="flex flex-col gap-8">
      <PageSection
        title="The pool"
        caption="Every notice on this deployment, shared by every tenant. Reprocess re-runs extraction and matching; re-parse goes back to the payload stored at ingestion and asks the portal for nothing."
      >
        <Pool />
      </PageSection>

      <PageSection
        title="Add a notice"
        caption="For one that arrived as a PDF, or that a portal published and withdrew before the scraper saw it. It goes through the same upsert the scrapers use, so it is indistinguishable downstream."
      >
        {sources.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <AddNotice sources={options} />
        )}
      </PageSection>

      <PageSection
        title="Import many"
        caption="A JSON array or a CSV document. Adding the same notice twice updates it rather than duplicating it, so re-running a corrected file is safe."
      >
        {sources.isPending ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Import sources={options} />
        )}
      </PageSection>
    </div>
  )
}
