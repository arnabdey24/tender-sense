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

const LABELS: Record<string, string> = {
  app: "Home",
  dashboard: "Dashboard",
  today: "Today",
  tenders: "Tenders",
  pipeline: "Pipeline",
  notifications: "Notifications",
  settings: "Settings",
  onboarding: "Onboarding",
}

function humanize(segment: string) {
  return (
    LABELS[segment] ??
    segment.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
  )
}

function AutoBreadcrumb() {
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const segments = pathname.split("/").filter(Boolean)

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {segments.map((segment, index) => {
          const href = "/" + segments.slice(0, index + 1).join("/")
          const isLast = index === segments.length - 1
          return (
            <React.Fragment key={href}>
              {index > 0 ? <BreadcrumbSeparator /> : null}
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{humanize(segment)}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink render={<Link to={href} />}>
                    {humanize(segment)}
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
        <span className="max-w-40 truncate">{label}</span>
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
        <span className="max-w-40 truncate">{label}</span>
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

export function AppHeader({ breadcrumb }: { breadcrumb?: React.ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <div className="min-w-0 flex-1">{breadcrumb ?? <AutoBreadcrumb />}</div>
      <div className="flex items-center gap-2">
        <OrgSwitcher />
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                variant="ghost"
                size="icon"
                aria-label="Notifications"
                render={<Link to="/app/notifications" />}
                nativeButton={false}
              />
            }
          >
            <BellIcon />
          </TooltipTrigger>
          <TooltipContent>Notifications</TooltipContent>
        </Tooltip>
      </div>
    </header>
  )
}
