import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { SearchIcon, XIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import {
  DataTableColumnsMenu,
  DataTableDensityToggle,
  DataTableProvider,
  DataTableSelectionBar,
  DataTableSurface,
  useDataTable,
  useDataTableContext,
} from "@/components/ui/data-table"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Paginator } from "@/components/layout/Paginator"
import { usePersistentState } from "@/hooks/use-persistent-state"
import { Switch } from "@/components/ui/switch"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { TendersTable, type TenderSort } from "@/features/tenders/TendersTable"
import { PortalSyncButton } from "@/features/sources/PortalSync"
import { usePortalSync } from "@/features/sources/use-portal-sync"
import { EmptySignal } from "@/components/brand/EmptySignal"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { TENDER_COLUMNS } from "@/features/tenders/columns"
import { useRecordDecisions } from "@/features/decisions/api"
import { TenderFilterSelect } from "@/features/tenders/TenderFilterSelect"
import {
  useTenderFacets,
  useTenders,
  useSources,
  type TenderQuery,
} from "@/features/tenders/api"
import { categoryLabel, statusLabel } from "@/features/tenders/format"
import { cn } from "@/lib/utils"


const searchSchema = z.object({
  q: z.string().optional(),
  source: z.string().optional(),
  category: z
    .enum(["goods", "works", "services", "consulting", "unknown"])
    .optional(),
  status: z
    .enum(["open", "closed", "cancelled", "awarded", "unknown"])
    .optional(),
  open_only: z.boolean().optional(),
  sort: z
    .enum(["published_at", "deadline_at", "title", "estimated_value"])
    .optional(),
  // Direction is its own parameter now that column headers can flip it. It was
  // previously derived from the field, so a user could sort by deadline but
  // never furthest-first.
  desc: z.boolean().optional(),
  page: z.number().int().min(1).optional(),
})

type Search = z.infer<typeof searchSchema>

/**
 * The pool has never been filled — or has been emptied. Distinct from "no
 * notices match", and answered with the control rather than with advice.
 */
function EmptyPool() {
  const { state } = usePortalSync()
  const everPulled = state?.portals.some((portal) => portal.last_success_at)

  return (
    <Empty>
      <EmptyHeader>
        <EmptySignal />
        <EmptyTitle>
          {everPulled ? "The portals have nothing right now" : "Nothing pulled yet"}
        </EmptyTitle>
        <EmptyDescription>
          {everPulled
            ? "The last pass over each portal came back empty. The schedule tries again at 02:00, 08:00, 14:00 and 20:00 — or pull them now."
            : "TenderSense reads e-GP Bangladesh and the World Bank procurement feed four times a day. Pull them now and the first notices arrive in a few minutes."}
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <PortalSyncButton />
      </EmptyContent>
    </Empty>
  )
}

export const Route = createFileRoute("/_app/app/tenders/")({
  validateSearch: searchSchema,
  component: TendersPage,
})

/** What each field means when you first click it: newest, soonest, A–Z, largest. */
const DEFAULT_DESC: Record<TenderSort, boolean> = {
  published_at: true,
  deadline_at: false,
  title: false,
  estimated_value: true,
}

const CATEGORIES = ["goods", "works", "services", "consulting"] as const
const STATUSES = ["open", "closed", "cancelled", "awarded"] as const
const SORTS: { value: NonNullable<Search["sort"]>; label: string }[] = [
  { value: "published_at", label: "Newest" },
  { value: "deadline_at", label: "Deadline" },
  { value: "estimated_value", label: "Value" },
  { value: "title", label: "Title" },
]

function TendersPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })

  const setSearch = React.useCallback(
    (patch: Partial<Search>) => {
      void navigate({
        search: (prev) => {
          const next = { ...prev, ...patch }
          // Any filter change resets to the first page.
          if (!("page" in patch)) delete next.page
          for (const key of Object.keys(next) as (keyof Search)[]) {
            if (next[key] === undefined || next[key] === "" || next[key] === false) {
              delete next[key]
            }
          }
          return next
        },
      })
    },
    [navigate]
  )

  // A view preference, not a filter: it belongs to the reader, not the URL.
  const [pageSize, setPageSize] = usePersistentState("tenders:page-size", 10)

  const sortField: TenderSort = search.sort ?? "published_at"
  const descending = search.desc ?? DEFAULT_DESC[sortField]

  // Clicking the column you are already sorted by reverses it; clicking a new
  // one starts at that field's natural direction rather than inheriting the
  // last one, which is what makes "Closes" open on soonest-first.
  const onSort = (key: TenderSort) => {
    if (key === sortField) setSearch({ desc: !descending })
    else setSearch({ sort: key, desc: DEFAULT_DESC[key] })
  }

  const query: TenderQuery = {
    q: search.q,
    source: search.source,
    category: search.category,
    status: search.status,
    open_only: search.open_only,
    sort: sortField,
    descending,
    page: search.page ?? 1,
    page_size: pageSize,
  }

  const tenders = useTenders(query)
  const facets = useTenderFacets(query)
  const sources = useSources()

  const items = React.useMemo(
    () => tenders.data?.items ?? [],
    [tenders.data?.items]
  )
  const rowIds = React.useMemo(() => items.map((t) => t.id), [items])
  const table = useDataTable({
    rowIds,
    storageKey: "tenders",
    columns: TENDER_COLUMNS,
    // Absent on roughly nine notices in ten, so it does not earn a column
    // until someone asks for it.
    defaultHidden: ["value"],
  })

  // Local text buffer for the search box, reconciled with the URL during render
  // (React's "adjust state on prop change" pattern) rather than in an effect.
  const [draftQ, setDraftQ] = React.useState(search.q ?? "")
  const [syncedQ, setSyncedQ] = React.useState(search.q)
  if (search.q !== syncedQ) {
    setSyncedQ(search.q)
    setDraftQ(search.q ?? "")
  }

  const total = tenders.data?.total ?? 0
  const page = search.page ?? 1

  const activeFilters = [
    search.q && {
      key: "q",
      label: `“${search.q}”`,
      clear: () => setSearch({ q: undefined }),
    },
    search.category && {
      key: "category",
      label: categoryLabel(search.category),
      clear: () => setSearch({ category: undefined }),
    },
    search.status && {
      key: "status",
      label: statusLabel(search.status),
      clear: () => setSearch({ status: undefined }),
    },
    search.source && {
      key: "source",
      label: search.source,
      clear: () => setSearch({ source: undefined }),
    },
    search.open_only && {
      key: "open_only",
      label: "Open only",
      clear: () => setSearch({ open_only: undefined }),
    },
  ].filter(Boolean) as { key: string; label: string; clear: () => void }[]

  const sourceOptions = (sources.data ?? []).map((s) => ({
    value: s.code,
    label: s.name,
    count: facets.data?.by_source?.[s.code],
  }))

  return (
    <>
      <PageHeader
        title="Tenders"
        description="The shared pool of procurement notices TenderSense tracks."
      />

      {/* One self-describing toolbar. Each control states what it filters, so
          the five stacked labels above them were saying it twice. */}
      <DataTableProvider value={table}>
        <DataTableSurface className="flex flex-col gap-3">
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setSearch({ q: draftQ.trim() || undefined })
          }}
        >
          <InputGroup className="min-w-64 flex-1">
            <InputGroupAddon>
              <SearchIcon />
            </InputGroupAddon>
            <InputGroupInput
              id="tender-search"
              aria-label="Search tenders"
              value={draftQ}
              onChange={(e) => setDraftQ(e.target.value)}
              placeholder="Search title, summary or buyer"
            />
          </InputGroup>

          <div className="w-40">
            <TenderFilterSelect
              label="Category"
              anyLabel="Any category"
              value={search.category}
              onChange={(v) => setSearch({ category: v as Search["category"] })}
              options={CATEGORIES.map((c) => ({
                value: c,
                label: categoryLabel(c),
                count: facets.data?.by_category?.[c],
              }))}
            />
          </div>
          <div className="w-36">
            <TenderFilterSelect
              label="Status"
              anyLabel="Any status"
              value={search.status}
              onChange={(v) => setSearch({ status: v as Search["status"] })}
              options={STATUSES.map((s) => ({
                value: s,
                label: statusLabel(s),
                count: facets.data?.by_status?.[s],
              }))}
            />
          </div>
          <div className="w-40">
            <TenderFilterSelect
              label="Source"
              anyLabel="Any source"
              value={search.source}
              onChange={(v) => setSearch({ source: v })}
              options={sourceOptions}
            />
          </div>
          {/* The desktop table sorts from its column headers; a phone gets
              stacked rows with no headers to click, so it keeps the select. */}
          <div className="w-36 md:hidden">
            <TenderFilterSelect
              label="Sort by"
              anyLabel="Newest first"
              value={search.sort}
              onChange={(v) => setSearch({ sort: v as Search["sort"] })}
              options={SORTS.filter((s) => s.value !== "published_at")}
            />
          </div>

          <label className="flex h-8 shrink-0 items-center gap-2 rounded-lg border px-2.5 text-sm">
            <Switch
              checked={search.open_only ?? false}
              onCheckedChange={(checked) =>
                setSearch({ open_only: checked || undefined })
              }
            />
            Open only
          </label>

          {/* Filtering a list is not this page's primary action — opening a
              notice is — so it does not take the brand fill. */}
          <Button type="submit" size="sm" variant="outline">
            Search
          </Button>

          <div className="ml-auto hidden items-center gap-1 md:flex">
            <DataTableDensityToggle />
            <DataTableColumnsMenu />
          </div>
        </form>

        {/* The same band reports either what is filtered or what is selected.
            Putting the selection bar below would push the table down and move
            the row the user just clicked out from under the cursor. */}
        <DataTableSelectionBar>
          <TenderBulkActions />
        </DataTableSelectionBar>

        <div
          className={cn(
            "flex flex-wrap items-center gap-2 border-b pb-3 text-sm",
            table.selected.size > 0 && "hidden"
          )}
        >
          <span className="text-muted-foreground tabular-nums">
            {tenders.isPending
              ? "Searching…"
              : `${total.toLocaleString()} notice${total === 1 ? "" : "s"}`}
          </span>
          {activeFilters.length > 0 && (
            <>
              <span className="text-muted-foreground">·</span>
              {activeFilters.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  onClick={filter.clear}
                  className="inline-flex items-center gap-1 rounded-4xl bg-muted px-2 py-0.5 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {filter.label}
                  <XIcon className="size-3" />
                </button>
              ))}
              <button
                type="button"
                onClick={() =>
                  setSearch({
                    q: undefined,
                    category: undefined,
                    status: undefined,
                    source: undefined,
                    open_only: undefined,
                  })
                }
                className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                Clear all
              </button>
            </>
          )}
        </div>

        <ApiErrorAlert error={tenders.error} />

        <TendersTable
          tenders={items}
          isLoading={tenders.isPending}
          sort={sortField}
          descending={descending}
          onSort={onSort}
          /*
            An empty pool is not an empty result. With no filter applied there
            is nothing to broaden and nothing to clear — the portals have simply
            not been read yet, which is what a new organization on a fresh
            deployment sees and what it saw with no way out of. So this is where
            the pull is offered, on the screen where the wall actually is.
          */
          emptyState={
            activeFilters.length === 0 ? <EmptyPool /> : undefined
          }
        />

        <Paginator
          page={page}
          pageSize={pageSize}
          total={total}
          noun="notice"
          onPage={(next) => {
            setSearch({ page: next === 1 ? undefined : next })
            window.scrollTo({ top: 0 })
          }}
          onPageSize={(size) => {
            setPageSize(size)
            // The old page number can point past the end of the resized set.
            setSearch({ page: undefined })
          }}
        />
        </DataTableSurface>
      </DataTableProvider>
    </>
  )
}

/**
 * Bid, hold or skip across every selected notice.
 *
 * There is no bulk endpoint; the per-tender route is a PUT, so this fans out
 * over it. The selection clears only once the write settles, so a failure
 * leaves the rows selected and the action repeatable.
 */
function TenderBulkActions() {
  const { selected, clearSelection } = useDataTableContext()
  const record = useRecordDecisions()

  const apply = (decision: "bid" | "hold" | "skip") => {
    record.mutate(
      { tenderIds: [...selected], decision },
      { onSuccess: ({ failed }) => failed === 0 && clearSelection() }
    )
  }

  return (
    <>
      {(["bid", "hold", "skip"] as const).map((decision) => (
        <Button
          key={decision}
          variant="outline"
          size="sm"
          disabled={record.isPending}
          onClick={() => apply(decision)}
          className="capitalize"
        >
          {decision}
        </Button>
      ))}
    </>
  )
}
