import { createFileRoute, Outlet, redirect } from "@tanstack/react-router"

import { AppHeader } from "@/components/layout/AppHeader"
import { AppSidebar } from "@/components/layout/AppSidebar"
import { CommandPalette } from "@/components/layout/CommandPalette"
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
        <CommandPalette />
        <SidebarInset>
          <AppHeader />
          {/*
            The floating assistant sits bottom-right over this column, and
            was covering the last row of every table and the pagination under
            it. The extra bottom padding is the launcher's height plus its
            offset, so content can always scroll clear of it.
          */}
          <div className="flex flex-1 flex-col gap-6 p-4 pb-28 md:p-6 md:pb-28">
            <Outlet />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </AssistantProvider>
  )
}
