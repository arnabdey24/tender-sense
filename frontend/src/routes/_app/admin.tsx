import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import { useAuthStore } from "@/lib/auth/store"
import { cn } from "@/lib/utils"

/**
 * The platform operator console.
 *
 * The guard is on the section rather than repeated on each page: every route
 * below it is staff-only, and a rule stated once cannot be forgotten on the
 * seventh page. The API enforces it independently — this only spares a
 * non-staff visitor a screen full of 403s.
 */
export const Route = createFileRoute("/_app/admin")({
  beforeLoad: () => {
    if (!useAuthStore.getState().user?.is_superuser) {
      throw redirect({ to: "/app/dashboard" })
    }
  },
  component: AdminLayout,
})

type AdminPage = {
  to:
    | "/admin"
    | "/admin/sources"
    | "/admin/pool"
    | "/admin/tenants"
    | "/admin/jobs"
    | "/admin/limits"
  label: string
  /** Overview is the section root, so every child would match it loosely. */
  exact?: boolean
}

const PAGES: AdminPage[] = [
  { to: "/admin", label: "Overview", exact: true },
  { to: "/admin/sources", label: "Portals" },
  { to: "/admin/pool", label: "Tender pool" },
  { to: "/admin/tenants", label: "Tenants" },
  { to: "/admin/jobs", label: "Jobs & mail" },
  { to: "/admin/limits", label: "Limits" },
]

function AdminLayout() {
  return (
    <>
      <PageHeader
        title="Operations"
        description="Platform staff only. Everything here is across every tenant — the pool, the portals, the queues and the limits they all run under."
      />

      {/*
        A rail of links rather than one page of stacked cards. The console had
        grown three cards on a single route while source registration, the
        tender pool, tenants and accounts had no screen at all, which is how an
        operator ends up in psql for questions the API already answers.
      */}
      <nav
        aria-label="Operations sections"
        className="-mb-px flex gap-1 overflow-x-auto border-b"
      >
        {PAGES.map((page) => (
          <Link
            key={page.to}
            to={page.to}
            activeOptions={{ exact: page.exact ?? false }}
            className={cn(
              "shrink-0 border-b-2 border-transparent px-3 py-2 text-sm font-medium text-muted-foreground transition-colors",
              "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            )}
            activeProps={{
              className: "border-primary text-foreground",
              "aria-current": "page",
            }}
          >
            {page.label}
          </Link>
        ))}
      </nav>

      <div className="pt-6">
        <Outlet />
      </div>
    </>
  )
}
