import { createRootRouteWithContext, Outlet } from "@tanstack/react-router"
import * as React from "react"

import type { RouterContext } from "@/router"

const RouterDevtools = import.meta.env.DEV
  ? React.lazy(() =>
      import("@tanstack/react-router-devtools").then((m) => ({
        default: m.TanStackRouterDevtools,
      }))
    )
  : () => null

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  return (
    <>
      <Outlet />
      <React.Suspense fallback={null}>
        <RouterDevtools position="bottom-right" />
      </React.Suspense>
    </>
  )
}
