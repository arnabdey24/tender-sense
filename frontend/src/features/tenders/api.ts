import { keepPreviousData, useQuery } from "@tanstack/react-query"

import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type TenderSummary = components["schemas"]["TenderSummary"]
export type TenderDetail = components["schemas"]["TenderDetail"]
export type TenderFacets = components["schemas"]["TenderFacets"]
export type TenderPage = components["schemas"]["Page_TenderSummary_"]
export type SourceRead = components["schemas"]["SourceRead"]
export type ProcurementCategory = components["schemas"]["ProcurementCategory"]
export type TenderStatus = components["schemas"]["TenderStatus"]

export type TenderQuery = {
  q?: string
  source?: string
  category?: ProcurementCategory
  status?: TenderStatus
  open_only?: boolean
  deadline_within_days?: number
  sort?: "published_at" | "deadline_at" | "title" | "estimated_value"
  descending?: boolean
  page?: number
  page_size?: number
}

/** Drop empty values so the query key and the request stay stable. */
function toParams(input: TenderQuery): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined || value === "" || value === false) continue
    out[key] = value
  }
  return out
}

export function useTenders(input: TenderQuery) {
  const params = toParams(input)
  return useQuery<TenderPage, ApiError>({
    queryKey: qk.tenders.list(params),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(api.GET("/api/v1/tenders", { params: { query: params } })),
  })
}

export function useTenderFacets(input: TenderQuery) {
  // Facets follow the same filters as the list but never the pagination.
  const rest: TenderQuery = { ...input }
  delete rest.page
  delete rest.page_size
  const params = toParams(rest)
  return useQuery<TenderFacets, ApiError>({
    queryKey: qk.tenders.facets(params),
    placeholderData: keepPreviousData,
    queryFn: () =>
      unwrap(api.GET("/api/v1/tenders/facets", { params: { query: params } })),
  })
}

export function useTender(id: string) {
  return useQuery<TenderDetail, ApiError>({
    queryKey: qk.tenders.detail(id),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/tenders/{tender_id}", {
          params: { path: { tender_id: id } },
        })
      ),
  })
}

export function useSources() {
  return useQuery<SourceRead[], ApiError>({
    queryKey: qk.tenders.sources(),
    queryFn: () => unwrap(api.GET("/api/v1/sources")),
  })
}
