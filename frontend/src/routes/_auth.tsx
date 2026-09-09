import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router"

import { waitForAuth } from "@/lib/auth/bootstrap"

export const Route = createFileRoute("/_auth")({
  beforeLoad: async () => {
    const status = await waitForAuth()
    if (status === "authed") {
      throw redirect({ to: "/app/dashboard" })
    }
  },
  component: AuthLayout,
})

function AuthLayout() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-muted/40 p-6">
      <Link to="/" className="text-lg font-semibold tracking-tight">
        TenderSense
      </Link>
      <Outlet />
    </main>
  )
}
