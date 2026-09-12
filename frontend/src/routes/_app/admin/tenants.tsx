import { createFileRoute } from "@tanstack/react-router"
import * as React from "react"
import { Building2Icon, SearchIcon, UsersIcon } from "lucide-react"

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
    <Table density="compact" fixed>
      <TableHeader>
        <TableRow>
          <TableHead>Organization</TableHead>
          <TableHead numeric className="w-24">
            People
          </TableHead>
          <TableHead className="w-32">Last decision</TableHead>
          <TableHead className="w-28">Joined</TableHead>
          <TableHead className="w-28">State</TableHead>
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
    <Table density="compact" fixed>
      <TableHeader>
        <TableRow>
          <TableHead>Account</TableHead>
          <TableHead>Organizations</TableHead>
          <TableHead className="w-32">Last signed in</TableHead>
          <TableHead className="w-[22rem] text-right">Access</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.data.map((user) => {
          const self = user.id === me?.id
          return (
            <TableRow key={user.id}>
              {/*
                `max-w-0` is what makes truncation work inside a fixed table:
                without it the cell sizes to its content and one unbroken
                string — a name somebody pasted a keyboard into — pushes every
                other column off the page. The full value stays reachable as a
                tooltip rather than being lost.
              */}
              <TableCell className="max-w-0">
                <div className="truncate font-medium" title={user.full_name}>
                  {user.full_name}
                </div>
                <div
                  className="truncate text-xs text-muted-foreground"
                  title={user.email}
                >
                  {user.email}
                  {!user.email_verified && " · unverified"}
                </div>
              </TableCell>
              <TableCell className="max-w-0 text-sm">
                <div
                  className="truncate"
                  title={user.organizations?.join(", ") || undefined}
                >
                  {user.organizations?.length
                    ? user.organizations.join(", ")
                    : "—"}
                </div>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {user.last_login_at ? timeAgo(user.last_login_at) : "Never"}
              </TableCell>
              <TableCell>
                <div className="flex items-center justify-end gap-2">
                  {user.is_superuser && (
                    <Badge variant="secondary">Staff</Badge>
                  )}
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
                    title={
                      self ? "You cannot change your own access" : undefined
                    }
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
                    title={
                      self ? "You cannot change your own access" : undefined
                    }
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
        icon={Building2Icon}
        caption="Every tenant on this deployment. Nothing here crosses the boundary between them — these are counts and dates, not their matches or decisions."
      >
        <Organizations q={q} />
      </ConsoleSection>

      <ConsoleSection
        title="Accounts"
        icon={UsersIcon}
        caption="Everyone who can sign in. Staff reach this console; members do not."
      >
        <Accounts q={q} />
      </ConsoleSection>
    </div>
  )
}
