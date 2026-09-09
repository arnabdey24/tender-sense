import { createFileRoute, useNavigate } from "@tanstack/react-router"
import * as React from "react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Pagination,
  PaginationContent,
  PaginationItem,
} from "@/components/ui/pagination"
import { Switch } from "@/components/ui/switch"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { TendersTable } from "@/features/tenders/TendersTable"
import { TenderFilterSelect } from "@/features/tenders/TenderFilterSelect"
import {
  useTenderFacets,
  useTenders,
  useSources,
  type TenderQuery,
} from "@/features/tenders/api"
import { categoryLabel, statusLabel } from "@/features/tenders/format"

const PAGE_SIZE = 25

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
  page: z.number().int().min(1).optional(),
})

type Search = z.infer<typeof searchSchema>

export const Route = createFileRoute("/_app/app/tenders/")({
  validateSearch: searchSchema,
  component: TendersPage,
})

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

  const query: TenderQuery = {
    q: search.q,
    source: search.source,
    category: search.category,
    status: search.status,
    open_only: search.open_only,
    sort: search.sort ?? "published_at",
    descending: (search.sort ?? "published_at") !== "deadline_at",
    page: search.page ?? 1,
    page_size: PAGE_SIZE,
  }

  const tenders = useTenders(query)
  const facets = useTenderFacets(query)
  const sources = useSources()

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
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

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

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {tenders.isPending
              ? "Searching…"
              : `${total.toLocaleString()} notice${total === 1 ? "" : "s"}`}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault()
              setSearch({ q: draftQ.trim() || undefined })
            }}
          >
            <div className="flex min-w-56 flex-1 flex-col gap-1">
              <label htmlFor="tender-search" className="text-xs font-medium">
                Search
              </label>
              <Input
                id="tender-search"
                value={draftQ}
                onChange={(e) => setDraftQ(e.target.value)}
                placeholder="Title, summary or buyer"
              />
            </div>
            <div className="flex w-40 flex-col gap-1">
              <span className="text-xs font-medium">Category</span>
              <TenderFilterSelect
                label="Category"
                value={search.category}
                onChange={(v) =>
                  setSearch({ category: v as Search["category"] })
                }
                options={CATEGORIES.map((c) => ({
                  value: c,
                  label: categoryLabel(c),
                  count: facets.data?.by_category?.[c],
                }))}
              />
            </div>
            <div className="flex w-40 flex-col gap-1">
              <span className="text-xs font-medium">Status</span>
              <TenderFilterSelect
                label="Status"
                value={search.status}
                onChange={(v) => setSearch({ status: v as Search["status"] })}
                options={STATUSES.map((s) => ({
                  value: s,
                  label: statusLabel(s),
                  count: facets.data?.by_status?.[s],
                }))}
              />
            </div>
            <div className="flex w-44 flex-col gap-1">
              <span className="text-xs font-medium">Source</span>
              <TenderFilterSelect
                label="Source"
                value={search.source}
                onChange={(v) => setSearch({ source: v })}
                options={sourceOptions}
              />
            </div>
            <div className="flex w-36 flex-col gap-1">
              <span className="text-xs font-medium">Sort by</span>
              <TenderFilterSelect
                label="Sort by"
                value={search.sort}
                anyLabel="Newest"
                onChange={(v) => setSearch({ sort: v as Search["sort"] })}
                options={SORTS.filter((s) => s.value !== "published_at")}
              />
            </div>
            <label className="flex h-8 items-center gap-2 text-sm">
              <Switch
                checked={search.open_only ?? false}
                onCheckedChange={(checked) =>
                  setSearch({ open_only: checked || undefined })
                }
              />
              Open only
            </label>
            <Button type="submit" size="sm">
              Search
            </Button>
          </form>

          <ApiErrorAlert error={tenders.error} />

          <TendersTable
            tenders={tenders.data?.items ?? []}
            isLoading={tenders.isPending}
          />

          {pageCount > 1 ? (
            <Pagination className="justify-between">
              <span className="text-sm text-muted-foreground">
                Page {page} of {pageCount}
              </span>
              <PaginationContent>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setSearch({ page: page - 1 })}
                  >
                    Previous
                  </Button>
                </PaginationItem>
                <PaginationItem>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= pageCount}
                    onClick={() => setSearch({ page: page + 1 })}
                  >
                    Next
                  </Button>
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          ) : null}
        </CardContent>
      </Card>
    </>
  )
}
