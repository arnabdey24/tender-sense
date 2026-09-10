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
  // The pipeline view is built from decisions, so it moves too.
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
