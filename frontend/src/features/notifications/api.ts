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

export type NotificationItem = components["schemas"]["NotificationRead"]
export type NotificationSettings =
  components["schemas"]["NotificationSettingsRead"]
export type NotificationSettingsUpdate =
  components["schemas"]["NotificationSettingsUpdate"]
export type Recipient = components["schemas"]["RecipientRead"]
export type NotificationType = components["schemas"]["NotificationType"]

/** Human copy for the codes this surface can return. */
const ERROR_TITLES: Record<string, string> = {
  recipient_exists: "That address is already a recipient",
  already_verified: "That address is already confirmed",
  recipient_not_found: "That recipient no longer exists",
  admin_required: "Admins only",
  rate_limited: "Too many requests",
  invalid_token: "That link is not valid",
}

export function toastApiError(error: ApiError, fallbackTitle: string): void {
  toast.add({
    type: "error",
    title: ERROR_TITLES[error.code] ?? fallbackTitle,
    description: error.message,
  })
}

export function useNotifications(unreadOnly = false) {
  return useQuery<NotificationItem[], ApiError>({
    queryKey: qk.notifications.list(unreadOnly),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/notifications", {
          params: { query: { unread_only: unreadOnly, limit: 50 } },
        })
      ),
  })
}

/**
 * Polled rather than pushed. A badge that is a minute stale costs nothing; a
 * WebSocket that has to survive a proxy, a sleeping laptop and a token refresh
 * costs a great deal.
 */
export function useUnreadCount(enabled = true) {
  return useQuery<{ unread: number }, ApiError>({
    queryKey: qk.notifications.unreadCount(),
    enabled,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    queryFn: () => unwrap(api.GET("/api/v1/notifications/unread-count")),
  })
}

export function useMarkRead(): UseMutationResult<unknown, ApiError, string> {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.POST("/api/v1/notifications/{notification_id}/read", {
          params: { path: { notification_id: id } },
        })
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications.all() })
    },
  })
}

export function useMarkAllRead() {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, void>({
    mutationFn: () => unwrap(api.POST("/api/v1/notifications/read-all")),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: qk.notifications.all() })
    },
    onError: (error) => toastApiError(error, "Could not clear notifications"),
  })
}

export function useNotificationSettings() {
  return useQuery<NotificationSettings, ApiError>({
    queryKey: qk.notifications.settings(),
    queryFn: () => unwrap(api.GET("/api/v1/notification-settings")),
  })
}

export function useUpdateNotificationSettings() {
  const queryClient = useQueryClient()
  return useMutation<
    NotificationSettings,
    ApiError,
    NotificationSettingsUpdate
  >({
    mutationFn: (body) =>
      unwrap(api.PUT("/api/v1/notification-settings", { body })),
    onSuccess: (updated) => {
      queryClient.setQueryData(qk.notifications.settings(), updated)
      toast.add({ type: "success", title: "Notification settings saved" })
    },
    onError: (error) => toastApiError(error, "Could not save the settings"),
  })
}

export function useRecipients() {
  return useQuery<Recipient[], ApiError>({
    queryKey: qk.notifications.recipients(),
    queryFn: () => unwrap(api.GET("/api/v1/notification-recipients")),
  })
}

export function useAddRecipient() {
  const queryClient = useQueryClient()
  return useMutation<
    Recipient,
    ApiError,
    { email: string; name?: string | null }
  >({
    mutationFn: (body) =>
      unwrap(
        api.POST("/api/v1/notification-recipients", {
          body: { email: body.email, name: body.name || null, types: [] },
        })
      ),
    onSuccess: (recipient) => {
      toast.add({
        type: "success",
        title: "Confirmation sent",
        description: `${recipient.email} receives nothing until someone there confirms it.`,
      })
      void queryClient.invalidateQueries({
        queryKey: qk.notifications.recipients(),
      })
    },
    onError: (error) => toastApiError(error, "Could not add that address"),
  })
}

export function useRemoveRecipient() {
  const queryClient = useQueryClient()
  return useMutation<unknown, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.DELETE("/api/v1/notification-recipients/{recipient_id}", {
          params: { path: { recipient_id: id } },
        })
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: qk.notifications.recipients(),
      })
    },
    onError: (error) => toastApiError(error, "Could not remove that address"),
  })
}

export function useResendVerification() {
  const queryClient = useQueryClient()
  return useMutation<Recipient, ApiError, string>({
    mutationFn: (id) =>
      unwrap(
        api.POST("/api/v1/notification-recipients/{recipient_id}/resend", {
          params: { path: { recipient_id: id } },
        })
      ),
    onSuccess: (recipient) => {
      toast.add({
        type: "success",
        title: "Confirmation resent",
        description: `A fresh link is on its way to ${recipient.email}. The old one no longer works.`,
      })
      void queryClient.invalidateQueries({
        queryKey: qk.notifications.recipients(),
      })
    },
    onError: (error) => toastApiError(error, "Could not resend the link"),
  })
}

export function useSendTestEmail() {
  return useMutation<{ to_email: string }, ApiError, void>({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/notification-settings/test-email", { body: {} })
      ),
    onSuccess: (result) => {
      toast.add({
        type: "success",
        title: "Test message queued",
        description: `Sent to ${result.to_email}. If it lands in spam, fix that before the first real alert.`,
      })
    },
    onError: (error) => toastApiError(error, "Could not send a test message"),
  })
}
