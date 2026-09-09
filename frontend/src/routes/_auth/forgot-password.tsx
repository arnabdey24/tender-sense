import { createFileRoute, Link } from "@tanstack/react-router"
import { MailCheckIcon, SendIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Button } from "@/components/ui/button"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

export const Route = createFileRoute("/_auth/forgot-password")({
  component: ForgotPasswordPage,
})

const schema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Email is required")
    .email("Enter a valid email"),
})

export function ForgotPasswordForm() {
  const [error, setError] = React.useState<ApiError | null>(null)
  const [sent, setSent] = React.useState<string | null>(null)

  const form = useZodForm({ schema, defaultValues: { email: "" } })

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await unwrap(
        api.POST("/api/v1/auth/forgot-password", {
          body: { email: values.email },
        })
      )
      setSent(values.email)
    } catch (err) {
      if (!isApiError(err)) throw err
      if (!applyFieldErrors(form, err, ["email"])) setError(err)
    }
  })

  if (sent) {
    return (
      <div className="flex flex-col items-start gap-4" data-testid="reset-sent">
        <MailCheckIcon aria-hidden="true" className="size-8 text-primary" />
        <p className="text-sm text-muted-foreground">
          If an account exists for{" "}
          <span className="font-medium text-foreground">{sent}</span>, a reset
          link is on its way. The link expires shortly, so use it soon.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />
      <FieldGroup>
        <RhfField form={form} name="email" label="Email">
          <Input
            type="email"
            autoComplete="email"
            placeholder="you@company.com"
          />
        </RhfField>
      </FieldGroup>
      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <SendIcon data-icon="inline-start" />
        )}
        Send reset link
      </Button>
    </form>
  )
}

function ForgotPasswordPage() {
  return (
    <AuthCard
      title="Reset your password"
      description="We will email you a reset link."
      footer={
        <span>
          Remembered it?{" "}
          <Link
            to="/login"
            className="text-foreground underline underline-offset-4"
          >
            Back to sign in
          </Link>
        </span>
      }
    >
      <ForgotPasswordForm />
    </AuthCard>
  )
}
