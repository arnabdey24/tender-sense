import type { QueryClient } from "@tanstack/react-query"

import { unwrap } from "@/lib/api/call"
import { api } from "@/lib/api/client"
import { qk } from "@/lib/api/query-keys"
import { refreshOnce } from "@/lib/auth/refresh"
import { useAuthStore, type SessionPayload } from "@/lib/auth/store"

/**
 * Commit a fresh `SessionResponse` to the auth store and drop every cached
 * query that is scoped to the session or the active organization.
 *
 * Call this after login, verify-email, reset-password, switch-org and after
 * the post-create-org refresh — anything that hands back a new access token.
 */
export function applySession(
  payload: SessionPayload,
  queryClient?: QueryClient
): void {
  useAuthStore.getState().setSession(payload)
  invalidateSessionScopedQueries(queryClient)
}

export function invalidateSessionScopedQueries(queryClient?: QueryClient): void {
  if (!queryClient) return
  void queryClient.invalidateQueries({ queryKey: qk.auth.all() })
  void queryClient.invalidateQueries({ queryKey: qk.orgs.all() })
}

/**
 * Exchange the refresh cookie for a new access token.
 *
 * This is the only way to pick up a changed org claim: creating an org or
 * accepting an invitation mints the membership server-side but the access
 * token in hand still has no (or the old) `org_id`, so org-scoped calls would
 * fail with 403 `no_active_org` until this runs.
 */
export async function refreshSession(
  queryClient?: QueryClient
): Promise<boolean> {
  const ok = await refreshOnce()
  if (ok) invalidateSessionScopedQueries(queryClient)
  return ok
}

/** Switch the active organization and adopt the returned session. */
export async function switchOrg(
  orgId: string,
  queryClient?: QueryClient
): Promise<SessionPayload> {
  const payload = await unwrap(
    api.POST("/api/v1/auth/switch-org", { body: { org_id: orgId } })
  )
  applySession(payload, queryClient)
  return payload
}

/** Revoke the refresh cookie(s) and clear all local state. */
export async function signOut(options?: {
  everywhere?: boolean
  queryClient?: QueryClient
}): Promise<void> {
  try {
    await api.POST(
      options?.everywhere ? "/api/v1/auth/logout-all" : "/api/v1/auth/logout"
    )
  } catch {
    // Signing out locally must succeed even when the network call does not.
  }
  useAuthStore.getState().logout()
  options?.queryClient?.clear()
}

/** Reject anything that is not a same-site absolute path. */
export function sanitizeRedirect(redirect?: string | null): string | null {
  if (!redirect) return null
  if (!redirect.startsWith("/") || redirect.startsWith("//")) return null
  return redirect
}

/**
 * Where to land after a call that signs the user in. Users without a single
 * membership go to onboarding — every `/app/*` screen is org-scoped.
 */
export function postAuthDestination(
  payload: Pick<SessionPayload, "memberships">,
  redirect?: string | null
): string {
  if ((payload.memberships?.length ?? 0) === 0) return "/onboarding"
  return sanitizeRedirect(redirect) ?? "/app/dashboard"
}

/** Where the browser should be sent to begin Google sign-in. */
export function googleStartUrl(redirect = "/app/dashboard"): string {
  return `/api/v1/auth/google/start?redirect=${encodeURIComponent(redirect)}`
}
