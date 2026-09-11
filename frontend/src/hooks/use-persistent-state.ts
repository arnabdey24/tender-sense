import * as React from "react"

/**
 * State that outlives the route.
 *
 * Density and column choices are settings, not view state: a bid manager who
 * switches the tender pool to compact expects it compact tomorrow morning too.
 * Storage is best-effort — Safari's private mode throws on write, and a
 * browser with site data blocked throws on read — so every access is guarded
 * and a failure silently falls back to the in-memory default.
 */
function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function usePersistentState<T>(key: string, fallback: T) {
  const [value, setValue] = React.useState<T>(() => read(key, fallback))

  const set = React.useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved =
          typeof next === "function" ? (next as (p: T) => T)(prev) : next
        try {
          window.localStorage.setItem(key, JSON.stringify(resolved))
        } catch {
          /* Storage unavailable; the value still applies for this session. */
        }
        return resolved
      })
    },
    [key]
  )

  return [value, set] as const
}
