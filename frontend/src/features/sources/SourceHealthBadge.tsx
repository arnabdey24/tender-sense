import { Badge } from "@/components/ui/badge"

import type { SourceHealth } from "@/features/sources/api"

const LABELS: Record<SourceHealth, string> = {
  ok: "Healthy",
  degraded: "Degraded",
  down: "Down",
}

const VARIANTS: Record<
  SourceHealth,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  ok: "success",
  degraded: "warning",
  down: "destructive",
}

/**
 * "Degraded" is deliberately distinct from "down": one timeout is weather,
 * three failures in a row is a broken portal, and collapsing the two would
 * either cry wolf or hide a real outage.
 *
 * A paused source reports neither. Health describes the last poll, and a source
 * nobody is polling has no health to report — it used to render the stale "ok"
 * from before it was paused, so a switched-off portal read as Healthy.
 */
export function SourceHealthBadge({
  health,
  enabled = true,
}: {
  health: SourceHealth
  enabled?: boolean
}) {
  if (!enabled) return <Badge variant="outline">Paused</Badge>
  return <Badge variant={VARIANTS[health]}>{LABELS[health]}</Badge>
}
