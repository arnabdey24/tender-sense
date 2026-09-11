import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { PageHeader } from "@/components/layout/PageHeader"
import { useAuthStore } from "@/lib/auth/store"

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

function AdminLayout() {
  return (
    <>
      <PageHeader
        title="Operations"
        description="Platform staff only. Everything here is across every tenant — the pool, the portals, the queues and the limits they all run under."
      />

      {/*
        The sections live in the sidebar now. A strip here repeated them, and
        two navigations for one thing makes both less trustworthy — the rail is
        the one that is always on screen, so it is the one that carries them.
      */}
      <div className="pt-2">
        <Outlet />
      </div>
    </>
  )
}
