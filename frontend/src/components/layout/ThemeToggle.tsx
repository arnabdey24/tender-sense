import { CheckIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react"
import * as React from "react"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Kbd } from "@/components/ui/kbd"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

const OPTIONS = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: MonitorIcon },
] as const

/** Track the OS preference so the trigger shows what is actually on screen. */
function useSystemPrefersDark() {
  const [dark, setDark] = React.useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
  )

  React.useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => setDark(query.matches)
    query.addEventListener("change", onChange)
    return () => query.removeEventListener("change", onChange)
  }, [])

  return dark
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const systemDark = useSystemPrefersDark()

  const resolved = theme === "system" ? (systemDark ? "dark" : "light") : theme
  const Icon = resolved === "dark" ? MoonIcon : SunIcon
  const current = OPTIONS.find((o) => o.value === theme)

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger
          render={
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Theme: ${current?.label ?? "System"}`}
                />
              }
            />
          }
        >
          <Icon />
        </TooltipTrigger>
        <TooltipContent className="flex items-center gap-2">
          <span>Theme — {current?.label ?? "System"}</span>
          <Kbd>D</Kbd>
        </TooltipContent>
      </Tooltip>

      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuGroup>
          <DropdownMenuLabel>Appearance</DropdownMenuLabel>
          {OPTIONS.map((option) => (
            <DropdownMenuItem
              key={option.value}
              onClick={() => setTheme(option.value)}
            >
              <option.icon />
              <span>{option.label}</span>
              {theme === option.value ? (
                <CheckIcon className="ml-auto" />
              ) : null}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
