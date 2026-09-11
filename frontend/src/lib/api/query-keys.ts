/**
 * Central query-key factory. Every React Query key in the app must come from
 * here so invalidation stays consistent. Extend per feature as endpoints land.
 */
export const qk = {
  assistant: {
    capabilities: (orgId: string | null, userId: string | undefined) => ["assistant", orgId, userId, "capabilities"] as const,
  },
  auth: {
    all: () => ["auth"] as const,
    me: () => ["auth", "me"] as const,
  },
  orgs: {
    all: () => ["orgs"] as const,
    current: () => ["orgs", "current"] as const,
    members: (page = 1, pageSize = 50) =>
      ["orgs", "current", "members", { page, pageSize }] as const,
    membersAll: () => ["orgs", "current", "members"] as const,
    invitations: () => ["orgs", "current", "invitations"] as const,
  },
  invitations: {
    preview: (token: string) => ["invitations", "preview", token] as const,
  },
  tenders: {
    all: () => ["tenders"] as const,
    list: (params: Record<string, unknown>) =>
      ["tenders", "list", params] as const,
    facets: (params: Record<string, unknown>) =>
      ["tenders", "facets", params] as const,
    detail: (id: string) => ["tenders", "detail", id] as const,
    sources: () => ["tenders", "sources"] as const,
    sync: () => ["tenders", "sources", "sync"] as const,
  },
  matches: {
    all: () => ["matches"] as const,
    list: (params: Record<string, unknown>) =>
      ["matches", "list", params] as const,
    stats: (params: Record<string, unknown>) =>
      ["matches", "stats", params] as const,
    today: (params: Record<string, unknown>) =>
      ["matches", "today", params] as const,
    pipeline: (params: Record<string, unknown>) =>
      ["matches", "pipeline", params] as const,
    detail: (tenderId: string) => ["matches", "detail", tenderId] as const,
  },
  profile: {
    all: () => ["profile"] as const,
    current: () => ["profile", "current"] as const,
    completeness: () => ["profile", "completeness"] as const,
    taxonomies: () => ["profile", "taxonomies"] as const,
  },
  rules: {
    all: () => ["rules"] as const,
    catalogue: () => ["rules", "catalogue"] as const,
    current: () => ["rules", "current"] as const,
    versions: () => ["rules", "versions"] as const,
  },
  decisions: {
    all: () => ["decisions"] as const,
    list: (params: Record<string, unknown>) =>
      ["decisions", "list", params] as const,
    forTender: (tenderId: string) => ["decisions", "tender", tenderId] as const,
  },
  notifications: {
    all: () => ["notifications"] as const,
    list: (unreadOnly: boolean) =>
      ["notifications", "list", unreadOnly] as const,
    unreadCount: () => ["notifications", "unread-count"] as const,
    settings: () => ["notifications", "settings"] as const,
    recipients: () => ["notifications", "recipients"] as const,
  },
  admin: {
    all: () => ["admin"] as const,
    sources: () => ["admin", "sources"] as const,
    scraperRuns: (sourceId?: string) =>
      ["admin", "scraper-runs", sourceId ?? "all"] as const,
    jobRuns: (name?: string) => ["admin", "job-runs", name ?? "all"] as const,
    emailOutbox: () => ["admin", "email-outbox"] as const,
    aiUsage: (days: number) => ["admin", "ai-usage", days] as const,
    overview: () => ["admin", "overview"] as const,
    organizations: (q?: string) => ["admin", "organizations", q ?? ""] as const,
    users: (q?: string) => ["admin", "users", q ?? ""] as const,
    limits: () => ["admin", "limits"] as const,
    adapters: () => ["admin", "adapters"] as const,
  },
  health: () => ["health"] as const,
} as const
