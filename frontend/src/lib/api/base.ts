/**
 * Absolute origin for API calls.
 *
 * The dev server and the production Caddyfile both serve the API from the same
 * origin as the SPA, so this is always `window.location.origin`. It must be
 * absolute rather than "/" because `Request` in Node (jsdom tests, SSR) cannot
 * parse a relative URL.
 */
export const API_ORIGIN =
  typeof window !== "undefined" && window.location?.origin
    ? window.location.origin
    : "http://localhost"

/** Absolute URL for an API path such as `/api/v1/auth/refresh`. */
export function apiUrl(path: string): string {
  return new URL(path, API_ORIGIN).toString()
}
