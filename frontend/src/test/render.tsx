import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router"
import { render, waitFor, type RenderOptions } from "@testing-library/react"
import { http, HttpResponse } from "msw"
import type { ReactElement, ReactNode } from "react"

import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/toast"
import { TooltipProvider } from "@/components/ui/tooltip"
import { resetAuthBootstrap } from "@/lib/auth/bootstrap"
import { useAuthStore, type SessionPayload } from "@/lib/auth/store"
import { server } from "@/mocks/server"
import { createAppRouter } from "@/router"

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  })
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & { queryClient?: QueryClient }
) {
  const queryClient = options?.queryClient ?? createTestQueryClient()

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <Toaster>{children}</Toaster>
          </TooltipProvider>
        </QueryClientProvider>
      </ThemeProvider>
    )
  }

  return { queryClient, ...render(ui, { wrapper: Wrapper, ...options }) }
}

/**
 * Reset every module-level auth singleton between tests. Passing a session
 * also makes the silent refresh succeed, which is what actually signs the
 * user in once a route's `beforeLoad` awaits `waitForAuth()`.
 */
export function resetAuth(session?: SessionPayload) {
  resetAuthBootstrap()
  if (session) {
    server.use(
      http.post("*/api/v1/auth/refresh", () => HttpResponse.json(session))
    )
    useAuthStore.setState({
      status: "authed",
      accessToken: session.access_token,
      user: session.user,
      memberships: session.memberships ?? [],
      activeOrgId: session.active_org_id ?? null,
    })
  } else {
    useAuthStore.setState({
      status: "booting",
      accessToken: null,
      user: null,
      memberships: [],
      activeOrgId: null,
    })
  }
}

/**
 * Mount the real application router at `path` on a memory history, so route
 * guards, loaders and layouts all run exactly as they do in the browser.
 */
export async function renderRoute(
  path: string,
  options?: { session?: SessionPayload }
) {
  resetAuth(options?.session)
  const queryClient = createTestQueryClient()
  const router = createAppRouter(
    queryClient,
    createMemoryHistory({ initialEntries: [path] })
  )

  // Provider order mirrors main.tsx: the theme wraps everything, because the
  // header's theme control reads it during the very first render.
  const result = render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster>
            <RouterProvider router={router} />
          </Toaster>
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )

  await waitFor(() => {
    if (router.state.status !== "idle") throw new Error("router not idle")
  })

  return { ...result, router, queryClient }
}

export * from "@testing-library/react"
