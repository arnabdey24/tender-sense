import { createFileRoute, Link } from "@tanstack/react-router"
import { SatelliteDishIcon } from "lucide-react"

import { PageHeader } from "@/components/layout/PageHeader"
import { PageBody, PageSection } from "@/components/layout/PageSection"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PortalSyncPanel } from "@/features/sources/PortalSync"
import { SourceHealthBadge } from "@/features/sources/SourceHealthBadge"
import { useSources } from "@/features/sources/api"
import { countryName } from "@/lib/data/locale"
import { useIsSuperuser } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/sources")({
  component: SourcesSettingsPage,
})

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "Never"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "Never"
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

function SourceTable() {
  const sources = useSources()

  if (sources.isPending) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (!sources.data?.length) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <SatelliteDishIcon />
          </EmptyMedia>
          <EmptyTitle>No portals yet</EmptyTitle>
          <EmptyDescription>
            Notices arrive once a portal is registered. Ask your TenderSense
            operator to add one.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Portal</TableHead>
            <TableHead>Country</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last checked</TableHead>
            <TableHead>Last success</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.data.map((source) => (
            <TableRow key={source.id}>
              <TableCell>
                <div className="font-medium">{source.name}</div>
                <div className="text-xs text-muted-foreground">
                  {source.code}
                  {!source.enabled && " · paused"}
                </div>
              </TableCell>
              <TableCell>{countryName(source.country) || "—"}</TableCell>
              <TableCell>
                <SourceHealthBadge
                  health={source.health}
                  enabled={source.enabled}
                />
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatWhen(source.last_run_at)}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {formatWhen(source.last_success_at)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function SourcesSettingsPage() {
  const isSuperuser = useIsSuperuser()

  return (
    <>
      <PageHeader
        title="Sources"
        description="The procurement portals TenderSense watches on your behalf."
      />

      <PageBody>
        <PageSection
          title="Portals"
          caption="The tender pool is shared, so every portal here feeds every organization's matches. A portal marked degraded or down means notices may be missing from your feed."
        >
          <SourceTable />
          {/*
            Not an operator control, and no longer filed as one. The schedule
            visits the portals four times a day, which leaves the two moments
            that matter to a member with nothing to press: the first pull on a
            deployment whose pool is still empty, and the hour after a portal
            publishes something they already know is there. Neither person is
            usually platform staff, and telling them to find someone who is was
            the whole of the previous answer.
          */}
          <PortalSyncPanel className="mt-4" />
        </PageSection>

        {/*
          The operator controls used to sit here behind a superuser check, which
          made one page serve two readers and neither of them well: a member
          scrolled past four staff-only blocks, and staff found portal
          registration nowhere at all. Configuration, registration and run
          history are in the operations console now; this page is what a member
          came for.
        */}
        {isSuperuser && (
          <PageSection
            title="Operator controls"
            caption="Registering a portal, changing its selectors and replaying stored pages live in the operations console."
          >
            <Link
              to="/admin/sources"
              className="text-sm font-medium text-primary hover:underline"
            >
              Open Portals in Operations
            </Link>
          </PageSection>
        )}
      </PageBody>
    </>
  )
}
