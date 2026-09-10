import { formatValue } from "@/features/tenders/format"

/**
 * What the extractor pulled out of the notice, rendered as requirements a
 * bidder can read.
 *
 * This used to be `JSON.stringify(attributes, null, 2)` in a `<pre>` — a debug
 * view shipped to someone deciding whether to spend two weeks on a bid. The
 * data was always the interesting part; it just had no presentation. Anything
 * the notice does not state stays visibly unstated rather than being dropped,
 * because "not stated" is the answer that sends a bidder to the document.
 */

type Evidence = { field?: string; quote?: string | null; confidence?: number }

/** The order a bidder cares about: can we qualify, then what is the work. */
const FIELDS: { key: string; label: string }[] = [
  { key: "min_annual_turnover", label: "Minimum annual turnover" },
  { key: "min_years_experience", label: "Minimum years of experience" },
  { key: "similar_projects_required", label: "Similar projects required" },
  { key: "required_certifications", label: "Required certifications" },
  { key: "local_registration_required", label: "Local registration" },
  { key: "jv_allowed", label: "Joint ventures" },
  { key: "eligible_countries", label: "Eligible countries" },
  { key: "bid_security", label: "Bid security" },
  { key: "sectors", label: "Sectors" },
  { key: "key_deliverables", label: "Key deliverables" },
]

function isMoney(v: unknown): v is { amount: unknown; currency?: unknown } {
  return typeof v === "object" && v !== null && "amount" in v
}

/** Returns null when the notice genuinely says nothing about this field. */
function render(key: string, value: unknown): React.ReactNode | null {
  if (value === null || value === undefined) return null
  if (Array.isArray(value)) {
    return value.length ? value.join(", ") : null
  }
  if (isMoney(value)) {
    const amount = typeof value.amount === "number" ? value.amount : null
    if (amount === null) return null
    const currency =
      typeof value.currency === "string" ? value.currency : undefined
    return formatValue(amount, currency)
  }
  if (typeof value === "boolean") {
    if (key === "jv_allowed") return value ? "Permitted" : "Not permitted"
    if (key === "local_registration_required")
      return value ? "Required" : "Not required"
    return value ? "Yes" : "No"
  }
  if (typeof value === "number") return String(value)
  if (typeof value === "string") return value.trim() || null
  return null
}

export function RequirementsList({
  attributes,
}: {
  attributes: Record<string, unknown>
}) {
  const evidence = Array.isArray(attributes.field_evidence)
    ? (attributes.field_evidence as Evidence[])
    : []
  const confidenceOf = (key: string) =>
    evidence.find((e) => e.field === key)?.confidence

  const rows = FIELDS.map((field) => ({
    ...field,
    value: render(field.key, attributes[field.key]),
    confidence: confidenceOf(field.key),
  }))

  const stated = rows.filter((r) => r.value !== null)
  const unstated = rows.filter((r) => r.value === null)

  const scope =
    typeof attributes.scope_summary === "string"
      ? attributes.scope_summary.trim()
      : ""
  const qualifications =
    typeof attributes.required_qualifications_text === "string"
      ? attributes.required_qualifications_text.trim()
      : ""

  if (!stated.length && !unstated.length && !scope) return null

  return (
    <div className="flex flex-col gap-6">
      {stated.length > 0 && (
        <dl className="flex flex-col">
          {stated.map((row) => (
            <div
              key={row.key}
              className="grid grid-cols-1 gap-x-6 gap-y-1 border-t py-3 first:border-t-0 first:pt-0 sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]"
            >
              <dt className="text-sm text-muted-foreground">{row.label}</dt>
              <dd className="text-sm font-medium tabular-nums">
                {row.value}
                {row.confidence !== undefined && row.confidence < 0.6 ? (
                  <span className="ml-2 align-middle text-xs font-normal text-warning">
                    read with low confidence
                  </span>
                ) : null}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {qualifications ? (
        <div>
          <h3 className="text-sm font-medium">Qualification requirements</h3>
          <p className="mt-1.5 text-pretty text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
            {qualifications}
          </p>
        </div>
      ) : null}

      {unstated.length > 0 && (
        <div>
          <h3 className="text-sm font-medium">Not stated in this notice</h3>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {unstated.map((r) => r.label).join(" · ")}
          </p>
          <p className="mt-2 text-xs text-muted-foreground">
            Bidding documents are not parsed yet, so these need checking against
            the tender document before you commit.
          </p>
        </div>
      )}
    </div>
  )
}
