/** Turning a URL segment into breadcrumb text. */

const LABELS: Record<string, string> = {
  app: "Home",
  dashboard: "Dashboard",
  today: "Today",
  matches: "Matches",
  tenders: "Tenders",
  pipeline: "Pipeline",
  notifications: "Notifications",
  settings: "Settings",
  profile: "Capability profile",
  organization: "Organization",
  members: "Members",
  onboarding: "Onboarding",
}

/** UUIDv7 with or without dashes — record ids that must not be title-cased. */
const ID_SEGMENT = /^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$/i

export function humanizeSegment(segment: string) {
  const known = LABELS[segment]
  if (known) return known
  // Title-casing a UUID gives "01a08644 403e 7ef2 8706 Babeb782048a", which is
  // both meaningless and wrong. The page heading already names the record.
  if (ID_SEGMENT.test(segment)) return "Detail"
  return segment.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}
