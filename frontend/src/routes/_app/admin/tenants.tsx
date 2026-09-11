import { createFileRoute } from "@tanstack/react-router"
import * as React from "react"
import { SearchIcon } from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import {
  useAdminOrganizations,
  useAdminUsers,
  useUpdateUser,
} from "@/features/admin/api"
import { useAuthStore } from "@/lib/auth/store"
import { countryName } from "@/lib/data/locale"
import { timeAgo } from "@/lib/data/time"

export const Route = createFileRoute("/_app/admin/tenants")({
  component: TenantsPage,
})

/** A search box that only asks the server once the typing settles. */
function useDebounced(value: string, delay = 300): string {
  const [settled, setSettled] = React.useState(value)

  React.useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])

  return settled
}

function Organizations({ q }: { q: string }) {
  const orgs = useAdminOrganizations(q || undefined)

  if (orgs.isPending) return <Skeleton className="h-32 w-full" />
  if (!orgs.data) return <ApiErrorAlert error={orgs.error} />
  if (!orgs.data.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {q ? "No organization matches that." : "No organizations yet."}
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table density="compact">
        <TableHeader>
          <TableRow>
            <TableHead>Organization</TableHead>
            <TableHead numeric>People</TableHead>
            <TableHead>Last decision</TableHead>
            <TableHead>Joined</TableHead>
            <TableHead>State</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {orgs.data.map((org) => (
            <TableRow key={org.id}>
              <TableCell>
                <div className="font-medium">{org.name}</div>
                {/* Country was its own column and blank on four rows in five.
                    It joins the identifying line, where an absent value costs
                    nothing instead of a column of dashes. */}
                <div className="text-xs text-muted-foreground">
                  {[org.slug, org.country ? countryName(org.country) : null]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
              </TableCell>
              <TableCell numeric>{org.members}</TableCell>
              {/*
                A tenant with people in it and no decisions ever recorded is
                the shape of one that signed up and bounced — worth seeing
                without opening each one.
              */}
              <TableCell className="text-sm text-muted-foreground">
                {org.last_activity_at ? timeAgo(org.last_activity_at) : "Never"}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {timeAgo(org.created_at)}
              </TableCell>
              {/*
                The state an operator is actually looking for. A tenant with
                nobody in it, or with people and no decision ever recorded, is
                the shape of one that signed up and bounced — and that was
                previously only visible by reading two columns and doing the
                arithmetic. Said in a word, and never in colour alone.
              */}
              <TableCell>
                {!org.is_active ? (
                  <Badge variant="destructive">Suspended</Badge>
                ) : org.members === 0 ? (
                  <Badge variant="outline">Empty</Badge>
                ) : org.last_activity_at ? (
                  <Badge variant="success">Active</Badge>
                ) : (
                  <Badge variant="warning">Dormant</Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function Accounts({ q }: { q: string }) {
  const users = useAdminUsers(q || undefined)
  const update = useUpdateUser()
  const me = useAuthStore((state) => state.user)

  if (users.isPending) return <Skeleton className="h-32 w-full" />
  if (!users.data) return <ApiErrorAlert error={users.error} />
  if (!users.data.length) {
    return (
      <p className="text-sm text-muted-foreground">
        {q ? "No account matches that." : "No accounts yet."}
      </p>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table density="compact">
        <TableHeader>
          <TableRow>
            <TableHead>Account</TableHead>
            <TableHead>Organizations</TableHead>
            <TableHead>Last signed in</TableHead>
            <TableHead className="text-right">Access</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.data.map((user) => {
            const self = user.id === me?.id
            return (
              <TableRow key={user.id}>
                <TableCell>
                  <div className="font-medium">{user.full_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {user.email}
                    {!user.email_verified && " · unverified"}
                  </div>
                </TableCell>
                <TableCell className="text-sm">
                  {user.organizations?.length
                    ? user.organizations.join(", ")
                    : "—"}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {user.last_login_at ? timeAgo(user.last_login_at) : "Never"}
                </TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-2">
                    {user.is_superuser && <Badge variant="secondary">Staff</Badge>}
                    {!user.is_active && (
                      <Badge variant="destructive">Suspended</Badge>
                    )}
                    {/*
                      Not on yourself. Revoking your own access, or suspending
                      the account you are signed in as, is the one change here
                      that cannot be undone from this page afterwards — and on a
                      single-VM deployment there may be no other operator.
                    */}
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={self || update.isPending}
                      title={self ? "You cannot change your own access" : undefined}
                      onClick={() =>
                        update.mutate({
                          userId: user.id,
                          is_active: !user.is_active,
                        })
                      }
                    >
                      {user.is_active ? "Suspend" : "Restore"}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={self || update.isPending}
                      title={self ? "You cannot change your own access" : undefined}
                      onClick={() =>
                        update.mutate({
                          userId: user.id,
                          is_superuser: !user.is_superuser,
                        })
                      }
                    >
                      {user.is_superuser ? "Revoke staff" : "Make staff"}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

function TenantsPage() {
  const [draft, setDraft] = React.useState("")
  const q = useDebounced(draft)

  return (
    <div className="flex flex-col gap-8">
      <div className="relative max-w-sm">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search organizations and accounts"
          aria-label="Search organizations and accounts"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </div>

      <ConsoleSection
        title="Organizations"
        caption="Every tenant on this deployment. Nothing here crosses the boundary between them — these are counts and dates, not their matches or decisions."
      >
        <Organizations q={q} />
      </ConsoleSection>

      <ConsoleSection
        title="Accounts"
        caption="Everyone who can sign in. Staff reach this console; members do not."
      >
        <Accounts q={q} />
      </ConsoleSection>
    </div>
  )
}
