import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { LogInIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Button } from "@/components/ui/button"
import { FieldGroup, FieldSeparator } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { GoogleButton } from "@/features/auth/GoogleButton"
import { ResendVerificationButton } from "@/features/auth/ResendVerificationButton"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { applySession, postAuthDestination } from "@/lib/auth/session"
import type { SessionPayload } from "@/lib/auth/store"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

const searchSchema = z.object({
  redirect: z.string().optional(),
})

export const Route = createFileRoute("/_auth/login")({
  validateSearch: searchSchema,
  component: LoginPage,
})

const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Email is required")
    .email("Enter a valid email"),
  password: z.string().min(1, "Password is required"),
})

type LoginValues = z.infer<typeof loginSchema>

export function LoginForm({
  redirect,
  onSignedIn,
}: {
  redirect?: string
  /** Overrides the default post-login navigation (used by the invite flow). */
  onSignedIn?: (session: SessionPayload) => void
}) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = React.useState<ApiError | null>(null)

  const form = useZodForm({
    schema: loginSchema,
    defaultValues: { email: "", password: "" },
  })

  const onSubmit = form.handleSubmit(async (values: LoginValues) => {
    setError(null)
    try {
      const session = await unwrap(
        api.POST("/api/v1/auth/login", {
          body: { email: values.email, password: values.password },
        })
      )
      applySession(session, queryClient)
      if (onSignedIn) {
        onSignedIn(session)
        return
      }
      await navigate({ href: postAuthDestination(session, redirect) })
    } catch (err) {
      if (!isApiError(err)) throw err
      const attached = applyFieldErrors(form, err, ["email", "password"])
      if (!attached) setError(err)
    }
  })

  const email = form.watch("email")

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      {error ? (
        <ApiErrorAlert error={error}>
          {error.code === "email_not_verified" ? (
            <ResendVerificationButton email={email} />
          ) : null}
        </ApiErrorAlert>
      ) : null}

      <FieldGroup>
        <RhfField form={form} name="email" label="Email">
          <Input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
          />
        </RhfField>
        <RhfField
          form={form}
          name="password"
          label="Password"
          description={
            <Link to="/forgot-password" className="underline underline-offset-4">
              Forgot your password?
            </Link>
          }
        >
          <Input type="password" autoComplete="current-password" />
        </RhfField>
      </FieldGroup>

      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <LogInIcon data-icon="inline-start" />
        )}
        Sign in
      </Button>

      <FieldSeparator>or</FieldSeparator>
      <GoogleButton redirect={redirect ?? "/app/dashboard"} />
    </form>
  )
}

function LoginPage() {
  const { redirect } = Route.useSearch()

  return (
    <AuthCard
      title="Sign in"
      description="Welcome back. Enter your credentials to continue."
      footer={
        <span>
          New here?{" "}
          <Link
            to="/register"
            className="text-foreground underline underline-offset-4"
          >
            Create an account
          </Link>
        </span>
      }
    >
      <LoginForm redirect={redirect} />
    </AuthCard>
  )
}
