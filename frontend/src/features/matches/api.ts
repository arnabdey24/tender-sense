import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type Match = components["schemas"]["MatchRead"]
export type MatchDetail = components["schemas"]["MatchDetail"]
export type MatchPage = components["schemas"]["Page_MatchRead_"]
export type MatchStats = components["schemas"]["MatchStats"]
export type MatchGrade = components["schemas"]["MatchGrade"]
export type EligibilityStatus = components["schemas"]["EligibilityStatus"]
export type Recommendation = components["schemas"]["Recommendation"]
export type Urgency = components["schemas"]["Urgency"]

export type MatchQuery = {
  grade?: MatchGrade
  eligibility?: EligibilityStatus
  recommendation?: Recommendation
  urgency?: Urgency
  q?: string
  deadline_within_days?: number
  open_only?: boolean
  sort?: "similarity" | "deadline_at" | "published_at" | "created_at"
  descending?: boolean
  page?: number
  page_size?: number
}

/** Drop empty values so the query key and the request stay stable. */
function toParams(input: MatchQuery): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === "") continue
    out[key] = value
  }
  return out
}

export function useMatches(input: MatchQuery = {}) {
  const params = toParams(input)
  return useQuery<MatchPage, ApiError>({
    queryKey: qk.matches.list(params),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(api.GET("/api/v1/matches", { params: { query: params } })),
  })
}

export function useMatchStats(input: MatchQuery = {}) {
  const rest: MatchQuery = { ...input }
  delete rest.page
  delete rest.page_size
  const params = toParams(rest)
  return useQuery<MatchStats, ApiError>({
    queryKey: qk.matches.stats(params),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(api.GET("/api/v1/matches/stats", { params: { query: params } })),
  })
}

export function useTodayShortlist(input: MatchQuery = {}) {
  const params = toParams(input)
  return useQuery<MatchPage, ApiError>({
    queryKey: qk.matches.today(params),
    queryFn: () =>
      unwrap(api.GET("/api/v1/matches/today", { params: { query: params } })),
  })
}

/**
 * This organization's verdict on one tender. A 404 is expected and normal —
 * it means the tender has not been scored for this org yet — so it must not
 * be retried or surfaced as an error on the tender detail page.
 */
export function useMatch(tenderId: string) {
  return useQuery<MatchDetail | null, ApiError>({
    queryKey: qk.matches.detail(tenderId),
    retry: false,
    queryFn: async () => {
      const { data, error, response } = await api.GET(
        "/api/v1/matches/{tender_id}",
        { params: { path: { tender_id: tenderId } } }
      )
      if (response.status === 404) return null
      if (!response.ok || error !== undefined) {
        const { normalizeError } = await import("@/lib/api/errors")
        throw normalizeError(response, error)
      }
      return data as MatchDetail
    },
  })
}
