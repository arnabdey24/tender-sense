import { useQueryClient } from "@tanstack/react-query"
import { Link, useNavigate, useRouterState } from "@tanstack/react-router"
import {
  BellIcon,
  CalendarCheckIcon,
  ChevronsUpDownIcon,
  FileTextIcon,
  KanbanIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  SettingsIcon,
  TargetIcon,
  WrenchIcon,
  UserRoundIcon,
  UsersIcon,
} from "lucide-react"

import { LogoMark } from "@/components/brand/Logo"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { signOut } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"

const NAV_ITEMS = [
  { title: "Dashboard", to: "/app/dashboard", icon: LayoutDashboardIcon },
  { title: "Today", to: "/app/today", icon: CalendarCheckIcon },
  { title: "Matches", to: "/app/matches", icon: TargetIcon },
  { title: "Tenders", to: "/app/tenders", icon: FileTextIcon },
  { title: "Pipeline", to: "/app/pipeline", icon: KanbanIcon },
  { title: "Notifications", to: "/app/notifications", icon: BellIcon },
  { title: "Settings", to: "/app/settings", icon: SettingsIcon },
] as const

//: Platform staff only. Kept out of NAV_ITEMS so it never renders for a
//: customer, who would only get a redirect from it anyway.
const STAFF_NAV = {
  title: "Operations",
  to: "/admin",
  icon: WrenchIcon,
} as const

function initials(name: string | undefined, email: string | undefined) {
  const source = name?.trim() || email || "?"
  return source
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
}

export function AppSidebar() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useAuthStore((s) => s.user)
  const activeOrg = useAuthStore((s) =>
    s.memberships.find((m) => m.org_id === s.activeOrgId)
  )

  async function handleSignOut() {
    await signOut({ queryClient })
    await navigate({ to: "/login" })
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {/*
          The collapse control lives here, not in the page header, so the
          breadcrumb can start on the content column's gutter instead of being
          pushed 45px right by a button sitting in the reading line. Collapsing
          hides it; the rail and Cmd/Ctrl+B bring the sidebar back.
        */}
        <div className="flex items-center gap-1">
          <SidebarMenu className="min-w-0 flex-1">
            <SidebarMenuItem>
              <SidebarMenuButton
                size="lg"
                render={<Link to="/app/dashboard" />}
              >
                {/* The parent forces every descendant svg to size-4, which is
                  right for nav icons and too small for the mark — hence the
                  explicit sizes, one per collapse state. */}
                <LogoMark
                  size={26}
                  className="size-6.5! text-primary group-data-[collapsible=icon]:size-5!"
                />
                <div className="flex min-w-0 flex-col gap-0.5 leading-none">
                  <span className="font-semibold tracking-[-0.012em]">
                    Tender<span className="text-primary">Sense</span>
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {activeOrg?.org_name ?? "No organization"}
                  </span>
                </div>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
          <SidebarTrigger className="shrink-0 group-data-[collapsible=icon]:hidden" />
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map((item) => (
                <SidebarMenuItem key={item.to}>
                  <SidebarMenuButton
                    tooltip={item.title}
                    isActive={pathname.startsWith(item.to)}
                    render={<Link to={item.to} />}
                  >
                    <item.icon />
                    <span>{item.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {user?.is_superuser && (
                <SidebarMenuItem>
                  <SidebarMenuButton
                    tooltip={STAFF_NAV.title}
                    isActive={pathname.startsWith(STAFF_NAV.to)}
                    render={<Link to={STAFF_NAV.to} />}
                  >
                    <STAFF_NAV.icon />
                    <span>{STAFF_NAV.title}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton size="lg" />}>
                {/* Without shrink-0 the avatar collapses under the name beside
                    it and the fallback initials print over the first glyph. */}
                <Avatar className="size-8 shrink-0">
                  {user?.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt="" />
                  ) : null}
                  <AvatarFallback>
                    {initials(user?.full_name, user?.email)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex min-w-0 flex-1 flex-col gap-0.5 text-left leading-none">
                  <span className="truncate font-medium">
                    {user?.full_name ?? "Signed in"}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {user?.email ?? ""}
                  </span>
                </div>
                <ChevronsUpDownIcon className="ml-auto shrink-0" />
              </DropdownMenuTrigger>
              <DropdownMenuContent
                side="top"
                align="start"
                className="min-w-56"
              >
                <DropdownMenuGroup>
                  <DropdownMenuLabel>
                    {user?.email ?? "Account"}
                  </DropdownMenuLabel>
                  <DropdownMenuItem render={<Link to="/account" />}>
                    <UserRoundIcon />
                    Account
                  </DropdownMenuItem>
                  <DropdownMenuItem render={<Link to="/app/settings" />}>
                    <SettingsIcon />
                    Settings
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    render={<Link to="/app/settings/members" />}
                  >
                    <UsersIcon />
                    Members
                  </DropdownMenuItem>
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
                <DropdownMenuGroup>
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => void handleSignOut()}
                  >
                    <LogOutIcon />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
