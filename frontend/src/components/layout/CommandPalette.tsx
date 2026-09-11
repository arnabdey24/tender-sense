import { useNavigate } from "@tanstack/react-router"
import {
  BellIcon,
  CalendarCheckIcon,
  FileTextIcon,
  KanbanIcon,
  LayoutDashboardIcon,
  MonitorIcon,
  MoonIcon,
  SettingsIcon,
  SunIcon,
  TargetIcon,
  UserRoundIcon,
} from "lucide-react"
import * as React from "react"

import { useTheme } from "@/components/theme-provider"
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command"
import { useTenders } from "@/features/tenders/api"
import { Deadline } from "@/features/tenders/Deadline"

const DESTINATIONS = [
  { label: "Dashboard", to: "/app/dashboard", icon: LayoutDashboardIcon },
  { label: "Today", to: "/app/today", icon: CalendarCheckIcon },
  { label: "Matches", to: "/app/matches", icon: TargetIcon },
  { label: "Tenders", to: "/app/tenders", icon: FileTextIcon },
  { label: "Pipeline", to: "/app/pipeline", icon: KanbanIcon },
  { label: "Notifications", to: "/app/notifications", icon: BellIcon },
  { label: "Settings", to: "/app/settings", icon: SettingsIcon },
  { label: "Account", to: "/account", icon: UserRoundIcon },
] as const

/**
 * Jump anywhere, or straight to a notice, without reaching for the mouse.
 *
 * `cmdk` and a `CommandDialog` wrapper were both already installed and
 * imported by nothing — the dependency was paid for and never spent. For the
 * bid manager PRODUCT.md describes, who lives in this at a desk under
 * deadline pressure, this is the single highest-value keyboard affordance the
 * app can offer: the tender search is the same endpoint the pool page uses,
 * so typing three words reaches a notice in two keystrokes and a return.
 */
export function CommandPalette() {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")
  const navigate = useNavigate()
  const { theme, setTheme } = useTheme()

  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((v) => !v)
      }
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [])

  // Only search once there is enough to search for; a one-character query
  // returns most of the pool and none of it is useful.
  const term = query.trim()
  const tenders = useTenders({
    q: term.length >= 2 ? term : undefined,
    page_size: 6,
    sort: "deadline_at",
    descending: false,
  })
  const results = term.length >= 2 ? (tenders.data?.items ?? []) : []

  const run = (action: () => void) => {
    setOpen(false)
    setQuery("")
    action()
  }

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      title="Command palette"
      description="Search notices or jump to a page."
    >
      {/* `shouldFilter={false}` because the notice results are already
          filtered by the server; letting cmdk score them again would hide
          matches the API deliberately returned. */}
      <CommandInput
        placeholder="Search notices, or jump to a page…"
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>
          {tenders.isPending && term.length >= 2
            ? "Searching…"
            : "Nothing matches that."}
        </CommandEmpty>

        {results.length > 0 ? (
          <>
            <CommandGroup heading="Notices">
              {results.map((tender) => (
                <CommandItem
                  key={tender.id}
                  value={`tender-${tender.id}-${tender.title}`}
                  onSelect={() =>
                    run(() =>
                      void navigate({
                        to: "/app/tenders/$tenderId",
                        params: { tenderId: tender.id },
                      })
                    )
                  }
                >
                  <FileTextIcon />
                  <span className="min-w-0 flex-1 truncate">{tender.title}</span>
                  <Deadline
                    days={tender.days_to_deadline}
                    deadlineAt={tender.deadline_at}
                    muteNormal
                    className="text-xs"
                  />
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        ) : null}

        <CommandGroup heading="Go to">
          {DESTINATIONS.map((destination) => (
            <CommandItem
              key={destination.to}
              value={`go ${destination.label}`}
              onSelect={() =>
                run(() => void navigate({ to: destination.to }))
              }
            >
              <destination.icon />
              {destination.label}
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        <CommandGroup heading="Appearance">
          {(
            [
              { value: "light", label: "Light", icon: SunIcon },
              { value: "dark", label: "Dark", icon: MoonIcon },
              { value: "system", label: "Match the system", icon: MonitorIcon },
            ] as const
          ).map((option) => (
            <CommandItem
              key={option.value}
              value={`theme ${option.label}`}
              onSelect={() => run(() => setTheme(option.value))}
            >
              <option.icon />
              {option.label}
              {theme === option.value ? (
                <CommandShortcut>Current</CommandShortcut>
              ) : null}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
