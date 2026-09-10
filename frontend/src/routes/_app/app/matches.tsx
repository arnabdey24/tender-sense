import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { MatchList } from "@/features/matches/MatchList"
import { useMatchStats, useMatches, type MatchQuery } from "@/features/matches/api"
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

  const total = matches.data?.total ?? 0
  const page = search.page ?? 1
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <>
      <PageHeader
        title="Matches"
        description="Every tender graded against your capability profile."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {matches.isPending ? "Scoring…" : `${total} matches`}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex w-36 flex-col gap-1">
              <span className="text-xs font-medium">Grade</span>
              <TenderFilterSelect
                label="Grade"
                value={search.grade}
                onChange={(v) => setSearch({ grade: v as Search["grade"] })}
                options={GRADES.map((g) => ({
                  value: g,
                  label: g,
                  count: stats.data?.by_grade?.[g],
                }))}
              />
            </div>
            <div className="flex w-44 flex-col gap-1">
              <span className="text-xs font-medium">Eligibility</span>
              <TenderFilterSelect
                label="Eligibility"
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
            <div className="flex w-40 flex-col gap-1">
              <span className="text-xs font-medium">Recommendation</span>
              <TenderFilterSelect
                label="Recommendation"
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
            <div className="flex w-36 flex-col gap-1">
              <span className="text-xs font-medium">Sort by</span>
              <TenderFilterSelect
                label="Sort by"
                value={search.sort}
                anyLabel="Best fit"
                onChange={(v) => setSearch({ sort: v as Search["sort"] })}
                options={[...SORTS]}
              />
            </div>
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
        </CardContent>
      </Card>
    </>
  )
}
