import { Link } from "@tanstack/react-router"
import { XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useRecipients } from "@/features/notifications/api"
import { useCompleteness } from "@/features/profile/api"
import { usePersistentState } from "@/hooks/use-persistent-state"

/**
 * One line of setup, not a column of cards.
 *
 * These were two cards in a right-hand rail. The rail held them at the top of
 * a column roughly six hundred pixels tall and left the rest empty, which
 * bought a permanent hole beside the day's work in exchange for two things a
 * user does once. They are the same task — this workspace is not finished
 * setting up — so they are one strip, they state only the next step, and they
 * disappear for good once there is nothing left to do.
 */
export function SetupStrip() {
  const [dismissed, setDismissed] = usePersistentState("setup-strip:dismissed", false)
  const completeness = useCompleteness()
  const recipients = useRecipients()

  const score = completeness.data?.score ?? 100
  const profileDone = score >= 100

  const list = recipients.data ?? []
  const hasVerified = list.some((r) => r.verified_at && !r.unsubscribed_at)
  const awaiting = list.some((r) => !r.verified_at)
  const emailDone = recipients.isPending || Boolean(recipients.error) || hasVerified

  if (dismissed) return null
  if (completeness.isPending) return null
  if (profileDone && emailDone) return null

  // The profile shapes every grade on the page below, so it outranks delivery.
  const task = !profileDone
    ? {
        title: "Finish your profile",
        detail:
          completeness.data?.next_step ?? "A fuller profile means sharper matches.",
        to: "/app/settings/profile" as const,
        action: "Open the profile",
        score,
      }
    : {
        title: awaiting ? "An address is still unconfirmed" : "Nothing is being emailed yet",
        detail: awaiting
          ? "Until someone clicks the link in it, matches only appear here in the app."
          : "Add an address so a strong match reaches you when nobody has the app open.",
        to: "/app/settings/notifications" as const,
        action: "Set up notifications",
        score: null,
      }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10">
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <p className="text-sm font-medium">{task.title}</p>
        <p className="min-w-0 text-sm text-muted-foreground">{task.detail}</p>
      </div>

      {task.score !== null ? (
        <div className="flex shrink-0 items-center gap-2">
          <Progress value={task.score} className="w-24" />
          <span className="text-xs tabular-nums text-muted-foreground">
            {Math.round(task.score)}%
          </span>
        </div>
      ) : null}

      <div className="flex shrink-0 items-center gap-1">
        <Button variant="outline" size="sm" render={<Link to={task.to} />} nativeButton={false}>
          {task.action}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Dismiss setup reminder"
          onClick={() => setDismissed(true)}
        >
          <XIcon />
        </Button>
      </div>
    </div>
  )
}
