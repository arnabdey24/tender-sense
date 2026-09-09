import { TriangleAlertIcon } from "lucide-react"
import type * as React from "react"

import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { isApiError, type ApiError } from "@/lib/api/errors"

const TITLES: Record<string, string> = {
  invalid_credentials: "Those details did not match",
  email_not_verified: "Verify your email first",
  rate_limited: "Too many attempts",
  token_expired: "That link has expired",
  invalid_token: "That link is not valid",
  no_active_org: "No active organization",
  admin_required: "Admins only",
  not_a_member: "You are not a member of this organization",
  already_member: "Already a member",
  invitation_email_mismatch: "This invitation is for a different address",
  validation_error: "Check the highlighted fields",
}

function apiErrorTitle(error: ApiError): string {
  return TITLES[error.code] ?? "Something went wrong"
}

export type ApiErrorAlertProps = {
  error: unknown
  /** Overrides the code-derived heading. */
  title?: React.ReactNode
  /** Rendered below the message — a resend button, a link back to login… */
  children?: React.ReactNode
}

/**
 * Renders any thrown {@link ApiError} as a destructive Alert, mapping the
 * backend `code` onto a human heading. Renders nothing when `error` is null.
 */
export function ApiErrorAlert({ error, title, children }: ApiErrorAlertProps) {
  if (!error) return null

  const message = isApiError(error)
    ? error.message
    : error instanceof Error
      ? error.message
      : "An unexpected error occurred."
  const heading =
    title ?? (isApiError(error) ? apiErrorTitle(error) : "Something went wrong")

  return (
    <Alert variant="destructive" data-testid="api-error">
      <TriangleAlertIcon />
      <AlertTitle>{heading}</AlertTitle>
      <AlertDescription>
        <div className="flex flex-col items-start gap-2">
          <span>{message}</span>
          {children}
        </div>
      </AlertDescription>
    </Alert>
  )
}
