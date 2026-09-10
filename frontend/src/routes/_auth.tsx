import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router"

import { Logo } from "@/components/brand/Logo"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
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
    <div className="relative flex min-h-svh flex-col bg-muted/40">
      <header className="relative flex items-center justify-between px-6 py-5">
        <Link
          to="/"
          className="rounded-md outline-offset-4 focus-visible:outline-2 focus-visible:outline-ring"
          aria-label="TenderSense home"
        >
          <Logo size={26} />
        </Link>
        <ThemeToggle />
      </header>

      <main className="relative flex flex-1 flex-col items-center justify-center gap-6 px-6 pb-16">
        <Outlet />
      </main>
    </div>
  )
}
