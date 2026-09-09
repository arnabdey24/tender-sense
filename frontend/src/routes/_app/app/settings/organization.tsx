import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { OrganizationForm } from "@/features/org/OrganizationForm"
import { useCurrentOrg } from "@/features/org/api"
import { countryName } from "@/lib/data/locale"
import { useIsOrgAdmin } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/organization")({
  component: OrganizationSettingsPage,
})

function ReadOnlyOrg() {
  const org = useCurrentOrg()
  if (!org.data) return null
  return (
    <dl className="grid gap-4 sm:grid-cols-2">
      {[
        ["Name", org.data.name],
        ["Country", countryName(org.data.country) || "—"],
        ["Website", org.data.website || "—"],
        ["Timezone", org.data.timezone],
        ["Plan", org.data.plan],
      ].map(([label, value]) => (
        <div key={label} className="flex flex-col gap-0.5">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="text-sm font-medium break-words">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function OrganizationSettingsPage() {
  const isAdmin = useIsOrgAdmin()
  const org = useCurrentOrg()

  return (
    <>
      <PageHeader
        title="Organization"
        description="Your company details, used across matching and notifications."
      />

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>
            {isAdmin
              ? "Only admins can change these."
              : "Ask an admin to change these."}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ApiErrorAlert error={org.error} />
          {org.isPending ? (
            <div className="flex flex-col gap-3">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : org.data && isAdmin ? (
            // Remounts when the organization changes, so the form's default
            // values follow an org switch instead of sticking to the first one.
            <OrganizationForm key={org.data.id} org={org.data} />
          ) : (
            <ReadOnlyOrg />
          )}
        </CardContent>
      </Card>
    </>
  )
}
