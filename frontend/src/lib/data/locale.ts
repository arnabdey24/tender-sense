/**
 * Small, dependency-free option lists for the organization forms.
 * The API stores free-form strings, so these are conveniences, not contracts.
 */

export const COUNTRIES: string[] = [
  "Bangladesh",
  "India",
  "Pakistan",
  "Sri Lanka",
  "Nepal",
  "United Arab Emirates",
  "Saudi Arabia",
  "Qatar",
  "Singapore",
  "Malaysia",
  "Indonesia",
  "Philippines",
  "Thailand",
  "Vietnam",
  "Australia",
  "New Zealand",
  "United Kingdom",
  "Ireland",
  "Germany",
  "France",
  "Netherlands",
  "Spain",
  "Italy",
  "Sweden",
  "Norway",
  "Denmark",
  "Poland",
  "Turkey",
  "South Africa",
  "Nigeria",
  "Kenya",
  "Egypt",
  "United States",
  "Canada",
  "Brazil",
  "Mexico",
  "Japan",
  "South Korea",
  "China",
]

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
