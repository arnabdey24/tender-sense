import { useQueryClient } from "@tanstack/react-query"
import { SaveIcon } from "lucide-react"
import * as React from "react"
import { z } from "zod"

import { CountryCombobox } from "@/components/form/CountryCombobox"
import { StringCombobox } from "@/components/form/StringCombobox"
import { Button } from "@/components/ui/button"
import { FieldGroup } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import type { Organization } from "@/features/org/api"
import { applyFieldErrors, unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { isApiError, type ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import { refreshSession } from "@/lib/auth/session"
import { timezoneOptions } from "@/lib/data/locale"
import { RhfField } from "@/lib/forms/RhfField"
import { useZodForm } from "@/lib/forms/useZodForm"

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

const FIELDS = ["name", "country", "website", "description", "timezone"]

/**
 * Edit the current organization. `PATCH /orgs/current` is admin-only, so
 * callers must not render this for members.
 */
export function OrganizationForm({ org }: { org: Organization }) {
  const queryClient = useQueryClient()
  const [error, setError] = React.useState<ApiError | null>(null)
  const timezones = React.useMemo(() => timezoneOptions(), [])

  const form = useZodForm({
    schema,
    defaultValues: {
      name: org.name,
      country: org.country ?? "",
      website: org.website ?? "",
      description: org.description ?? "",
      timezone: org.timezone,
    },
  })

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await unwrap(
        api.PATCH("/api/v1/orgs/current", {
          body: {
            name: values.name,
            country: values.country || null,
            website: values.website || null,
            description: values.description || null,
            timezone: values.timezone || null,
          },
        })
      )
      await queryClient.invalidateQueries({ queryKey: qk.orgs.current() })
      // The sidebar and header read the org name off the session rather than
      // this query, so a rename only shows up after the token is reissued.
      await refreshSession(queryClient)
      form.reset(values)
      toast.add({ type: "success", title: "Organization updated" })
    } catch (err) {
      if (!isApiError(err)) throw err
      if (!applyFieldErrors(form, err, FIELDS)) setError(err)
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
      <ApiErrorAlert error={error} />
      <FieldGroup>
        <RhfField form={form} name="name" label="Organization name">
          <Input autoComplete="organization" />
        </RhfField>

        <RhfField
          form={form}
          name="country"
          label="Country"
          description="Where you mainly bid."
        >
          {(control) => (
            <CountryCombobox
              id={control.id}
              name={control.name}
              value={(control.value as string) ?? ""}
              onValueChange={control.onChange}
              onBlur={control.onBlur}
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

        <RhfField
          form={form}
          name="timezone"
          label="Timezone"
          description="Digest times and deadline countdowns use this zone."
        >
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

      <Button
        type="submit"
        className="self-start"
        disabled={form.formState.isSubmitting || !form.formState.isDirty}
      >
        {form.formState.isSubmitting ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <SaveIcon data-icon="inline-start" />
        )}
        Save changes
      </Button>
    </form>
  )
}
