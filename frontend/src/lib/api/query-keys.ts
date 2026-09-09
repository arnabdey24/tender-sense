/**
 * Central query-key factory. Every React Query key in the app must come from
 * here so invalidation stays consistent. Extend per feature as endpoints land.
 */
export const qk = {
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
  },
  health: () => ["health"] as const,
} as const
