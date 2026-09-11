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
export type SyncState = components["schemas"]["SyncState"]
export type PortalSyncState = components["schemas"]["PortalSyncState"]

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

/**
 * Where the portals stand. Polled while a pass is in flight and left alone
 * otherwise: a control that says "syncing" has to stop saying it by itself, but
 * a settled one has nothing to watch and no reason to keep asking.
 */
export function useSyncState() {
  return useQuery<SyncState, ApiError>({
    queryKey: qk.tenders.sync(),
    queryFn: () => unwrap(api.GET("/api/v1/sources/sync")),
    refetchInterval: (query) => (query.state.data?.running ? 4000 : false),
  })
}

/**
 * Pull every portal now. Available to any member, because the person staring at
 * an empty pool is rarely platform staff.
 *
 * A press inside the cooldown is not an error and is not reported as one — the
 * server answers with the wait, and the button shows a countdown.
 */
export function useSyncSources() {
  const queryClient = useQueryClient()
  return useMutation<SyncState, ApiError, void>({
    mutationFn: () => unwrap(api.POST("/api/v1/sources/sync")),
    onSuccess: (state) => {
      queryClient.setQueryData(qk.tenders.sync(), state)
      void queryClient.invalidateQueries({ queryKey: qk.tenders.sources() })
      if (state.queued.length) {
        toast.add({
          type: "success",
          title:
            state.queued.length === 1
              ? "Syncing one portal"
              : `Syncing ${state.queued.length} portals`,
          description:
            "Notices appear as each pass works through. This page follows along.",
        })
      }
    },
    onError: (error) => reportFailure(error, "Could not start the sync"),
  })
}

/** Adapter keys this build knows, so registering a portal is a choice. */
export function useAdapters() {
  return useQuery<string[], ApiError>({
    queryKey: qk.admin.adapters(),
    queryFn: () => unwrap(api.GET("/api/v1/admin/adapters")),
    staleTime: Infinity,
  })
}

export function useCreateSource() {
  const queryClient = useQueryClient()
  return useMutation<
    SourceAdminRead,
    ApiError,
    components["schemas"]["SourceCreate"]
  >({
    mutationFn: (body) => unwrap(api.POST("/api/v1/admin/sources", { body })),
    onSuccess: (source) => {
      toast.add({
        type: "success",
        title: `${source.name} registered`,
        description: "It joins the schedule, and can be pulled now from Sources.",
      })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
      void queryClient.invalidateQueries({ queryKey: qk.tenders.sources() })
    },
    onError: (error) => reportFailure(error, "Could not register the portal"),
  })
}

export function useUpdateSource() {
  const queryClient = useQueryClient()
  return useMutation<
    SourceAdminRead,
    ApiError,
    { id: string } & components["schemas"]["SourceUpdate"]
  >({
    mutationFn: ({ id, ...body }) =>
      unwrap(
        api.PATCH("/api/v1/admin/sources/{source_id}", {
          params: { path: { source_id: id } },
          body,
        })
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
      void queryClient.invalidateQueries({ queryKey: qk.tenders.sources() })
    },
    onError: (error) => reportFailure(error, "Could not update the portal"),
  })
}
