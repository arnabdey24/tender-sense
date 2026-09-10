import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type SourceRead = components["schemas"]["SourceRead"]
export type SourceAdminRead = components["schemas"]["SourceAdminRead"]
export type ScraperRun = components["schemas"]["ScraperRunRead"]
export type SourceHealth = components["schemas"]["SourceHealth"]

/**
 * Everyone sees the portals and their health — "where do these notices come
 * from, and is that still working" is a question any member can ask about
 * their own feed. Only staff see the scraping configuration behind them.
 */
export function useSources() {
  return useQuery<SourceRead[], ApiError>({
    queryKey: qk.tenders.sources(),
    queryFn: () => unwrap(api.GET("/api/v1/sources")),
  })
}

export function useAdminSources(enabled: boolean) {
  return useQuery<SourceAdminRead[], ApiError>({
    queryKey: qk.admin.sources(),
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/admin/sources")),
  })
}

export function useScraperRuns(enabled: boolean, sourceId?: string) {
  return useQuery<ScraperRun[], ApiError>({
    queryKey: qk.admin.scraperRuns(sourceId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/scraper-runs", {
          params: { query: sourceId ? { source_id: sourceId } : {} },
        })
      ),
  })
}

function reportFailure(error: ApiError, title: string): void {
  toast.add({ type: "error", title, description: error.message })
}

/** Queue one portal for scraping. Deduplicated by source on the server. */
export function useRunSource() {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, string>({
    mutationFn: (sourceId) =>
      unwrap(
        api.POST("/api/v1/admin/sources/{source_id}/run", {
          params: { path: { source_id: sourceId } },
        })
      ),
    onSuccess: () => {
      toast.add({
        type: "success",
        title: "Scrape queued",
        description: "Notices appear as the run works through the portal.",
      })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) => reportFailure(error, "Could not queue the scrape"),
  })
}

/**
 * Ask the portal whether it answers right now, rather than reading the health
 * recorded by past runs — the two disagree exactly when it matters.
 */
export function useCheckSource() {
  return useMutation<
    components["schemas"]["SourceHealthCheck"],
    ApiError,
    string
  >({
    mutationFn: (sourceId) =>
      unwrap(
        api.POST("/api/v1/admin/sources/{source_id}/check", {
          params: { path: { source_id: sourceId } },
        })
      ),
    onSuccess: (result) => {
      toast.add({
        type: result.reachable ? "success" : "error",
        title: result.reachable
          ? `${result.source_code} is answering`
          : `${result.source_code} is not answering`,
        description: result.detail ?? undefined,
      })
    },
    onError: (error) => reportFailure(error, "The probe failed"),
  })
}

/**
 * Replay stored payloads through the parser. The repair path for a portal that
 * changed its markup: fix the selectors, replay, and every notice ingested by
 * the broken parser is corrected without touching the portal again.
 */
export function useReparseSource() {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, string>({
    mutationFn: (sourceId) =>
      unwrap(
        api.POST("/api/v1/admin/sources/{source_id}/reparse", {
          params: { path: { source_id: sourceId } },
        })
      ),
    onSuccess: () => {
      toast.add({
        type: "success",
        title: "Replay queued",
        description: "Stored pages are re-parsed; nothing is fetched again.",
      })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) => reportFailure(error, "Could not queue the replay"),
  })
}
