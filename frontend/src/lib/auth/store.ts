import { create } from "zustand"

import type { components } from "@/lib/api/schema"

export type AuthUser = components["schemas"]["UserRead"]
export type Membership = components["schemas"]["MembershipSummary"]
export type SessionPayload = components["schemas"]["SessionResponse"]
export type OrgRole = components["schemas"]["OrgRole"]

export type AuthStatus = "booting" | "authed" | "anon"

export type AuthState = {
  status: AuthStatus
  accessToken: string | null
  user: AuthUser | null
  memberships: Membership[]
  activeOrgId: string | null
  setSession: (payload: SessionPayload) => void
  /** Adopt a fresh profile without minting a new token (PATCH /users/me). */
  setUser: (user: AuthUser) => void
  setAccessToken: (token: string) => void
  setActiveOrg: (orgId: string | null) => void
  markAnon: () => void
  logout: () => void
}

const EMPTY = {
  accessToken: null,
  user: null,
  memberships: [] as Membership[],
  activeOrgId: null,
}

export const useAuthStore = create<AuthState>()((set) => ({
  status: "booting",
  ...EMPTY,

  setSession: (payload) =>
    set({
      status: "authed",
      accessToken: payload.access_token,
      user: payload.user,
      memberships: payload.memberships ?? [],
      activeOrgId: payload.active_org_id ?? null,
    }),

  setUser: (user) => set({ user }),

  setAccessToken: (token) => set({ accessToken: token }),

  setActiveOrg: (orgId) => set({ activeOrgId: orgId }),

  markAnon: () => set({ status: "anon", ...EMPTY }),

  logout: () => set({ status: "anon", ...EMPTY }),
}))

/** Role of the signed-in user inside the currently active organization. */
export function activeRole(state: AuthState): OrgRole | null {
  const membership = state.memberships.find(
    (m) => m.org_id === state.activeOrgId
  )
  return membership?.role ?? null
}

/** Convenience hook — `true` when the user administers the active org. */
export function useIsOrgAdmin(): boolean {
  return useAuthStore((s) => activeRole(s) === "admin")
}

/**
 * Platform staff, not organization admins. Gates the operator tools — running
 * a scrape, probing a portal, replaying stored pages — which act on the shared
 * pool every tenant reads from.
 */
export function useIsSuperuser(): boolean {
  return useAuthStore((s) => s.user?.is_superuser === true)
}
