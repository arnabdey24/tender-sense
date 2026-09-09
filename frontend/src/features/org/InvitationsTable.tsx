import { MailIcon, RotateCwIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import {
  useResendInvitation,
  useRevokeInvitation,
  type Invitation,
} from "@/features/org/api"

function formatExpiry(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

export function InvitationsTable({
  invitations,
  isLoading,
  isAdmin,
}: {
  invitations: Invitation[]
  isLoading?: boolean
  isAdmin: boolean
}) {
  const resend = useResendInvitation()
  const revoke = useRevokeInvitation()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  const pending = invitations.filter((i) => i.status === "pending")

  if (pending.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <MailIcon />
          </EmptyMedia>
          <EmptyTitle>No pending invitations</EmptyTitle>
          <EmptyDescription>
            Invitations you send will appear here until they are accepted.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Email</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Expires</TableHead>
          {isAdmin ? (
            <TableHead className="w-0 text-right">Actions</TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {pending.map((invitation) => (
          <TableRow key={invitation.id}>
            <TableCell>{invitation.email}</TableCell>
            <TableCell>
              <Badge variant="secondary">{invitation.role}</Badge>
            </TableCell>
            <TableCell className="text-muted-foreground">
              {formatExpiry(invitation.expires_at)}
            </TableCell>
            {isAdmin ? (
              <TableCell>
                <div className="flex justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={resend.isPending}
                    onClick={() => resend.mutate(invitation)}
                  >
                    <RotateCwIcon data-icon="inline-start" />
                    Resend
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={revoke.isPending}
                    onClick={() => revoke.mutate(invitation)}
                    aria-label={`Revoke invitation for ${invitation.email}`}
                  >
                    <XIcon data-icon="inline-start" />
                    Revoke
                  </Button>
                </div>
              </TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
