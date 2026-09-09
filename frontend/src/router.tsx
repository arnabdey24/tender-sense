import type { QueryClient } from "@tanstack/react-query"
import { createRouter, type RouterHistory } from "@tanstack/react-router"

import {
  DefaultError,
  DefaultNotFound,
} from "@/components/layout/RouterFallbacks"
import { useAuthStore, type AuthState } from "@/lib/auth/store"
import { routeTree } from "@/routeTree.gen"

export type RouterContext = {
  queryClient: QueryClient
  /** Snapshot accessor — always read fresh state via `auth.getState()`. */
  auth: typeof useAuthStore
}

export function createAppRouter(
  queryClient: QueryClient,
  /** Supply a memory history in tests; the browser history is the default. */
  history?: RouterHistory
) {
  return createRouter({
    routeTree,
    ...(history ? { history } : {}),
    context: { queryClient, auth: useAuthStore } satisfies RouterContext,
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
    defaultNotFoundComponent: DefaultNotFound,
    defaultErrorComponent: DefaultError,
  })
}

export type AppRouter = ReturnType<typeof createAppRouter>

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter
  }
}

export type { AuthState }
