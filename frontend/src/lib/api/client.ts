import createClient, { type Middleware } from "openapi-fetch"

import { API_ORIGIN } from "@/lib/api/base"
import type { paths } from "@/lib/api/schema"
import { refreshOnce, REFRESH_PATH } from "@/lib/auth/refresh"
import { useAuthStore } from "@/lib/auth/store"

const NO_RETRY_PATHS = [REFRESH_PATH, "/api/v1/auth/login"]

function shouldSkipRefresh(url: string): boolean {
  const { pathname } = new URL(url, window.location.origin)
  return NO_RETRY_PATHS.some((p) => pathname === p)
}

/** Pristine clones of outgoing requests so a 401 can be replayed once. */
const replayable = new WeakMap<Request, Request>()

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const token = useAuthStore.getState().accessToken
    if (token && !request.headers.has("Authorization")) {
      request.headers.set("Authorization", `Bearer ${token}`)
    }
    if (!request.headers.has("x-retried")) {
      replayable.set(request, request.clone())
    }
    return request
  },

  async onResponse({ request, response }) {
    if (response.status !== 401 || shouldSkipRefresh(request.url)) {
      return response
    }
    // Mark so we never loop: the replayed request carries this header.
    if (request.headers.has("x-retried")) {
      return response
    }

    const refreshed = await refreshOnce()
    if (!refreshed) {
      useAuthStore.getState().logout()
      return response
    }

    const retry = replayable.get(request) ?? request.clone()
    replayable.delete(request)
    retry.headers.set("x-retried", "1")
    const token = useAuthStore.getState().accessToken
    if (token) retry.headers.set("Authorization", `Bearer ${token}`)
    return fetch(retry)
  },
}

export const api = createClient<paths>({
  baseUrl: API_ORIGIN,
  credentials: "include",
  // Resolve `fetch` per call rather than capturing it at module load, so test
  // doubles (MSW) that swap `globalThis.fetch` are picked up.
  fetch: (request) => globalThis.fetch(request),
})

api.use(authMiddleware)
