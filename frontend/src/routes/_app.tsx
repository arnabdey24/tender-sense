import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { AppHeader } from "@/components/layout/AppHeader"
import { AppSidebar } from "@/components/layout/AppSidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"
import { waitForAuth } from "@/lib/auth/bootstrap"
import { useAuthStore } from "@/lib/auth/store"
import { AssistantProvider } from "@/features/assistant/AssistantProvider"

/** Screens a member-less account may still visit. */
const ORGLESS_ALLOWED = ["/onboarding", "/account"]

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const status = await waitForAuth()
    if (status !== "authed") {
      throw redirect({
        to: "/login",
        search: { redirect: location.href },
      })
    }

    // Every `/app/*` screen is org-scoped; without a membership the API would
    // answer 403 `no_active_org`, so send the user to create one first.
    const { memberships } = useAuthStore.getState()
    const allowed = ORGLESS_ALLOWED.some((p) => location.pathname.startsWith(p))
    if (memberships.length === 0 && !allowed) {
      throw redirect({ to: "/onboarding" })
    }
  },
  component: AppLayout,
})

function AppLayout() {
  return (
    <AssistantProvider>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <AppHeader />
          <div className="flex flex-1 flex-col gap-6 p-4 md:p-6">
            <Outlet />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </AssistantProvider>
  )
}
