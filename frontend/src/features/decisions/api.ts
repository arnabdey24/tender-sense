import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type Decision = components["schemas"]["Decision"]
export type DecisionRead = components["schemas"]["DecisionRead"]
export type DecisionWithTender = components["schemas"]["DecisionWithTender"]
export type DecisionPage = components["schemas"]["Page_DecisionWithTender_"]

/** Every decision ever recorded for a tender, newest first. */
export function useDecisionHistory(tenderId: string) {
  return useQuery<DecisionRead[], ApiError>({
    queryKey: qk.decisions.forTender(tenderId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/tenders/{tender_id}/decisions", {
          params: { path: { tender_id: tenderId } },
        })
      ),
  })
}

export function useDecisions(decision?: Decision) {
  const params = decision ? { decision } : {}
  return useQuery<DecisionPage, ApiError>({
    queryKey: qk.decisions.list(params),
    queryFn: () =>
      unwrap(api.GET("/api/v1/decisions", { params: { query: params } })),
  })
}

function invalidate(
  queryClient: ReturnType<typeof useQueryClient>,
  tenderId: string
) {
  void queryClient.invalidateQueries({ queryKey: qk.decisions.all() })
  void queryClient.invalidateQueries({
    queryKey: qk.decisions.forTender(tenderId),
  })
  // Every match row renders the decision beside the grade, so the feeds move
  // with it — the pipeline reads `decisions` and is already covered above.
  void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
}

export function useRecordDecision(
  tenderId: string
): UseMutationResult<
  DecisionRead,
  ApiError,
  { decision: Decision; note?: string }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      unwrap(
        api.PUT("/api/v1/tenders/{tender_id}/decision", {
          params: { path: { tender_id: tenderId } },
          body: { decision: body.decision, note: body.note ?? null },
        })
      ),
    onSuccess: (saved) => {
      invalidate(queryClient, tenderId)
      toast.add({ type: "success", title: `Marked as ${saved.decision}` })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not save the decision",
        description: error.message,
      }),
  })
}

export function useClearDecision(
  tenderId: string
): UseMutationResult<void, ApiError, void> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/v1/tenders/{tender_id}/decision", {
          params: { path: { tender_id: tenderId } },
        })
      ),
    onSuccess: () => {
      invalidate(queryClient, tenderId)
      toast.add({ type: "success", title: "Decision withdrawn" })
    },
  })
}

/**
 * One decision applied to many tenders.
 *
 * There is no bulk endpoint and this does not need one: the per-tender route
 * is a `PUT` and therefore idempotent, so a fan-out is safe to retry and
 * cannot double-record. Failures are collected rather than thrown — marking
 * twenty notices and having the nineteenth fail should still save the other
 * nineteen, and the toast has to say so honestly rather than reporting a
 * clean success or a total failure.
 */
export function useRecordDecisions(): UseMutationResult<
  { saved: number; failed: number },
  ApiError,
  { tenderIds: string[]; decision: Decision; note?: string }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tenderIds, decision, note }) => {
      const results = await Promise.allSettled(
        tenderIds.map((tenderId) =>
          unwrap(
            api.PUT("/api/v1/tenders/{tender_id}/decision", {
              params: { path: { tender_id: tenderId } },
              body: { decision, note: note ?? null },
            })
          )
        )
      )
      const failed = results.filter((r) => r.status === "rejected").length
      return { saved: results.length - failed, failed }
    },
    onSuccess: ({ saved, failed }, { decision }) => {
      void queryClient.invalidateQueries({ queryKey: qk.decisions.all() })
      void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
      if (failed === 0) {
        toast.add({
          type: "success",
          title: `${saved} marked as ${decision}`,
        })
        return
      }
      toast.add({
        type: failed === saved + failed ? "error" : "warning",
        title:
          saved === 0
            ? `Could not mark ${failed} notice${failed === 1 ? "" : "s"}`
            : `${saved} marked as ${decision}, ${failed} failed`,
        description: "The ones that failed are still unmarked. Try them again.",
      })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not save the decisions",
        description: error.message,
      }),
  })
}
