import { refreshOnce } from "@/lib/auth/refresh"
import { useAuthStore } from "@/lib/auth/store"

let bootPromise: Promise<void> | null = null

/**
 * Resolve the initial auth state exactly once per page load by attempting a
 * silent refresh. Safe to call from many places — returns the same promise.
 */
export function bootstrapAuth(): Promise<void> {
  if (!bootPromise) {
    bootPromise = refreshOnce().then(() => undefined)
  }
  return bootPromise
}

/** Test-only: forget the memoized boot so the next call refreshes again. */
export function resetAuthBootstrap(): void {
  bootPromise = null
}

/** Await until status is no longer "booting". */
export async function waitForAuth(): Promise<"authed" | "anon"> {
  await bootstrapAuth()
  const status = useAuthStore.getState().status
  return status === "booting" ? "anon" : status
}
