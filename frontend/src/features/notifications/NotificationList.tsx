import { Link } from "@tanstack/react-router"
import {
  AlertTriangleIcon,
  BellIcon,
  CalendarClockIcon,
  InfoIcon,
  RefreshCwIcon,
  TargetIcon,
} from "lucide-react"

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
import type {
  NotificationItem,
  NotificationType,
} from "@/features/notifications/api"

const ICONS: Record<NotificationType, typeof BellIcon> = {
  instant_match: TargetIcon,
  daily_digest: BellIcon,
  deadline_reminder: CalendarClockIcon,
  tender_updated: RefreshCwIcon,
  source_down: AlertTriangleIcon,
  system: InfoIcon,
}

const LABELS: Record<NotificationType, string> = {
  instant_match: "Strong match",
  daily_digest: "Shortlist",
  deadline_reminder: "Deadline",
  tender_updated: "Amended",
  source_down: "Source",
  system: "System",
}

/** Relative time, because "2 hours ago" is what a reader wants from a feed. */
function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ""
  const minutes = Math.round((Date.now() - then) / 60_000)
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })
}

export function NotificationList({
  notifications,
  isLoading,
  onRead,
}: {
  notifications: NotificationItem[]
  isLoading?: boolean
  onRead?: (id: string) => void
}) {
  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    )
  }

  if (!notifications.length) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <BellIcon />
          </EmptyMedia>
          <EmptyTitle>Nothing yet</EmptyTitle>
          <EmptyDescription>
            Strong matches, amended notices and deadlines on bids you are
            working on all land here.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <ul className="flex flex-col gap-2">
      {notifications.map((item) => {
        const Icon = ICONS[item.type] ?? InfoIcon
        const body = (
          <div className="flex flex-1 flex-col gap-1 text-left">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">{LABELS[item.type] ?? item.type}</Badge>
              {!item.read && (
                <span
                  className="size-2 rounded-full bg-primary"
                  aria-label="Unread"
                />
              )}
              <span className="text-xs text-muted-foreground">
                {timeAgo(item.created_at)}
              </span>
            </div>
            <span className="font-medium">{item.title}</span>
            {item.body && (
              <span className="text-sm text-muted-foreground">{item.body}</span>
            )}
          </div>
        )

        return (
          <li key={item.id}>
            <div
              className={`flex items-start gap-3 rounded-lg border p-3 ${
                item.read ? "" : "bg-muted/40"
              }`}
            >
              <Icon className="mt-1 size-4 shrink-0 text-muted-foreground" />
              {item.link ? (
                <Link
                  to={item.link}
                  className="flex flex-1"
                  onClick={() => !item.read && onRead?.(item.id)}
                >
                  {body}
                </Link>
              ) : (
                body
              )}
              {!item.read && onRead && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onRead(item.id)}
                >
                  Mark read
                </Button>
              )}
            </div>
          </li>
        )
      })}
    </ul>
  )
}
