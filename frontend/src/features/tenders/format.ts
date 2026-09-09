/**
 * Presentation helpers for the shared tender pool. Kept dependency-free so the
 * table and detail pages format money, dates and deadlines the same way.
 */

const DATE_FMT: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "short",
  day: "numeric",
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleDateString(undefined, DATE_FMT)
}

export function formatValue(
  amount: number | null | undefined,
  currency: string | null | undefined
): string {
  if (amount == null) return "—"
  try {
    return new Intl.NumberFormat(undefined, {
      style: currency ? "currency" : "decimal",
      currency: currency ?? undefined,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${currency ? currency + " " : ""}${amount.toLocaleString()}`
  }
}

export type DeadlineTone = "expired" | "critical" | "high" | "normal" | "none"

export type DeadlineInfo = {
  tone: DeadlineTone
  label: string
}

/**
 * Turn "days to deadline" (as the API computes it, negative once past) into a
 * short label and a tone the badge palette understands.
 */
export function deadlineInfo(
  days: number | null | undefined,
  deadlineAt: string | null | undefined
): DeadlineInfo {
  if (days == null || !deadlineAt) return { tone: "none", label: "No deadline" }
  if (days < 0) return { tone: "expired", label: "Closed" }
  if (days === 0) return { tone: "critical", label: "Closes today" }
  const label = days === 1 ? "1 day left" : `${days} days left`
  if (days <= 3) return { tone: "critical", label }
  if (days <= 7) return { tone: "high", label }
  return { tone: "normal", label }
}

const CATEGORY_LABELS: Record<string, string> = {
  goods: "Goods",
  works: "Works",
  services: "Services",
  consulting: "Consulting",
  unknown: "Unknown",
}

export function categoryLabel(value: string): string {
  return CATEGORY_LABELS[value] ?? value
}

const STATUS_LABELS: Record<string, string> = {
  open: "Open",
  closed: "Closed",
  cancelled: "Cancelled",
  awarded: "Awarded",
  unknown: "Unknown",
}

export function statusLabel(value: string): string {
  return STATUS_LABELS[value] ?? value
}
