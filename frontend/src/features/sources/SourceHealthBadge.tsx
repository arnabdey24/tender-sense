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
 */
export function SourceHealthBadge({ health }: { health: SourceHealth }) {
  return <Badge variant={VARIANTS[health]}>{LABELS[health]}</Badge>
}
