import { createFileRoute, Link } from "@tanstack/react-router"
import { MailCheckIcon, UserPlusIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { AuthCard } from "@/components/layout/AuthCard"
import { Button } from "@/components/ui/button"
import { FieldDescription, FieldGroup, FieldSeparator } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { GoogleButton } from "@/features/auth/GoogleButton"
import { PasswordStrength } from "@/features/auth/PasswordStrength"
import { PASSWORD_MIN_LENGTH, PASSWORD_RULE } from "@/features/auth/password"
import { ResendVerificationButton } from "@/features/auth/ResendVerificationButton"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

const searchSchema = z.object({
  /** Set when arriving from an invitation so we can prefill and come back. */
  email: z.string().optional(),
  redirect: z.string().optional(),
})

export const Route = createFileRoute("/_auth/register")({
  validateSearch: searchSchema,
  component: RegisterPage,
})

const registerSchema = z.object({
  full_name: z.string().trim().min(1, "Your name is required").max(200),
  email: z
    .string()
    .trim()
    .min(1, "Email is required")
    .email("Enter a valid email"),
  password: z.string().min(PASSWORD_MIN_LENGTH, PASSWORD_RULE),
})

type RegisterValues = z.infer<typeof registerSchema>

export function RegisterForm({
  defaultEmail = "",
  redirect,
}: {
  defaultEmail?: string
  redirect?: string
}) {
  const [error, setError] = React.useState<ApiError | null>(null)
  const [sentTo, setSentTo] = React.useState<string | null>(null)

  const form = useZodForm({
    schema: registerSchema,
    defaultValues: { full_name: "", email: defaultEmail, password: "" },
  })

  const password = form.watch("password")

  const onSubmit = form.handleSubmit(async (values: RegisterValues) => {
    setError(null)
    try {
      await unwrap(
        api.POST("/api/v1/auth/register", {
          body: {
            email: values.email,
            password: values.password,
            full_name: values.full_name,
          },
        })
      )
      setSentTo(values.email)
    } catch (err) {
      if (!isApiError(err)) throw err
      const attached = applyFieldErrors(form, err, [
        "email",
        "password",
        "full_name",
      ])
      if (!attached) setError(err)
    }
  })

  if (sentTo) {
    return (
      <div className="flex flex-col items-start gap-4" data-testid="check-inbox">
        <MailCheckIcon aria-hidden="true" className="size-8 text-primary" />
        <div className="flex flex-col gap-1">
          <p className="font-medium">Check your inbox</p>
          <p className="text-sm text-muted-foreground">
            We sent a verification link to{" "}
            <span className="font-medium text-foreground">{sentTo}</span>. Open
            it to finish setting up your account.
          </p>
        </div>
        <ResendVerificationButton email={sentTo} />
        <FieldDescription>
          Wrong address?{" "}
          <button
            type="button"
            className="underline underline-offset-4"
            onClick={() => setSentTo(null)}
          >
            Go back and edit it
          </button>
          .
        </FieldDescription>
      </div>
    )
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />

      <FieldGroup>
        <RhfField form={form} name="full_name" label="Full name">
          <Input autoComplete="name" placeholder="Ada Lovelace" />
        </RhfField>
        <RhfField form={form} name="email" label="Work email">
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
          description={PASSWORD_RULE}
          below={<PasswordStrength password={password ?? ""} />}
        >
          <Input type="password" autoComplete="new-password" />
        </RhfField>
      </FieldGroup>

      <FieldDescription>
        By creating an account you agree to the TenderSense Terms of Service and
        Privacy Policy.
      </FieldDescription>

      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <UserPlusIcon data-icon="inline-start" />
        )}
        Create account
      </Button>

      <FieldSeparator>or</FieldSeparator>
      <GoogleButton
        redirect={redirect ?? "/app/dashboard"}
        label="Sign up with Google"
      />
    </form>
  )
}

function RegisterPage() {
  const { email, redirect } = Route.useSearch()

  return (
    <AuthCard
      title="Create your account"
      description="Start tracking tenders in minutes."
      footer={
        <span>
          Already have an account?{" "}
          <Link
            to="/login"
            className="text-foreground underline underline-offset-4"
          >
            Sign in
          </Link>
        </span>
      }
    >
      <RegisterForm defaultEmail={email ?? ""} redirect={redirect} />
    </AuthCard>
  )
}
