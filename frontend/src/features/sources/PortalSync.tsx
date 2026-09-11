import * as React from "react"
import {
  CheckCircle2Icon,
  RefreshCwIcon,
  TriangleAlertIcon,
} from "lucide-react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { countdown, timeAgo } from "@/lib/data/time"
import { cn } from "@/lib/utils"
import type { PortalSyncState } from "@/features/sources/api"
import { usePortalSync } from "@/features/sources/use-portal-sync"

/** The control on its own, for a page that already has its own framing. */
export function PortalSyncButton({
  size = "sm",
  variant = "default",
  className,
}: {
  size?: React.ComponentProps<typeof Button>["size"]
  variant?: React.ComponentProps<typeof Button>["variant"]
  className?: string
}) {
  const { disabled, label, press, running } = usePortalSync()

  return (
    <Button
      size={size}
      variant={variant}
      className={className}
      disabled={disabled}
      onClick={press}
    >
      {running ? <Spinner label={null} /> : <RefreshCwIcon />}
      {label}
    </Button>
  )
}

/** One portal's position: what it is doing, or what the last pass found. */
function PortalLine({ portal }: { portal: PortalSyncState }) {
  const detail = portal.running
    ? "Working through the portal now"
    : portal.last_run_at
      ? [
          `Last pulled ${timeAgo(portal.last_run_at)}`,
          portal.last_status === "failed"
            ? "the portal did not answer"
            : portal.last_notices_added
              ? `${portal.last_notices_added} new`
              : "nothing new",
        ].join(" · ")
      : "Never pulled"

  const failed = !portal.running && portal.last_status === "failed"

  return (
    <div className="flex items-center gap-3 py-2 text-sm">
      {portal.running ? (
        <Spinner
          label={null}
          className="size-4 shrink-0 text-muted-foreground"
        />
      ) : failed ? (
        <TriangleAlertIcon className="size-4 shrink-0 text-warning" />
      ) : (
        <CheckCircle2Icon
          className={cn(
            "size-4 shrink-0",
            portal.last_run_at ? "text-success" : "text-muted-foreground/50"
          )}
        />
      )}
      <span className="min-w-0 flex-1 truncate font-medium">{portal.name}</span>
      <span className="shrink-0 text-xs text-muted-foreground">{detail}</span>
    </div>
  )
}

/**
 * Sync, with each portal's position underneath it.
 *
 * The button alone cannot answer the question a person actually has after
 * pressing it — whether anything is happening, and whether it found anything.
 * A timestamp from four hours ago reads the same whether a pass is running now
 * or the portal has been silent since, so the two are shown apart.
 */
export function PortalSyncPanel({ className }: { className?: string }) {
  const { state, running, waiting, disabled, label, press } = usePortalSync()

  return (
    <div
      className={cn(
        "rounded-lg bg-surface-sunken p-4 ring-1 ring-foreground/10",
        className
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">Pull every portal now</p>
          <p className="text-sm text-pretty text-muted-foreground">
            For a first pull, or for today&rsquo;s notices before the next
            scheduled pass. Portals are visited one at a time, so a sync is as
            gentle as the schedule is.
          </p>
        </div>
        <Button size="sm" disabled={disabled} onClick={press}>
          {running ? <Spinner label={null} /> : <RefreshCwIcon />}
          {label}
        </Button>
      </div>

      {state?.portals.length ? (
        <div className="mt-3 divide-y border-t pt-1">
          {state.portals.map((portal) => (
            <PortalLine key={portal.id} portal={portal} />
          ))}
        </div>
      ) : null}

      {waiting > 0 && !running && (
        <p className="mt-3 text-xs text-muted-foreground" role="status">
          One sync at a time across the whole deployment, so an old portal is
          never asked twice for the same thing. Next pull available in{" "}
          {countdown(waiting)}.
        </p>
      )}
    </div>
  )
}
