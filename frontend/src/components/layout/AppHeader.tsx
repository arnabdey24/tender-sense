import { useQueryClient } from "@tanstack/react-query"
import { Link, useRouterState } from "@tanstack/react-router"
import {
  BellIcon,
  Building2Icon,
  CheckIcon,
  ChevronsUpDownIcon,
} from "lucide-react"
import * as React from "react"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { humanizeSegment } from "@/components/layout/breadcrumb-labels"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Separator } from "@/components/ui/separator"
import { useUnreadCount } from "@/features/notifications/api"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { isApiError } from "@/lib/api/errors"
import { switchOrg } from "@/lib/auth/session"
import { useAuthStore } from "@/lib/auth/store"

function AutoBreadcrumb() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const segments = pathname.split("/").filter(Boolean)

  return (
    <Breadcrumb>
      {/* Wrapping put a second line inside a fixed 56px header on a phone. */}
      <BreadcrumbList className="flex-nowrap overflow-hidden">
        {segments.map((segment, index) => {
          const href = "/" + segments.slice(0, index + 1).join("/")
          const isLast = index === segments.length - 1
          return (
            <React.Fragment key={href}>
              {index > 0 ? <BreadcrumbSeparator /> : null}
              <BreadcrumbItem className="min-w-0 shrink">
                {isLast ? (
                  <BreadcrumbPage className="truncate">
                    {humanizeSegment(segment)}
                  </BreadcrumbPage>
                ) : (
                  <BreadcrumbLink
                    className="truncate"
                    render={<Link to={href} />}
                  >
                    {humanizeSegment(segment)}
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function OrgSwitcher() {
  const queryClient = useQueryClient()
  const memberships = useAuthStore((s) => s.memberships)
  const activeOrgId = useAuthStore((s) => s.activeOrgId)
  const active = memberships.find((m) => m.org_id === activeOrgId)
  const [switching, setSwitching] = React.useState(false)

  const label = active?.org_name ?? "No organization"

  // A single membership needs no menu — show it, but do not offer a switch.
  if (memberships.length <= 1) {
    return (
      <Button
        variant="outline"
        size="sm"
        disabled
        aria-label="Active organization"
      >
        <Building2Icon data-icon="inline-start" />
        <span className="hidden max-w-40 truncate sm:inline">{label}</span>
      </Button>
    )
  }

  async function handleSwitch(orgId: string) {
    if (orgId === activeOrgId) return
    setSwitching(true)
    try {
      await switchOrg(orgId, queryClient)
      // Everything on screen is org-scoped: refetch it against the new claim.
      await queryClient.refetchQueries({ type: "active" })
    } catch (error) {
      toast.add({
        type: "error",
        title: "Could not switch organization",
        description: isApiError(error) ? error.message : undefined,
      })
    } finally {
      setSwitching(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            disabled={switching}
            aria-label="Switch organization"
          />
        }
      >
        {switching ? (
          <Spinner data-icon="inline-start" />
        ) : (
          <Building2Icon data-icon="inline-start" />
        )}
        <span className="hidden max-w-40 truncate sm:inline">{label}</span>
        <ChevronsUpDownIcon data-icon="inline-end" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Organizations</DropdownMenuLabel>
          {memberships.map((membership) => (
            <DropdownMenuItem
              key={membership.org_id}
              onClick={() => void handleSwitch(membership.org_id)}
            >
              <Building2Icon />
              <span className="truncate">{membership.org_name}</span>
              {membership.org_id === activeOrgId ? (
                <CheckIcon className="ml-auto" />
              ) : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/**
 * The bell, with an unread count polled in the background. A badge that is a
 * minute stale costs nothing; a socket that has to survive a proxy, a sleeping
 * laptop and a token refresh costs a great deal.
 */
function NotificationBell() {
  const activeOrgId = useAuthStore((s) => s.activeOrgId)
  const unread = useUnreadCount(Boolean(activeOrgId))
  const count = unread.data?.unread ?? 0
  const label = count ? `Notifications (${count} unread)` : "Notifications"

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            aria-label={label}
            className="relative"
            render={<Link to="/app/notifications" />}
            nativeButton={false}
          />
        }
      >
        <BellIcon />
        {count > 0 && (
          // Ink rather than brand: an unread count is status, and blue is
          // reserved for things you can act on. It also sat over the middle of
          // the bell before, hiding the glyph it annotates.
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-foreground px-1 text-[10px] leading-none font-semibold text-background ring-2 ring-background tabular-nums"
          >
            {count > 9 ? "9+" : count}
          </span>
        )}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

export function AppHeader({ breadcrumb }: { breadcrumb?: React.ReactNode }) {
  return (
    // Sticky and translucent: the breadcrumb and org context stay reachable
    // while a long tender scrolls beneath them. Horizontal padding matches the
    // content column's, so the header's chrome starts on the page's gutter
    // instead of 4px inside it.
    <header className="material-chrome sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b px-4 md:px-6">
      <SidebarTrigger className="-ms-2" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <div className="min-w-0 flex-1">{breadcrumb ?? <AutoBreadcrumb />}</div>
      <div className="flex items-center gap-1">
        <OrgSwitcher />
        <Separator orientation="vertical" className="mx-1 h-4" />
        <ThemeToggle />
        <NotificationBell />
      </div>
    </header>
  )
}
