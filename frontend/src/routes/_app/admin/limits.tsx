import { createFileRoute } from "@tanstack/react-router"
import * as React from "react"
import { RotateCcwIcon } from "lucide-react"

import { ConsoleSection } from "@/components/layout/ConsoleSection"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Spinner } from "@/components/ui/spinner"
import { ApiErrorAlert } from "@/features/auth/ApiErrorAlert"
import {
  useLimits,
  useResetLimits,
  useSaveLimits,
  type Limits,
} from "@/features/admin/api"

export const Route = createFileRoute("/_app/admin/limits")({
  component: LimitsPage,
})

type Field = {
  key: keyof Limits
  label: string
  help: string
  unit?: string
  /** A switch rather than a number. */
  toggle?: boolean
}

/**
 * Grouped the way an operator thinks about them, not the way they are stored.
 *
 * Each `help` says what happens to a real person when the number is wrong,
 * because that is the judgement being made — a sign-in throttle is not "20", it
 * is how many colleagues can be locked out of one office before someone calls.
 */
const GROUPS: { title: string; caption: string; fields: Field[] }[] = [
  {
    title: "Portals",
    caption:
      "How often the portals may be asked for notices by hand. The tender pool is shared, so this is one limit across the whole deployment rather than one per tenant.",
    fields: [
      {
        key: "source_sync_cooldown_seconds",
        label: "Shortest gap between hand-started syncs",
        unit: "seconds",
        help: "Lower it to demonstrate a fresh deployment filling up; raise it if a portal starts refusing us. 0 allows a pull on every press.",
      },
      {
        key: "auto_sync_empty_pool",
        label: "Pull the portals automatically when the pool is empty",
        toggle: true,
        help: "On, a deployment with nothing in the pool starts one pull by itself when somebody opens the app — once per tab, never while a pass is running, never inside the cooldown. Worth turning off once the pool is filled and you would rather nothing happened without being asked.",
      },
    ],
  },
  {
    title: "Model spend",
    caption:
      "The daily ceiling on what the assistant and the matching pipeline may consume, and what one organization may take of it.",
    fields: [
      {
        key: "ai_daily_token_budget",
        label: "Tokens per day, all tenants",
        unit: "tokens",
        help: "Reached, the pipeline stops calling the model until tomorrow rather than running up a bill. 0 removes the cap.",
      },
      {
        key: "assistant_daily_turn_limit",
        label: "Assistant messages per organization per day",
        unit: "messages",
        help: "0 is unlimited.",
      },
      {
        key: "assistant_daily_voice_seconds",
        label: "Live voice per organization per day",
        unit: "seconds",
        help: "0 is unlimited.",
      },
    ],
  },
  {
    title: "Signing in",
    caption:
      "Guessing is cheap, so sign-in is throttled. Too tight and a real office sharing one address locks itself out; too loose and a password is worth guessing at.",
    fields: [
      {
        key: "login_attempts_per_ip",
        label: "Attempts from one address",
        unit: "per window",
        help: "Everyone in one office shares an address, so this counts the building, not the person.",
      },
      {
        key: "login_attempts_per_email",
        label: "Attempts against one account",
        unit: "per window",
        help: "This is the one that matters against guessing: it follows the account wherever the attempts come from.",
      },
      {
        key: "login_window_seconds",
        label: "The window both are counted over",
        unit: "seconds",
        help: "Counted from the first attempt, so a locked-out person waits at most this long.",
      },
    ],
  },
]

function LimitsPage() {
  const limits = useLimits()
  const save = useSaveLimits()
  const reset = useResetLimits()

  const [draft, setDraft] = React.useState<Limits | null>(null)
  const [loaded, setLoaded] = React.useState<Limits | null>(null)

  // React's documented way of resetting form state when the data behind it
  // changes: compared during render rather than copied in an effect.
  if (limits.data && limits.data !== loaded) {
    setLoaded(limits.data)
    setDraft(limits.data)
  }

  if (limits.isPending || !draft) {
    return limits.error ? (
      <ApiErrorAlert error={limits.error} />
    ) : (
      <Skeleton className="h-64 w-full" />
    )
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(loaded)

  return (
    <form
      className="flex flex-col gap-8"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate(draft)
      }}
    >
      <p className="max-w-prose text-pretty text-sm text-muted-foreground">
        These take effect within a few seconds, across every tenant, without a
        restart. Each starts at whatever this deployment was configured with;
        restoring clears the stored value rather than remembering a previous
        one, so it returns to a known state.
      </p>

      {/*
        Three groups of fields stacked down a 1,228px page, each a short list
        of numbers. They are independent of one another — nobody sets a
        sign-in throttle *because* of a model budget — so they sit side by side
        and the whole form is visible at once rather than scrolled through.
      */}
      <div className="grid gap-8 xl:grid-cols-3">
      {GROUPS.map((group) => (
        <ConsoleSection
          key={group.title}
          title={group.title}
          caption={group.caption}
        >
          <div className="flex flex-col gap-5">
            {group.fields.map((field) => (
              <div key={field.key} className="flex flex-col gap-1.5">
                {field.toggle ? (
                  <div className="flex items-center gap-3">
                    <Switch
                      id={field.key}
                      checked={Boolean(draft[field.key])}
                      onCheckedChange={(checked) =>
                        setDraft({ ...draft, [field.key]: checked })
                      }
                    />
                    <Label htmlFor={field.key}>{field.label}</Label>
                  </div>
                ) : (
                  <>
                    <Label htmlFor={field.key}>{field.label}</Label>
                    <div className="flex items-center gap-2">
                      <Input
                        id={field.key}
                        type="number"
                        inputMode="numeric"
                        min={0}
                        className="max-w-40 tabular-nums"
                        value={String(draft[field.key])}
                        onChange={(event) =>
                          setDraft({
                            ...draft,
                            [field.key]: Number(event.target.value),
                          })
                        }
                      />
                      {field.unit ? (
                        <span className="text-sm text-muted-foreground">
                          {field.unit}
                        </span>
                      ) : null}
                    </div>
                  </>
                )}
                <p className="max-w-prose text-pretty text-xs text-muted-foreground">
                  {field.help}
                </p>
              </div>
            ))}
          </div>
        </ConsoleSection>
      ))}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t pt-6">
        <Button type="submit" disabled={!dirty || save.isPending}>
          {save.isPending ? <Spinner label={null} /> : null}
          Save limits
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={reset.isPending}
          onClick={() => reset.mutate()}
        >
          {reset.isPending ? <Spinner label={null} /> : <RotateCcwIcon />}
          Restore configured values
        </Button>
        {dirty ? (
          <span className="text-sm text-muted-foreground" role="status">
            Unsaved changes.
          </span>
        ) : null}
      </div>
    </form>
  )
}
