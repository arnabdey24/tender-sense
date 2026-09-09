import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { ReactQueryDevtools } from "@tanstack/react-query-devtools"
import { RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"
import { ThemeProvider } from "@/components/theme-provider"
import { Toaster } from "@/components/ui/toast"
import { TooltipProvider } from "@/components/ui/tooltip"
import { bootstrapAuth } from "@/lib/auth/bootstrap"
import { createAppRouter } from "@/router"

async function enableMocking() {
  if (import.meta.env.VITE_MOCK_API !== "1") return
  const { worker } = await import("@/mocks/browser")
  await worker.start({ onUnhandledRequest: "bypass" })
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

const router = createAppRouter(queryClient)

async function main() {
  await enableMocking()
  // Kick off the silent refresh; routes await it in beforeLoad as needed.
  void bootstrapAuth()

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <TooltipProvider>
            <Toaster>
              <RouterProvider router={router} />
            </Toaster>
          </TooltipProvider>
          {import.meta.env.DEV ? (
            <ReactQueryDevtools
              initialIsOpen={false}
              buttonPosition="bottom-left"
            />
          ) : null}
        </QueryClientProvider>
      </ThemeProvider>
    </StrictMode>
  )
}

void main()
