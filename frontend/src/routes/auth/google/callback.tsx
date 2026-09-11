import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { ApiError } from "@/lib/api/errors"
import { refreshSession, postAuthDestination } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"

const searchSchema = z.object({
  status: z.enum(["ok", "error"]).optional(),
  code: z.string().optional(),
  redirect: z.string().optional(),
})

export const Route = createFileRoute("/auth/google/callback")({
  validateSearch: searchSchema,
  component: GoogleCallbackPage,
})

const GOOGLE_MESSAGES: Record<string, string> = {
  access_denied: "You cancelled the Google sign-in.",
  invalid_state: "The sign-in attempt expired. Please try again.",
  email_not_verified: "Google has not verified that address.",
  provider_error: "Google could not complete the sign-in.",
}

export function GoogleCallbackPanel({
  status,
  code,
  redirect,
}: {
  status?: "ok" | "error"
  code?: string
  redirect?: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [failure, setFailure] = React.useState<ApiError | null>(() =>
    status === "ok"
      ? null
      : new ApiError({
          status: 400,
          code: code ?? "provider_error",
          message:
            GOOGLE_MESSAGES[code ?? ""] ??
            `Google sign-in failed (${code ?? "unknown error"}).`,
        })
  )

  const started = React.useRef(false)

  React.useEffect(() => {
    if (status !== "ok" || started.current) return
    started.current = true

    void (async () => {
      const ok = await refreshSession(queryClient)
      if (!ok) {
        setFailure(
          new ApiError({
            status: 401,
            code: "invalid_token",
            message:
              "Google signed you in, but we could not start a session. Please sign in again.",
          })
        )
        return
      }
      const { memberships, user } = useAuthStore.getState()
      await navigate({ href: postAuthDestination({ memberships, user }, redirect) })
    })()
  }, [status, redirect, navigate, queryClient])

  if (failure) {
    return (
      <div className="flex flex-col gap-4" data-testid="google-error">
        <ApiErrorAlert error={failure} title="Google sign-in failed" />
        <Button render={<Link to="/login" />} nativeButton={false}>
          Back to sign in
        </Button>
      </div>
    )
  }

  return (
    <div
      className="flex flex-col items-center gap-3 py-6"
      data-testid="google-pending"
    >
      <Spinner className="size-6" />
      <p className="text-sm text-muted-foreground">Finishing sign-in…</p>
    </div>
  )
}

function GoogleCallbackPage() {
  const { status, code, redirect } = Route.useSearch()

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted/40 p-6">
      <AuthCard title="Signing you in" description="Google sign-in">
        <GoogleCallbackPanel status={status} code={code} redirect={redirect} />
      </AuthCard>
    </main>
  )
}
