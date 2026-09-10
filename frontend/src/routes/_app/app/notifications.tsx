import { createFileRoute } from "@tanstack/react-router"
import { CheckCheckIcon, SettingsIcon } from "lucide-react"
import { Link } from "@tanstack/react-router"
import * as React from "react"

import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import { NotificationList } from "@/features/notifications/NotificationList"
import {
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useUnreadCount,
} from "@/features/notifications/api"

export const Route = createFileRoute("/_app/app/notifications")({
  component: NotificationsPage,
})

function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = React.useState(false)
  const notifications = useNotifications(unreadOnly)
  const unread = useUnreadCount()
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()
  const unreadTotal = unread.data?.unread ?? 0

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Strong matches, amended notices, and deadlines on bids you are working on."
      />

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={unreadOnly ? "outline" : "secondary"}
              onClick={() => setUnreadOnly(false)}
            >
              All
            </Button>
            <Button
              size="sm"
              variant={unreadOnly ? "secondary" : "outline"}
              onClick={() => setUnreadOnly(true)}
            >
              Unread{unreadTotal ? ` (${unreadTotal})` : ""}
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending || unreadTotal === 0}
            >
              <CheckCheckIcon /> Mark all read
            </Button>
            <Button
              size="sm"
              variant="outline"
              render={<Link to="/app/settings/notifications" />}
            >
              <SettingsIcon /> Settings
            </Button>
          </div>
        </div>

        <ApiErrorAlert error={notifications.error} />
        <NotificationList
          notifications={notifications.data ?? []}
          isLoading={notifications.isPending}
          onRead={(id) => markRead.mutate(id)}
        />
      </div>
    </>
  )
}
