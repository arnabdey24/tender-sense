import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute, redirect, useNavigate } from "@tanstack/react-router"
import { Building2Icon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { StringCombobox } from "@/components/form/StringCombobox"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { refreshSession } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"
import { COUNTRIES, guessTimezone, timezoneOptions } from "@/lib/data/locale"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

export const Route = createFileRoute("/_app/onboarding/")({
  beforeLoad: () => {
    // Onboarding is only for accounts without an organization.
    if (useAuthStore.getState().memberships.length > 0) {
      throw redirect({ to: "/app/dashboard" })
    }
  },
  component: OnboardingPage,
})

const schema = z.object({
  name: z
    .string()
    .trim()
    .min(2, "Use at least 2 characters")
    .max(200, "Keep it under 200 characters"),
  country: z.string().optional(),
  website: z
    .string()
    .trim()
    .max(500)
    .optional()
    .refine(
      (v) => !v || /^https?:\/\/\S+\.\S+/.test(v),
      "Include the full URL, e.g. https://example.com"
    ),
  description: z.string().trim().max(2000).optional(),
  timezone: z.string().trim().min(1, "Pick a timezone"),
})

export function CreateOrganizationForm({
  onCreated,
}: {
  onCreated?: () => void
}) {
  const queryClient = useQueryClient()
  const [error, setError] = React.useState<ApiError | null>(null)
  const timezones = React.useMemo(() => timezoneOptions(), [])

  const form = useZodForm({
    schema,
    defaultValues: {
      name: "",
      country: "",
      website: "",
      description: "",
      timezone: guessTimezone(),
    },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await unwrap(
        api.POST("/api/v1/orgs", {
          body: {
            name: values.name,
            country: values.country || null,
            website: values.website || null,
            description: values.description || null,
            timezone: values.timezone || null,
          },
        })
      )
      // Critical: the current access token has no org claim yet, so every
      // org-scoped call would 403 with `no_active_org` until we refresh.
      await refreshSession(queryClient)
      toast.add({
        type: "success",
        title: "Organization created",
        description: `${values.name} is ready to go.`,
      })
      onCreated?.()
    } catch (err) {
      if (!isApiError(err)) throw err
      if (
        !applyFieldErrors(form, err, [
          "name",
          "country",
          "website",
          "description",
          "timezone",
        ])
      ) {
        setError(err)
      }
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />
      <FieldGroup>
        <RhfField form={form} name="name" label="Organization name">
          <Input placeholder="Acme Engineering Ltd" autoComplete="organization" />
        </RhfField>

        <RhfField
          form={form}
          name="country"
          label="Country"
          description="Where you mainly bid."
        >
          {(control) => (
            <StringCombobox
              id={control.id}
              name={control.name}
              items={COUNTRIES}
              value={(control.value as string) ?? ""}
              onValueChange={control.onChange}
              onBlur={control.onBlur}
              placeholder="Select a country"
              emptyText="No country found."
              aria-invalid={control["aria-invalid"]}
              aria-describedby={control["aria-describedby"]}
            />
          )}
        </RhfField>

        <RhfField form={form} name="website" label="Website">
          <Input type="url" placeholder="https://acme.com" />
        </RhfField>

        <RhfField
          form={form}
          name="description"
          label="What do you do?"
          description="Used to match tenders to your capabilities."
        >
          <Textarea rows={3} placeholder="Civil works, road construction…" />
        </RhfField>

        <RhfField form={form} name="timezone" label="Timezone">
          {(control) => (
            <StringCombobox
              id={control.id}
              name={control.name}
              items={timezones}
              value={(control.value as string) ?? ""}
              onValueChange={control.onChange}
              onBlur={control.onBlur}
              placeholder="Select a timezone"
              emptyText="No timezone found."
              aria-invalid={control["aria-invalid"]}
              aria-describedby={control["aria-describedby"]}
            />
          )}
        </RhfField>
      </FieldGroup>

      <Button type="submit" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <Building2Icon data-icon="inline-start" />
        )}
        Create organization
      </Button>
    </form>
  )
}

function OnboardingPage() {
  const navigate = useNavigate()

  return (
    <>
      <PageHeader
        title="Welcome to TenderSense"
        description="Set up your organization to start receiving matches."
      />
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Create your organization</CardTitle>
          <CardDescription>
            Everything in TenderSense — tenders, pipeline, teammates — lives
            inside an organization.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <CreateOrganizationForm
            onCreated={() => void navigate({ to: "/app/dashboard" })}
          />
        </CardContent>
      </Card>
    </>
  )
}
