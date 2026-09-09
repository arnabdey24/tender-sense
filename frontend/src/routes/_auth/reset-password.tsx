import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { KeyRoundIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Button } from "@/components/ui/button"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { PasswordStrength } from "@/features/auth/PasswordStrength"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { applySession, postAuthDestination } from "@/lib/auth/session"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

const searchSchema = z.object({
  token: z.string().optional(),
})

export const Route = createFileRoute("/_auth/reset-password")({
  validateSearch: searchSchema,
  component: ResetPasswordPage,
})

const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters"),
    confirm: z.string().min(1, "Confirm your new password"),
  })
  .refine((v) => v.password === v.confirm, {
    path: ["confirm"],
    message: "Passwords do not match",
  })

export function ResetPasswordForm({ token }: { token?: string }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = React.useState<ApiError | null>(null)

  const form = useZodForm({
    schema,
    defaultValues: { password: "", confirm: "" },
  })

  const password = form.watch("password")

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    if (!token) return
    try {
      const session = await unwrap(
        api.POST("/api/v1/auth/reset-password", {
          body: { token, password: values.password },
        })
      )
      applySession(session, queryClient)
      await navigate({ href: postAuthDestination(session) })
    } catch (err) {
      if (!isApiError(err)) throw err
      if (!applyFieldErrors(form, err, ["password"])) setError(err)
    }
  })

  if (!token) {
    return (
      <div className="flex flex-col gap-4" data-testid="reset-no-token">
        <p className="text-sm text-muted-foreground">
          This reset link is missing its token. Request a fresh one.
        </p>
        <Button render={<Link to="/forgot-password" />} nativeButton={false}>
          Request a new link
        </Button>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />
      <FieldGroup>
        <RhfField
          form={form}
          name="password"
          label="New password"
          below={<PasswordStrength password={password ?? ""} />}
        >
          <Input type="password" autoComplete="new-password" />
        </RhfField>
        <RhfField form={form} name="confirm" label="Confirm new password">
          <Input type="password" autoComplete="new-password" />
        </RhfField>
      </FieldGroup>
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <KeyRoundIcon data-icon="inline-start" />
        )}
        Set new password
      </Button>
    </form>
  )
}

function ResetPasswordPage() {
  const { token } = Route.useSearch()

  return (
    <AuthCard
      title="Choose a new password"
      description="Pick something strong and unique. We will sign you in straight away."
    >
      <ResetPasswordForm token={token} />
    </AuthCard>
  )
}
