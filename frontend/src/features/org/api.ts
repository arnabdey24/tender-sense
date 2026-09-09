import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query"

import { toast } from "@/components/ui/toast"
import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import type { ApiError } from "@/lib/api/errors"
import { qk } from "@/lib/api/query-keys"
import type { components } from "@/lib/api/schema"

export type Member = components["schemas"]["MemberRead"]
export type Invitation = components["schemas"]["InvitationRead"]
export type OrgRole = components["schemas"]["OrgRole"]
export type MemberPage = components["schemas"]["Page_MemberRead_"]
export type Organization = components["schemas"]["OrganizationRead"]

/** Human copy for the org-management error codes the backend can return. */
const ERROR_TITLES: Record<string, string> = {
  cannot_change_own_role: "You cannot change your own role",
  last_admin: "The organization needs at least one admin",
  admin_required: "Admins only",
  already_member: "That person is already a member",
  not_a_member: "That person is not a member",
  rate_limited: "Too many requests",
}

export function toastApiError(error: ApiError, fallbackTitle: string): void {
  toast.add({
    type: "error",
    title: ERROR_TITLES[error.code] ?? fallbackTitle,
    description: error.message,
  })
}

export function useCurrentOrg() {
  return useQuery<Organization, ApiError>({
    queryKey: qk.orgs.current(),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/current")),
  })
}

export function useMembers(page = 1, pageSize = 50) {
  return useQuery<MemberPage, ApiError>({
    queryKey: qk.orgs.members(page, pageSize),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/orgs/current/members", {
          params: { query: { page, page_size: pageSize } },
        })
      ),
  })
}

export function useInvitations(enabled = true) {
  return useQuery<Invitation[], ApiError>({
    queryKey: qk.orgs.invitations(),
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/orgs/current/invitations")),
  })
}

export function useUpdateMemberRole(): UseMutationResult<
  Member,
  ApiError,
  { userId: string; role: OrgRole }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }) =>
      unwrap(
        api.PATCH("/api/v1/orgs/current/members/{user_id}", {
          params: { path: { user_id: userId } },
          body: { role },
        })
      ),
    onSuccess: (member) => {
      void queryClient.invalidateQueries({ queryKey: qk.orgs.membersAll() })
      toast.add({
        type: "success",
        title: "Role updated",
        description: `${member.full_name || member.email} is now ${member.role}.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not update the role"),
  })
}

export function useRemoveMember(): UseMutationResult<void, ApiError, Member> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (member) =>
      unwrap(
        api.DELETE("/api/v1/orgs/current/members/{user_id}", {
          params: { path: { user_id: member.user_id } },
        })
      ),
    onSuccess: (_data, member) => {
      void queryClient.invalidateQueries({ queryKey: qk.orgs.membersAll() })
      toast.add({
        type: "success",
        title: "Member removed",
        description: `${member.full_name || member.email} no longer has access.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not remove the member"),
  })
}

export function useCreateInvitation(): UseMutationResult<
  Invitation,
  ApiError,
  { email: string; role: OrgRole }
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body) =>
      unwrap(api.POST("/api/v1/orgs/current/invitations", { body })),
    onSuccess: (invitation) => {
      void queryClient.invalidateQueries({ queryKey: qk.orgs.invitations() })
      toast.add({
        type: "success",
        title: "Invitation sent",
        description: `${invitation.email} has been invited as ${invitation.role}.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not send the invitation"),
  })
}

export function useResendInvitation(): UseMutationResult<
  Invitation,
  ApiError,
  Invitation
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (invitation) =>
      unwrap(
        api.POST("/api/v1/orgs/current/invitations/{invitation_id}/resend", {
          params: { path: { invitation_id: invitation.id } },
        })
      ),
    onSuccess: (invitation) => {
      void queryClient.invalidateQueries({ queryKey: qk.orgs.invitations() })
      toast.add({
        type: "success",
        title: "Invitation resent",
        description: `A fresh link is on its way to ${invitation.email}.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not resend the invitation"),
  })
}

export function useRevokeInvitation(): UseMutationResult<
  void,
  ApiError,
  Invitation
> {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (invitation) =>
      unwrap(
        api.DELETE("/api/v1/orgs/current/invitations/{invitation_id}", {
          params: { path: { invitation_id: invitation.id } },
        })
      ),
    onSuccess: (_data, invitation) => {
      void queryClient.invalidateQueries({ queryKey: qk.orgs.invitations() })
      toast.add({
        type: "success",
        title: "Invitation revoked",
        description: `The link sent to ${invitation.email} no longer works.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not revoke the invitation"),
  })
}
