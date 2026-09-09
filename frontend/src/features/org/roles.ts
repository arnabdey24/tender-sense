import type { components } from "@/lib/api/schema"

export type OrgRole = components["schemas"]["OrgRole"]

export const ROLE_ITEMS: { label: string; value: OrgRole }[] = [
  { label: "Admin", value: "admin" },
  { label: "Member", value: "member" },
]
