import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { CheckCircle2Icon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { ResendVerificationButton } from "@/features/auth/ResendVerificationButton"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { ApiError, isApiError } from "@/lib/api/errors"
import { applySession, postAuthDestination } from "@/lib/auth/session"

const searchSchema = z.object({
  token: z.string().optional(),
  redirect: z.string().optional(),
})

export const Route = createFileRoute("/_auth/verify-email")({
  validateSearch: searchSchema,
  component: VerifyEmailPage,
})

type State =
  | { phase: "verifying" }
  | { phase: "done" }
  | { phase: "failed"; error: ApiError }

export function VerifyEmailPanel({
  token,
  redirect,
}: {
  token?: string
  redirect?: string
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [email, setEmail] = React.useState("")
  const [state, setState] = React.useState<State>(() =>
    token
      ? { phase: "verifying" }
      : {
          phase: "failed",
          error: new ApiError({
            status: 400,
            code: "invalid_token",
            message:
              "This link is missing its verification token. Request a new email below.",
          }),
        }
  )

  const started = React.useRef(false)

  React.useEffect(() => {
    if (!token || started.current) return
    started.current = true

    void (async () => {
      try {
        const session = await unwrap(
          api.POST("/api/v1/auth/verify-email", { body: { token } })
        )
        applySession(session, queryClient)
        setState({ phase: "done" })
        await navigate({ href: postAuthDestination(session, redirect) })
      } catch (err) {
        if (!isApiError(err)) throw err
        setState({ phase: "failed", error: err })
      }
    })()
  }, [token, redirect, navigate, queryClient])

  if (state.phase === "verifying") {
    return (
      <div
        className="flex flex-col items-center gap-3 py-6"
        data-testid="verify-pending"
      >
        <Spinner className="size-6" />
        <p className="text-sm text-muted-foreground">Verifying your email…</p>
      </div>
    )
  }

  if (state.phase === "done") {
    return (
      <div
        className="flex flex-col items-center gap-3 py-6"
        data-testid="verify-success"
      >
        <CheckCircle2Icon aria-hidden="true" className="size-8 text-primary" />
        <p className="text-sm text-muted-foreground">
          Email verified. Taking you to TenderSense…
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6" data-testid="verify-expired">
      <ApiErrorAlert error={state.error} />
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="resend-email">
            Send a new verification link
          </FieldLabel>
          <Input
            id="resend-email"
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </Field>
      </FieldGroup>
      <ResendVerificationButton
        email={email.trim()}
        variant="default"
        size="default"
        label="Send new link"
      />
      <p className="text-sm text-muted-foreground">
        Already verified?{" "}
        <Link to="/login" className="underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </div>
  )
}

function VerifyEmailPage() {
  const { token, redirect } = Route.useSearch()

  return (
    <AuthCard
      title="Verify your email"
      description="One moment while we confirm your address."
    >
      <VerifyEmailPanel token={token} redirect={redirect} />
    </AuthCard>
  )
}
