import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type JobRun = components["schemas"]["JobRunRead"]
export type EmailOutboxRow = components["schemas"]["EmailOutboxRead"]
export type AiUsageSummary = components["schemas"]["AiUsageSummary"]
export type Trends = components["schemas"]["Trends"]

export function useJobRuns(limit = 25) {
  return useQuery<JobRun[], ApiError>({
    queryKey: qk.admin.jobRuns(),
    // Runs are how you tell a broken worker from a quiet one, so this stays
    // fresh without anyone reaching for the reload button.
    refetchInterval: 30_000,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/jobs/runs", { params: { query: { limit } } })
      ),
  })
}

export function useEmailOutbox(limit = 25) {
  return useQuery<EmailOutboxRow[], ApiError>({
    queryKey: qk.admin.emailOutbox(),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/email-outbox", { params: { query: { limit } } })
      ),
  })
}

export function useAiUsage(days = 14) {
  return useQuery<AiUsageSummary, ApiError>({
    queryKey: qk.admin.aiUsage(days),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/ai-usage", { params: { query: { days } } })
      ),
  })
}

export function useTrends(days = 14) {
  return useQuery<Trends, ApiError>({
    queryKey: qk.admin.trends(days),
    // Same cadence as the run list it sits beside: a console showing a chart
    // that disagrees with the table under it is worse than one showing
    // neither.
    refetchInterval: 30_000,
    queryFn: () =>
      unwrap(api.GET("/api/v1/admin/trends", { params: { query: { days } } })),
  })
}

export function useTriggerJob() {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, string>({
    mutationFn: (job) =>
      unwrap(api.POST("/api/v1/admin/jobs/trigger", { body: { job } })),
    onSuccess: (_result, job) => {
      toast.add({
        type: "success",
        title: `${JOB_LABELS[job] ?? job} queued`,
        description: "It runs on the worker; the run appears below when it finishes.",
      })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not start that job",
        description: error.message,
      }),
  })
}

export function useRetryEmail() {
  const queryClient = useQueryClient()
  return useMutation<{ requeued: boolean }, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.POST("/api/v1/admin/email-outbox/{email_id}/retry", {
          params: { path: { email_id: id } },
        })
      ),
    onSuccess: (result) => {
      toast.add({
        type: result.requeued ? "success" : "error",
        title: result.requeued
          ? "Queued for another attempt"
          : "Only a message that gave up can be retried",
      })
      void queryClient.invalidateQueries({ queryKey: qk.admin.emailOutbox() })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not retry that message",
        description: error.message,
      }),
  })
}

/**
 * Jobs an operator may start by hand. The server keeps the authoritative
 * allowlist; this is the subset worth a button.
 */
export const TRIGGERABLE_JOBS = [
  { job: "scrape_all_sources", label: "Scrape all sources" },
  { job: "digest_dispatcher", label: "Send due digests" },
  { job: "deadline_reminder_sweep", label: "Sweep deadlines" },
  { job: "pump_email_outbox", label: "Flush the mail queue" },
  { job: "close_expired_tenders", label: "Close expired tenders" },
  { job: "refresh_fx_rates", label: "Refresh FX rates" },
  { job: "mark_source_health", label: "Check source health" },
  { job: "purge_orphan_blobs", label: "Purge orphaned payloads" },
] as const

/** So a toast can say "Scrape all sources queued" rather than the identifier. */
const JOB_LABELS: Record<string, string> = Object.fromEntries(
  TRIGGERABLE_JOBS.map((entry) => [entry.job, entry.label])
)

function reportFailure(error: ApiError, title: string): void {
  toast.add({ type: "error", title, description: error.message })
}

export type Overview = components["schemas"]["Overview"]
export type OrganizationAdminRead =
  components["schemas"]["OrganizationAdminRead"]
export type UserAdminRead = components["schemas"]["UserAdminRead"]
export type Limits = components["schemas"]["Limits"]

/**
 * The console's front page in one request. Polled slowly: an operator leaves
 * this open, and the questions it answers — is a portal down, is mail stuck —
 * change on the scale of a cron pass, not a second.
 */
export function useOverview() {
  return useQuery<Overview, ApiError>({
    queryKey: qk.admin.overview(),
    queryFn: () => unwrap(api.GET("/api/v1/admin/overview")),
    refetchInterval: 60_000,
  })
}

export function useAdminOrganizations(q?: string) {
  return useQuery<OrganizationAdminRead[], ApiError>({
    queryKey: qk.admin.organizations(q),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/organizations", {
          params: { query: q ? { q } : {} },
        })
      ),
  })
}

export function useAdminUsers(q?: string) {
  return useQuery<UserAdminRead[], ApiError>({
    queryKey: qk.admin.users(q),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/admin/users", { params: { query: q ? { q } : {} } })
      ),
  })
}

export function useUpdateUser() {
  const queryClient = useQueryClient()
  return useMutation<
    UserAdminRead,
    ApiError,
    { userId: string; is_active?: boolean; is_superuser?: boolean }
  >({
    mutationFn: ({ userId, ...body }) =>
      unwrap(
        api.PATCH("/api/v1/admin/users/{user_id}", {
          params: { path: { user_id: userId } },
          body,
        })
      ),
    onSuccess: (user) => {
      toast.add({ type: "success", title: `${user.email} updated` })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) => reportFailure(error, "Could not update the account"),
  })
}

/** The limits in force. Always fetched fresh — this page exists to edit them. */
export function useLimits() {
  return useQuery<Limits, ApiError>({
    queryKey: qk.admin.limits(),
    queryFn: () => unwrap(api.GET("/api/v1/admin/limits")),
    staleTime: 0,
  })
}

export function useSaveLimits() {
  const queryClient = useQueryClient()
  return useMutation<Limits, ApiError, Limits>({
    mutationFn: (body) => unwrap(api.PUT("/api/v1/admin/limits", { body })),
    onSuccess: (limits) => {
      queryClient.setQueryData(qk.admin.limits(), limits)
      toast.add({
        type: "success",
        title: "Limits saved",
        description: "In force within a few seconds. No restart needed.",
      })
    },
    onError: (error) => reportFailure(error, "Could not save the limits"),
  })
}

export function useResetLimits() {
  const queryClient = useQueryClient()
  return useMutation<Limits, ApiError, void>({
    mutationFn: () => unwrap(api.DELETE("/api/v1/admin/limits")),
    onSuccess: (limits) => {
      queryClient.setQueryData(qk.admin.limits(), limits)
      toast.add({
        type: "success",
        title: "Restored the configured limits",
        description: "The values this deployment was started with.",
      })
    },
    onError: (error) => reportFailure(error, "Could not restore the limits"),
  })
}

export type TenderCreate = components["schemas"]["TenderCreate"]
export type ImportResponse = components["schemas"]["ImportResponse"]

/** Add one notice by hand, through the same upsert path the scrapers use. */
export function useCreateTender() {
  const queryClient = useQueryClient()
  return useMutation<
    components["schemas"]["TenderCreateResponse"],
    ApiError,
    TenderCreate
  >({
    mutationFn: (body) => unwrap(api.POST("/api/v1/admin/tenders", { body })),
    onSuccess: (result) => {
      toast.add({
        type: "success",
        title:
          result.outcome === "created" ? "Notice added" : `Notice ${result.outcome}`,
        description: "It goes through extraction and matching like any other.",
      })
      void queryClient.invalidateQueries({ queryKey: qk.tenders.all() })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) => reportFailure(error, "Could not add the notice"),
  })
}

/**
 * Bulk import from a JSON array or a CSV document.
 *
 * The body is the document itself rather than a form field, and the content
 * type is what tells the server which it is — so this posts raw rather than
 * going through the typed client, which has no route for an unstructured body.
 */
export function useImportTenders() {
  const queryClient = useQueryClient()
  return useMutation<
    ImportResponse,
    ApiError,
    { payload: string; format: "json" | "csv"; sourceCode?: string }
  >({
    mutationFn: async ({ payload, format, sourceCode }) => {
      const query = sourceCode
        ? `?source_code=${encodeURIComponent(sourceCode)}`
        : ""
      return unwrap(
        api.POST(`/api/v1/admin/tenders/import${query}` as "/api/v1/admin/tenders/import", {
          body: payload as unknown as never,
          bodySerializer: (body: unknown) => body as string,
          headers: {
            "Content-Type": format === "csv" ? "text/csv" : "application/json",
          },
        })
      )
    },
    onSuccess: (report) => {
      toast.add({
        type: report.failed ? "warning" : "success",
        title: `${report.created} added, ${report.updated} updated`,
        description: report.failed
          ? `${report.failed} rows were skipped; the reasons are listed below.`
          : `${report.unchanged} already held, nothing lost.`,
      })
      void queryClient.invalidateQueries({ queryKey: qk.tenders.all() })
      void queryClient.invalidateQueries({ queryKey: qk.admin.all() })
    },
    onError: (error) => reportFailure(error, "Could not import that document"),
  })
}

/** Send one notice back through extraction, embedding and matching. */
export function useReprocessTender() {
  return useMutation<unknown, ApiError, { tenderId: string; reparse?: boolean }>({
    mutationFn: ({ tenderId, reparse }) =>
      unwrap(
        api.POST("/api/v1/admin/tenders/{tender_id}/reprocess", {
          params: {
            path: { tender_id: tenderId },
            query: reparse ? { reparse: true } : {},
          },
        })
      ),
    onSuccess: (_result, { reparse }) =>
      toast.add({
        type: "success",
        title: reparse ? "Re-parse and reprocess queued" : "Reprocess queued",
        description:
          "Extraction, embedding and every tenant's match are recomputed.",
      }),
    onError: (error) => reportFailure(error, "Could not queue the reprocess"),
  })
}
