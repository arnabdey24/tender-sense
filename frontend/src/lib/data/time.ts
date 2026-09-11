/**
 * Clock formatting shared across surfaces.
 *
 * A feed, a portal's last pull and a run record all answer the same question —
 * how long ago — and were each answering it in their own file. One definition
 * means "2h ago" means the same thing everywhere, including at the boundaries
 * where a rounding choice starts to show.
 */

/** Relative time, because "2 hours ago" is what a reader wants from a feed. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return ""
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

/**
 * A countdown in words. Rounds minutes up rather than down, so a control that
 * says "1 min" is never still refusing when the minute is over.
 */
export function countdown(seconds: number): string {
  if (seconds <= 0) return "now"
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.ceil(seconds / 60)
  return minutes === 1 ? "1 min" : `${minutes} min`
}
