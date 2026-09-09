import { Badge } from "@/components/ui/badge"
import { deadlineInfo, type DeadlineTone } from "@/features/tenders/format"

const VARIANT_BY_TONE: Record<
  DeadlineTone,
  React.ComponentProps<typeof Badge>["variant"]
> = {
  expired: "outline",
  critical: "destructive",
  high: "warning",
  normal: "secondary",
  none: "outline",
}

export function DeadlineBadge({
  days,
  deadlineAt,
}: {
  days: number | null | undefined
  deadlineAt: string | null | undefined
}) {
  const info = deadlineInfo(days, deadlineAt)
  return <Badge variant={VARIANT_BY_TONE[info.tone]}>{info.label}</Badge>
}
