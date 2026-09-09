import { apiUrl } from "@/lib/api/base"
import { useAuthStore, type SessionPayload } from "@/lib/auth/store"

export const REFRESH_PATH = "/api/v1/auth/refresh"

let inFlight: Promise<boolean> | null = null

/**
 * Exchange the HttpOnly refresh cookie for a new access token.
 * Concurrent callers share one network request. Resolves `true` on success
 * (store updated) and `false` otherwise (store marked anon).
 */
export function refreshOnce(): Promise<boolean> {
  if (inFlight) return inFlight

  inFlight = (async () => {
    try {
      const res = await fetch(apiUrl(REFRESH_PATH), {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      })
      if (!res.ok) {
        useAuthStore.getState().markAnon()
        return false
      }
      const payload = (await res.json()) as SessionPayload
      useAuthStore.getState().setSession(payload)
      return true
    } catch {
      useAuthStore.getState().markAnon()
      return false
    } finally {
      inFlight = null
    }
  })()

  return inFlight
}
