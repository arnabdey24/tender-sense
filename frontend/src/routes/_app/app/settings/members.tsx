import { createFileRoute } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { InvitationsTable } from "@/features/org/InvitationsTable"
import { InviteDialog } from "@/features/org/InviteDialog"
import { MembersTable } from "@/features/org/MembersTable"
import { useInvitations, useMembers } from "@/features/org/api"
import { useAuthStore, useIsOrgAdmin } from "@/lib/auth/store"

export const Route = createFileRoute("/_app/app/settings/members")({
  component: MembersPage,
})

export function MembersPanel() {
  const isAdmin = useIsOrgAdmin()
  const currentUserId = useAuthStore((s) => s.user?.id)
  const members = useMembers()
  // Only admins may list invitations — do not fire a call members will 403 on.
  const invitations = useInvitations(isAdmin)

  return (
    <>
      <PageHeader
        title="Members"
        description="Who has access to this organization."
        actions={isAdmin ? <InviteDialog /> : undefined}
      />

      <Card>
        <CardHeader>
          <CardTitle>Team</CardTitle>
          <CardDescription>
            {members.data
              ? `${members.data.total} member${members.data.total === 1 ? "" : "s"}`
              : "Loading members…"}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ApiErrorAlert error={members.error} />
          <MembersTable
            members={members.data?.items ?? []}
            isLoading={members.isPending}
            isAdmin={isAdmin}
            currentUserId={currentUserId}
          />
        </CardContent>
      </Card>

      {isAdmin ? (
        <Card>
          <CardHeader>
            <CardTitle>Pending invitations</CardTitle>
            <CardDescription>
              Links that have been emailed but not yet accepted.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <ApiErrorAlert error={invitations.error} />
            <InvitationsTable
              invitations={invitations.data ?? []}
              isLoading={invitations.isPending}
              isAdmin={isAdmin}
            />
          </CardContent>
        </Card>
      ) : null}
    </>
  )
}

function MembersPage() {
  return <MembersPanel />
}
