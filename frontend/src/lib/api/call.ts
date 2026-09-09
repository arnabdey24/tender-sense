import type { FieldValues, Path, UseFormReturn } from "react-hook-form"

import { normalizeError, type ApiError } from "@/lib/api/errors"

export type FetchResult<T> = {
  data?: T
  error?: unknown
  response: Response
}

/**
 * Turn an openapi-fetch result into plain data, throwing a normalized
 * {@link ApiError} for any non-2xx response. Use it so every mutation and
 * query in the app fails with the same error shape.
 */
export async function unwrap<T>(promise: Promise<FetchResult<T>>): Promise<T> {
  const { data, error, response } = await promise
  if (!response.ok || error !== undefined) {
    throw normalizeError(response, error)
  }
  return data as T
}

/** `body.email` / `body -> email` → `email`. */
function normalizeFieldName(field: string): string {
  return field.replace(/^body[.>\s-]*/i, "").trim()
}

/**
 * Push `details: [{field, message}]` from a 422 onto the matching
 * react-hook-form fields. Returns `true` when at least one error was attached,
 * so callers can decide whether they still need a banner or toast.
 */
export function applyFieldErrors<
  TFieldValues extends FieldValues,
  TContext,
  TTransformed extends FieldValues,
>(
  form: UseFormReturn<TFieldValues, TContext, TTransformed>,
  err: ApiError,
  known?: readonly string[]
): boolean {
  let attached = false
  for (const [rawField, message] of Object.entries(err.fieldErrors)) {
    const field = normalizeFieldName(rawField)
    if (!field) continue
    if (known && !known.includes(field)) continue
    form.setError(field as Path<TFieldValues>, { type: "server", message })
    attached = true
  }
  return attached
}
