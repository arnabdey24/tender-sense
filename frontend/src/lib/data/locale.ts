/**
 * Small, dependency-free option lists for the organization forms.
 *
 * Country is a contract, not a convenience: the API validates it as an
 * ISO 3166-1 alpha-2 code, so the picker must yield the code and only ever
 * show the name. Timezones are validated as IANA zone names.
 */

export type Country = { code: string; name: string }

export const COUNTRIES: Country[] = [
  { code: "BD", name: "Bangladesh" },
  { code: "IN", name: "India" },
  { code: "PK", name: "Pakistan" },
  { code: "LK", name: "Sri Lanka" },
  { code: "NP", name: "Nepal" },
  { code: "BT", name: "Bhutan" },
  { code: "MV", name: "Maldives" },
  { code: "AE", name: "United Arab Emirates" },
  { code: "SA", name: "Saudi Arabia" },
  { code: "QA", name: "Qatar" },
  { code: "SG", name: "Singapore" },
  { code: "MY", name: "Malaysia" },
  { code: "ID", name: "Indonesia" },
  { code: "PH", name: "Philippines" },
  { code: "TH", name: "Thailand" },
  { code: "VN", name: "Vietnam" },
  { code: "AU", name: "Australia" },
  { code: "NZ", name: "New Zealand" },
  { code: "GB", name: "United Kingdom" },
  { code: "IE", name: "Ireland" },
  { code: "DE", name: "Germany" },
  { code: "FR", name: "France" },
  { code: "NL", name: "Netherlands" },
  { code: "ES", name: "Spain" },
  { code: "IT", name: "Italy" },
  { code: "SE", name: "Sweden" },
  { code: "NO", name: "Norway" },
  { code: "DK", name: "Denmark" },
  { code: "PL", name: "Poland" },
  { code: "TR", name: "Turkey" },
  { code: "ZA", name: "South Africa" },
  { code: "NG", name: "Nigeria" },
  { code: "KE", name: "Kenya" },
  { code: "EG", name: "Egypt" },
  { code: "US", name: "United States" },
  { code: "CA", name: "Canada" },
  { code: "BR", name: "Brazil" },
  { code: "MX", name: "Mexico" },
  { code: "JP", name: "Japan" },
  { code: "KR", name: "South Korea" },
  { code: "CN", name: "China" },
]

const BY_CODE = new Map(COUNTRIES.map((c) => [c.code, c]))

/** Display name for a stored code; falls back to the code itself. */
export function countryName(code: string | null | undefined): string {
  if (!code) return ""
  return BY_CODE.get(code.toUpperCase())?.name ?? code
}

/** Whether a stored value is one the picker can round-trip. */
export function isKnownCountry(code: string | null | undefined): boolean {
  return !!code && BY_CODE.has(code.toUpperCase())
}

const FALLBACK_TIMEZONES = [
  "Asia/Dhaka",
  "Asia/Kolkata",
  "Asia/Karachi",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "Africa/Lagos",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "UTC",
]

type IntlWithSupportedValues = typeof Intl & {
  supportedValuesOf?: (key: "timeZone") => string[]
}

/** Every IANA zone the runtime knows, falling back to a curated shortlist. */
export function timezoneOptions(): string[] {
  const intl = Intl as IntlWithSupportedValues
  try {
    const supported = intl.supportedValuesOf?.("timeZone")
    if (supported && supported.length > 0) return supported
  } catch {
    // Older engines: keep the fallback list.
  }
  return FALLBACK_TIMEZONES
}

/** The browser's own zone, when it can be determined. */
export function guessTimezone(fallback = "Asia/Dhaka"): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || fallback
  } catch {
    return fallback
  }
}
