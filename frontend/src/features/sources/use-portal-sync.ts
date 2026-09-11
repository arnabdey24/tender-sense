import * as React from "react"

import { countdown } from "@/lib/data/time"
import { useCompleteness } from "@/features/profile/api"
import {
  useSyncSources,
  useSyncState,
  type SyncState,
} from "@/features/sources/api"

/**
 * Below this, a sync is still worth running — the pool is shared, and the
 * notices arrive for everyone — but the organization that pressed the button
 * will not see a grade against any of them, which is not what pressing it
 * looks like it promises.
 */
export const PROFILE_SYNC_THRESHOLD = 50

/**
 * Tick a server-issued wait down locally.
 *
 * The cooldown is ten minutes. Polling for it would be asking a question whose
 * answer is already known — the server said how long, and a clock can count.
 * Reserving the network for what actually changes (whether a pass is running)
 * is also what lets the button stay honest while the tab is idle.
 */
function useCountdown(seconds: number): number {
  // Reset on a new figure from the server, the way React documents deriving
  // state from a prop: compared during render rather than in an effect, so the
  // count never renders one tick behind the answer it is counting down from.
  const [issued, setIssued] = React.useState(seconds)
  const [left, setLeft] = React.useState(seconds)

  if (issued !== seconds) {
    setIssued(seconds)
    setLeft(seconds)
  }

  React.useEffect(() => {
    if (seconds <= 0) return
    const timer = window.setInterval(
      () => setLeft((value) => (value <= 1 ? 0 : value - 1)),
      1000
    )
    return () => window.clearInterval(timer)
  }, [seconds])

  return left
}

type SyncControl = {
  state: SyncState | undefined
  running: boolean
  waiting: number
  disabled: boolean
  label: string
  press: () => void
  /** The profile is too thin for anything this pulls to be graded. */
  profileThin: boolean
  /** What the profile scores now, or undefined until it is known. */
  completeness: number | undefined
}

/**
 * The one place that decides what the sync button says and whether it works,
 * so the copy on the empty state and the copy in settings cannot drift apart.
 */
export function usePortalSync(): SyncControl {
  const state = useSyncState()
  const sync = useSyncSources()
  const completeness = useCompleteness()
  const waiting = useCountdown(state.data?.retry_after_seconds ?? 0)
  const running = state.data?.running ?? false

  // Unknown is not thin: a warning shown while the score is still loading
  // would flash on every page that carries the button.
  const score = completeness.data?.score
  const profileThin = score !== undefined && score < PROFILE_SYNC_THRESHOLD

  return {
    state: state.data,
    running,
    waiting,
    profileThin,
    completeness: score,
    disabled: sync.isPending || running || waiting > 0 || state.isPending,
    label: running
      ? "Syncing…"
      : waiting > 0
        ? `Again in ${countdown(waiting)}`
        : "Sync now",
    press: () => sync.mutate(),
  }
}


/**
 * Start a pull, once, when the pool is empty and nothing else is happening.
 *
 * The case this exists for is a deployment nobody has filled yet: a new
 * organization lands on a dashboard with nothing on it, and the honest next
 * step is the one thing they cannot be expected to know to go and do. So it
 * happens for them.
 *
 * Four guards, and each one is load-bearing:
 *
 * * **Only an empty pool.** A full pool and no matches is a profile or rules
 *   problem; pulling the portals again would change nothing and would spend a
 *   cooldown somebody else may need.
 * * **Once per tab.** A module-level flag rather than component state, so
 *   navigating back to the dashboard, or React remounting it, does not fire a
 *   second time.
 * * **Never while one is running or the cooldown is live.** The server would
 *   refuse anyway; not asking is politer and keeps the toast honest.
 * * **The cooldown is deployment-wide.** Ten people opening an empty dashboard
 *   at nine in the morning produce one pull between them, not ten.
 */
let attemptedThisSession = false

export function useAutoSyncEmptyPool(enabled = true): void {
  const state = useSyncState()
  const sync = useSyncSources()
  const data = state.data

  React.useEffect(() => {
    if (!enabled || attemptedThisSession || !data) return
    // The deployment's own answer, editable from the operations console: an
    // operator who would rather nothing happened without being asked can say
    // so, and this is the one place that acts without being asked.
    if (!data.auto_sync) return
    if (data.pool_size !== 0) return
    if (data.running || data.retry_after_seconds > 0) return
    if (sync.isPending) return

    attemptedThisSession = true
    sync.mutate()
  }, [enabled, data, sync])
}

/** Test seam: forget that this tab has already tried. */
export function resetAutoSync(): void {
  attemptedThisSession = false
}
