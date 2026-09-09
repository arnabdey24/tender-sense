export type ApiErrorEnvelope = {
  error: {
    code: string
    message: string
    details?: { field: string; message: string }[]
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fieldErrors: Record<string, string>

  constructor(init: {
    status: number
    code: string
    message: string
    fieldErrors?: Record<string, string>
  }) {
    super(init.message)
    this.name = "ApiError"
    this.status = init.status
    this.code = init.code
    this.fieldErrors = init.fieldErrors ?? {}
  }
}

function isEnvelope(body: unknown): body is ApiErrorEnvelope {
  if (typeof body !== "object" || body === null) return false
  const err = (body as { error?: unknown }).error
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { code?: unknown }).code === "string" &&
    typeof (err as { message?: unknown }).message === "string"
  )
}

const FALLBACK_MESSAGES: Record<number, string> = {
  400: "The request was invalid.",
  401: "You need to sign in to continue.",
  403: "You do not have permission to do that.",
  404: "We could not find what you were looking for.",
  409: "That conflicts with something that already exists.",
  422: "Some fields need attention.",
  429: "Too many requests. Please slow down.",
}

/**
 * Turn a failed fetch Response (+ parsed body, if any) into an ApiError.
 * Expects the backend envelope `{ error: { code, message, details?: [{field, message}] } }`;
 * falls back to sensible defaults when the body is missing or malformed.
 */
export function normalizeError(
  resp: Pick<Response, "status" | "statusText">,
  body: unknown
): ApiError {
  const status = resp.status

  if (isEnvelope(body)) {
    const fieldErrors: Record<string, string> = {}
    for (const d of body.error.details ?? []) {
      if (d && typeof d.field === "string" && !(d.field in fieldErrors)) {
        fieldErrors[d.field] = d.message
      }
    }
    return new ApiError({
      status,
      code: body.error.code,
      message: body.error.message,
      fieldErrors,
    })
  }

  const message =
    FALLBACK_MESSAGES[status] ??
    (status >= 500
      ? "Something went wrong on our side. Please try again."
      : resp.statusText || "Request failed.")

  return new ApiError({
    status,
    code: status >= 500 ? "server_error" : "unknown_error",
    message,
  })
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}
