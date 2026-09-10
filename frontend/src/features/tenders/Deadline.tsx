import { deadlineInfo, type DeadlineTone } from "@/features/tenders/format"
import { cn } from "@/lib/utils"

/**
 * The clock, rendered one way everywhere.
 *
 * It used to be three: a Badge component nothing imported any more, muted
 * right-aligned text that turned amber under seven days on the match rows, and
 * bold near-black text with no urgency at all in the tender pool — so the field
 * the product treats as decisive looked least urgent on the screen listing the
 * most notices. Every surface now renders this.
 *
 * Colour is never the only signal: the label always says what it means
 * ("4 days left", "Closes today", "Closed"), so the tone only reinforces it.
 */
const TONE: Record<DeadlineTone, string> = {
  expired: "text-muted-foreground",
  critical: "text-destructive",
  high: "text-warning",
  normal: "text-foreground",
  none: "text-muted-foreground",
}

export function Deadline({
  days,
  deadlineAt,
  className,
  muteNormal = false,
}: {
  days: number | null | undefined
  deadlineAt: string | null | undefined
  className?: string
  /** In a dense list, an unremarkable deadline should not read as emphasis. */
  muteNormal?: boolean
}) {
  const info = deadlineInfo(days, deadlineAt)
  const tone =
    muteNormal && info.tone === "normal" ? "text-muted-foreground" : TONE[info.tone]

  return (
    <span
      className={cn("font-medium tabular-nums whitespace-nowrap", tone, className)}
    >
      {info.label}
    </span>
  )
}
