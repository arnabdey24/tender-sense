import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { XIcon } from "lucide-react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import {
  useMatchStats,
  useMatches,
  type MatchQuery,
} from "@/features/matches/api"
import { TenderFilterSelect } from "@/features/tenders/TenderFilterSelect"

const PAGE_SIZE = 25

const searchSchema = z.object({
  grade: z.enum(["S", "A", "B", "C"]).optional(),
  eligibility: z
    .enum(["eligible", "needs_verification", "ineligible"])
    .optional(),
  recommendation: z.enum(["bid", "hold", "skip"]).optional(),
  sort: z
    .enum(["similarity", "deadline_at", "published_at", "created_at"])
    .optional(),
  page: z.number().int().min(1).optional(),
})

type Search = z.infer<typeof searchSchema>

export const Route = createFileRoute("/_app/app/matches")({
  validateSearch: searchSchema,
  component: MatchesPage,
})

const GRADES = ["S", "A", "B", "C"] as const
const ELIGIBILITY = [
  { value: "eligible", label: "Eligible" },
  { value: "needs_verification", label: "Needs checking" },
  { value: "ineligible", label: "Not eligible" },
] as const
const RECOMMENDATIONS = [
  { value: "bid", label: "Bid" },
  { value: "hold", label: "Hold" },
  { value: "skip", label: "Skip" },
] as const
const SORTS = [
  { value: "deadline_at", label: "Deadline" },
  { value: "created_at", label: "Newest" },
] as const

function MatchesPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: Route.fullPath })

  function setSearch(patch: Partial<Search>) {
    void navigate({
      search: (prev) => {
        const next = { ...prev, ...patch }
        if (!("page" in patch)) delete next.page
        for (const key of Object.keys(next) as (keyof Search)[]) {
          if (next[key] === undefined) delete next[key]
        }
        return next
      },
    })
  }

  const query: MatchQuery = {
    grade: search.grade,
    eligibility: search.eligibility,
    recommendation: search.recommendation,
    sort: search.sort ?? "similarity",
    descending: (search.sort ?? "similarity") !== "deadline_at",
    page: search.page ?? 1,
    page_size: PAGE_SIZE,
  }

  const matches = useMatches(query)
  const stats = useMatchStats(query)

  const activeFilters = [
    search.grade && {
      key: "grade",
      label: `Grade ${search.grade}`,
      clear: () => setSearch({ grade: undefined }),
    },
    search.eligibility && {
      key: "eligibility",
      label:
        ELIGIBILITY.find((e) => e.value === search.eligibility)?.label ??
        search.eligibility,
      clear: () => setSearch({ eligibility: undefined }),
    },
    search.recommendation && {
      key: "recommendation",
      label:
        RECOMMENDATIONS.find((r) => r.value === search.recommendation)?.label ??
        search.recommendation,
      clear: () => setSearch({ recommendation: undefined }),
    },
  ].filter(Boolean) as { key: string; label: string; clear: () => void }[]

  const total = matches.data?.total ?? 0
  const page = search.page ?? 1
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <>
      <PageHeader
        title="Matches"
        description="Every tender graded against your capability profile."
      />

      {/* Same toolbar the tender pool uses: each control names its own filter,
          then the applied ones are listed where the result count is. */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="w-36">
            <TenderFilterSelect
              label="Grade"
              anyLabel="Any grade"
              value={search.grade}
              onChange={(v) => setSearch({ grade: v as Search["grade"] })}
              options={GRADES.map((g) => ({
                value: g,
                label: `Grade ${g}`,
                count: stats.data?.by_grade?.[g],
              }))}
            />
          </div>
          <div className="w-44">
            <TenderFilterSelect
              label="Eligibility"
              anyLabel="Any eligibility"
              value={search.eligibility}
              onChange={(v) =>
                setSearch({ eligibility: v as Search["eligibility"] })
              }
              options={ELIGIBILITY.map((e) => ({
                ...e,
                count: stats.data?.by_eligibility?.[e.value],
              }))}
            />
          </div>
          <div className="w-44">
            <TenderFilterSelect
              label="Recommendation"
              anyLabel="Any recommendation"
              value={search.recommendation}
              onChange={(v) =>
                setSearch({ recommendation: v as Search["recommendation"] })
              }
              options={RECOMMENDATIONS.map((r) => ({
                ...r,
                count: stats.data?.by_recommendation?.[r.value],
              }))}
            />
          </div>
          <div className="w-36">
            <TenderFilterSelect
              label="Sort by"
              value={search.sort}
              anyLabel="Best fit"
              onChange={(v) => setSearch({ sort: v as Search["sort"] })}
              options={[...SORTS]}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b pb-3 text-sm">
          <span className="text-muted-foreground tabular-nums">
            {matches.isPending ? "Scoring…" : `${total} matches`}
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
                    grade: undefined,
                    eligibility: undefined,
                    recommendation: undefined,
                  })
                }
                className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
              >
                Clear all
              </button>
            </>
          )}
        </div>

        <ApiErrorAlert error={matches.error} />

        <MatchList
          matches={matches.data?.items ?? []}
          isLoading={matches.isPending}
        />

        {pageCount > 1 ? (
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              Page {page} of {pageCount}
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setSearch({ page: page - 1 })}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount}
                onClick={() => setSearch({ page: page + 1 })}
              >
                Next
              </Button>
            </div>
          </div>
        ) : null}
      </div>
    </>
  )
}
