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

export type RuleCatalogue = components["schemas"]["RuleCatalogue"]
export type CatalogueAttribute = components["schemas"]["CatalogueAttribute"]
export type CataloguePreset = components["schemas"]["CataloguePreset"]
export type RuleSet = components["schemas"]["RuleSetRead"]
export type RuleSetWrite = components["schemas"]["RuleSetWrite"]
export type RuleSetVersion = components["schemas"]["RuleSetVersionRead"]
export type RuleDefinition = components["schemas"]["RuleDefinition"]
export type RuleSetDefinition = components["schemas"]["RuleSetDefinition"]
export type RulePreview = components["schemas"]["RulePreview"]
export type RuleStatus = components["schemas"]["RuleStatus"]
export type Operator = components["schemas"]["Operator"]
export type Severity = components["schemas"]["Severity"]
export type OnMissing = components["schemas"]["OnMissing"]

export function useRuleCatalogue() {
  return useQuery<RuleCatalogue, ApiError>({
    queryKey: qk.rules.catalogue(),
    // A fixed vocabulary; refetching it on every mount is pure noise.
    staleTime: Infinity,
    queryFn: () => unwrap(api.GET("/api/v1/rules/catalogue")),
  })
}

export function useRuleSet() {
  return useQuery<RuleSet, ApiError>({
    queryKey: qk.rules.current(),
    queryFn: () => unwrap(api.GET("/api/v1/rule-sets/current")),
  })
}

export function useRuleSetVersions() {
  return useQuery<RuleSetVersion[], ApiError>({
    queryKey: qk.rules.versions(),
    queryFn: () => unwrap(api.GET("/api/v1/rule-sets/current/versions")),
  })
}

export function useSaveRuleSet(): UseMutationResult<RuleSet, ApiError, RuleSetWrite> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) => unwrap(api.PUT("/api/v1/rule-sets/current", { body })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.rules.all() })
      // Saving re-scores the pool in the background, so anything showing a
      // verdict is now stale.
      void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
      toast.add({
        type: "success",
        title: "Criteria saved",
        description: "Your tenders are being re-checked in the background.",
      })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not save the criteria",
        description: error.message,
      }),
  })
}

export function useActivateVersion(): UseMutationResult<
  RuleSetVersion,
  ApiError,
  string
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (versionId) =>
      unwrap(
        api.POST("/api/v1/rule-sets/current/versions/{version_id}/activate", {
          params: { path: { version_id: versionId } },
        })
      ),
    onSuccess: (version) => {
      void queryClient.invalidateQueries({ queryKey: qk.rules.all() })
      void queryClient.invalidateQueries({ queryKey: qk.matches.all() })
      toast.add({
        type: "success",
        title: `Rolled back to version ${version.version_number}`,
      })
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not roll back",
        description: error.message,
      }),
  })
}

/**
 * Run a draft over the pool without saving it. Deliberately a mutation rather
 * than a query: it is an explicit action with a cost, not something to fire on
 * every keystroke.
 */
export function usePreviewRules(): UseMutationResult<
  RulePreview,
  ApiError,
  RuleSetDefinition
> {
  return useMutation({
    mutationFn: (definition) =>
      unwrap(
        api.POST("/api/v1/rule-sets/preview", {
          params: { query: { limit: 500 } },
          body: { name: "draft", definition },
        })
      ),
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not preview",
        description: error.message,
      }),
  })
}
