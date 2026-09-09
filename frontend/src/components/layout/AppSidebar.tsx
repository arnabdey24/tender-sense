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
  UserRoundIcon,
  UsersIcon,
} from "lucide-react"

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
} from "@/components/ui/sidebar"
import { signOut } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"

const NAV_ITEMS = [
  { title: "Dashboard", to: "/app/dashboard", icon: LayoutDashboardIcon },
  { title: "Today", to: "/app/today", icon: CalendarCheckIcon },
  { title: "Tenders", to: "/app/tenders", icon: FileTextIcon },
  { title: "Pipeline", to: "/app/pipeline", icon: KanbanIcon },
  { title: "Notifications", to: "/app/notifications", icon: BellIcon },
  { title: "Settings", to: "/app/settings", icon: SettingsIcon },
] as const

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
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link to="/app/dashboard" />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <FileTextIcon />
              </div>
              <div className="flex min-w-0 flex-col gap-0.5 leading-none">
                <span className="font-semibold">TenderSense</span>
                <span className="truncate text-xs text-muted-foreground">
                  {activeOrg?.org_name ?? "No organization"}
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
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
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton size="lg" />}>
                <Avatar className="size-8">
                  {user?.avatar_url ? (
                    <AvatarImage src={user.avatar_url} alt="" />
                  ) : null}
                  <AvatarFallback>
                    {initials(user?.full_name, user?.email)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex min-w-0 flex-col gap-0.5 text-left leading-none">
                  <span className="truncate font-medium">
                    {user?.full_name ?? "Signed in"}
                  </span>
                  <span className="truncate text-xs text-muted-foreground">
                    {user?.email ?? ""}
                  </span>
                </div>
                <ChevronsUpDownIcon className="ml-auto" />
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
