import { Trash2Icon, UsersIcon } from "lucide-react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
  useRemoveMember,
  useUpdateMemberRole,
  type Member,
} from "@/features/org/api"
import { ROLE_ITEMS, type OrgRole } from "@/features/org/roles"

function initials(name: string, email: string) {
  const source = name?.trim() || email || "?"
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
}

export function MembersTable({
  members,
  isLoading,
  isAdmin,
  currentUserId,
}: {
  members: Member[]
  isLoading?: boolean
  isAdmin: boolean
  currentUserId?: string
}) {
  const updateRole = useUpdateMemberRole()
  const removeMember = useRemoveMember()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (members.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <UsersIcon />
          </EmptyMedia>
          <EmptyTitle>No members yet</EmptyTitle>
          <EmptyDescription>
            Invite a teammate to start working together.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          {isAdmin ? (
            <TableHead className="w-0 text-right">Actions</TableHead>
          ) : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((member) => {
          const isSelf = member.user_id === currentUserId
          return (
            <TableRow key={member.user_id}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <Avatar className="size-7 shrink-0">
                    {member.avatar_url ? (
                      <AvatarImage src={member.avatar_url} alt="" />
                    ) : null}
                    <AvatarFallback>
                      {initials(member.full_name, member.email)}
                    </AvatarFallback>
                  </Avatar>
                  <span className="truncate">{member.full_name}</span>
                  {isSelf ? <Badge variant="outline">You</Badge> : null}
                </div>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {member.email}
              </TableCell>
              <TableCell>
                {isAdmin ? (
                  <Select
                    items={ROLE_ITEMS}
                    value={member.role}
                    // The backend rejects self-demotion with cannot_change_own_role.
                    disabled={isSelf || updateRole.isPending}
                    onValueChange={(role: OrgRole | null) => {
                      if (role && role !== member.role) {
                        updateRole.mutate({ userId: member.user_id, role })
                      }
                    }}
                  >
                    <SelectTrigger
                      size="sm"
                      aria-label={`Role for ${member.email}`}
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {ROLE_ITEMS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                ) : (
                  <Badge variant="secondary" className="capitalize">
                    {member.role}
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                {/* The raw enum was printed straight out, so this cell read
                    "active" in lower case beside every other pill in the app,
                    which is written as prose. */}
                <Badge
                  variant={member.status === "active" ? "success" : "outline"}
                >
                  {member.status === "active" ? "Active" : "Disabled"}
                </Badge>
              </TableCell>
              {isAdmin ? (
                <TableCell className="text-right">
                  <AlertDialog>
                    <AlertDialogTrigger
                      render={
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          disabled={isSelf}
                          aria-label={`Remove ${member.email}`}
                        />
                      }
                    >
                      <Trash2Icon />
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>
                          Remove {member.full_name || member.email}?
                        </AlertDialogTitle>
                        <AlertDialogDescription>
                          They lose access to this organization immediately. You
                          can invite them again later.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => removeMember.mutate(member)}
                        >
                          Remove
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </TableCell>
              ) : null}
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
