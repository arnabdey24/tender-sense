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

/**
 * A source code as a human reads it.
 *
 * The raw codes are database identifiers — `egp_bd`, `wb` — and uppercasing
 * them blindly printed "EGP_BD" in a column of otherwise typeset text, which
 * is the underscore of a column name leaking into the interface. Unknown
 * codes fall back to a readable form rather than being dropped, because a new
 * scraper should not need a frontend release to render.
 */
const SOURCE_LABELS: Record<string, string> = {
  egp_bd: "e-GP",
  wb: "World Bank",
}

export function sourceLabel(code: string | null | undefined): string {
  if (!code) return "—"
  return SOURCE_LABELS[code] ?? code.replace(/_/g, " ")
}

/** The same source, abbreviated for a narrow column. */
export function sourceShort(code: string | null | undefined): string {
  if (!code) return "—"
  const label = SOURCE_LABELS[code]
  if (label) return label === "World Bank" ? "WB" : label
  return code.replace(/_/g, " ")
}

/**
 * Text with the punctuation and casing removed, for comparing what two
 * strings actually say rather than how they are typed.
 */
function normalise(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
}

/**
 * Words a portal appends when it has nothing to add. e-GP's "Brief
 * Description" is very often the package title with one of these stuck on the
 * end, which then printed the same sentence twice on the tender page under two
 * different headings.
 */
const FILLER_WORD_LIMIT = 5

/**
 * True when this prose says nothing the text it is compared against already
 * said — so the section that would carry it should not be rendered at all.
 *
 * Deliberately conservative: it only suppresses an exact restatement, or a
 * restatement with a handful of filler words appended ("… as per tender
 * documents"). Anything that adds a real clause is kept, because hiding a
 * requirement is far more expensive than showing a repetitive line.
 */
export function addsNothing(
  text: string | null | undefined,
  ...against: (string | null | undefined)[]
): boolean {
  if (!text) return true
  const candidate = normalise(text)
  if (!candidate) return true

  return against.some((other) => {
    if (!other) return false
    const baseline = normalise(other)
    if (!baseline) return false
    if (candidate === baseline) return true
    if (!candidate.startsWith(baseline)) return false
    const remainder = candidate.slice(baseline.length).trim()
    return remainder.split(" ").filter(Boolean).length <= FILLER_WORD_LIMIT
  })
}
