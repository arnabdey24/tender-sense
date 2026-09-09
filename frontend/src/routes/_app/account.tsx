import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { KeyRoundIcon, LogOutIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { FieldDescription, FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { PasswordStrength } from "@/features/auth/PasswordStrength"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { signOut } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

export const Route = createFileRoute("/_app/account")({
  component: AccountPage,
})

const schema = z.object({
  current_password: z.string().optional(),
  new_password: z.string().min(8, "Use at least 8 characters"),
})

export function ChangePasswordForm({
  /**
   * `false` for accounts created through Google that have never set a local
   * password — the backend accepts a null `current_password` for those.
   */
  hasPassword = true,
}: {
  hasPassword?: boolean
}) {
  const [error, setError] = React.useState<ApiError | null>(null)

  const form = useZodForm({
    schema,
    defaultValues: { current_password: "", new_password: "" },
  })

  const newPassword = form.watch("new_password")

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await unwrap(
        api.POST("/api/v1/auth/change-password", {
          body: {
            current_password: values.current_password || null,
            new_password: values.new_password,
          },
        })
      )
      form.reset({ current_password: "", new_password: "" })
      toast.add({
        type: "success",
        title: "Password changed",
        description: "Use your new password the next time you sign in.",
      })
    } catch (err) {
      if (!isApiError(err)) throw err
      if (
        !applyFieldErrors(form, err, ["current_password", "new_password"])
      ) {
        setError(err)
      }
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />
      <FieldGroup>
        {hasPassword ? (
          <RhfField
            form={form}
            name="current_password"
            label="Current password"
            description="Leave blank only if you have never set one (Google sign-in)."
          >
            <Input type="password" autoComplete="current-password" />
          </RhfField>
        ) : null}
        <RhfField
          form={form}
          name="new_password"
          label="New password"
          below={<PasswordStrength password={newPassword ?? ""} />}
        >
          <Input type="password" autoComplete="new-password" />
        </RhfField>
      </FieldGroup>
      <Button
        type="submit"
        className="self-start"
        disabled={form.formState.isSubmitting}
      >
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <KeyRoundIcon data-icon="inline-start" />
        )}
        Change password
      </Button>
    </form>
  )
}

function initials(name?: string, email?: string) {
  const source = name?.trim() || email || "?"
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
}

function AccountPage() {
  const user = useAuthStore((s) => s.user)
  const memberships = useAuthStore((s) => s.memberships)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [signingOut, setSigningOut] = React.useState(false)

  return (
    <>
      <PageHeader
        title="Account"
        description="Your profile and sign-in settings."
      />

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            Details from your TenderSense account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <Avatar className="size-12">
              {user?.avatar_url ? (
                <AvatarImage src={user.avatar_url} alt="" />
              ) : null}
              <AvatarFallback>
                {initials(user?.full_name, user?.email)}
              </AvatarFallback>
            </Avatar>
            <div className="flex min-w-0 flex-col gap-1">
              <span className="font-medium">{user?.full_name}</span>
              <span className="truncate text-sm text-muted-foreground">
                {user?.email}
              </span>
              <div className="flex flex-wrap gap-2">
                <Badge variant={user?.email_verified ? "success" : "warning"}>
                  {user?.email_verified ? "Email verified" : "Email unverified"}
                </Badge>
                <Badge variant="outline">
                  {memberships.length} organization
                  {memberships.length === 1 ? "" : "s"}
                </Badge>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Password</CardTitle>
          <CardDescription>
            Choose a password you do not use anywhere else.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChangePasswordForm hasPassword={user?.has_password ?? true} />
        </CardContent>
      </Card>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
          <CardDescription>
            Signing out everywhere revokes every refresh token, including this
            browser.
          </CardDescription>
        </CardHeader>
        <CardFooter className="flex-col items-start gap-2">
          <Button
            variant="destructive"
            disabled={signingOut}
            onClick={async () => {
              setSigningOut(true)
              await signOut({ everywhere: true, queryClient })
              await navigate({ to: "/login" })
            }}
          >
            {signingOut ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <LogOutIcon data-icon="inline-start" />
            )}
            Sign out of all devices
          </Button>
          <FieldDescription>
            You will need to sign in again on every device.
          </FieldDescription>
        </CardFooter>
      </Card>
    </>
  )
}
