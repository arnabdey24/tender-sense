import { useMutation, type UseMutationResult } from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import type { components } from "@/lib/api/schema"

export type CompanyResearch = components["schemas"]["CompanyResearch"]
export type ResearchResponse = components["schemas"]["ResearchResponse"]
export type WritingField = components["schemas"]["WritingField"]

/**
 * Read a company's website and draft its profile.
 *
 * No `onSuccess` that writes anything: the caller drops the draft into its own
 * form state and the person corrects it before saving. A failure is surfaced
 * by the caller too, beside the field, rather than as a toast — the address
 * they typed is the thing that needs fixing and it is right there.
 */
export function useResearchCompany(): UseMutationResult<
  ResearchResponse,
  ApiError,
  { url: string }
> {
  return useMutation({
    mutationFn: ({ url }) =>
      unwrap(api.POST("/api/v1/ai/research-company", { body: { url } })),
  })
}

/** Rewrite one field's prose, keeping the facts already in it. */
export function useImproveText(): UseMutationResult<
  { text: string; note: string },
  ApiError,
  { field: WritingField; text: string }
> {
  return useMutation({
    mutationFn: async ({ field, text }) => {
      const result = await unwrap(
        api.POST("/api/v1/ai/improve-text", { body: { field, text } })
      )
      return { text: result.text, note: result.note ?? "" }
    },
    onError: (error) =>
      toast.add({
        type: "error",
        title: "Could not improve that",
        description: error.message,
      }),
  })
}
